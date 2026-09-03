import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import B24Client, PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"

COMPANY_FIELDS = ["ID", "TITLE", "COMPANY_TYPE", "INDUSTRY", "REVENUE",
                  "EMAIL", "PHONE", "DATE_MODIFY"]
CONTACT_FIELDS = ["ID", "NAME", "LAST_NAME", "COMPANY_ID", "EMAIL", "PHONE",
                  "DATE_MODIFY"]


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def _join_multi(v, field="VALUE"):
    if not v:
        return None
    if isinstance(v, list):
        return "; ".join(str(x.get(field) or "") for x in v if isinstance(x, dict) and x.get(field))
    return str(v)


def ensure_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS companies (
            ID TEXT PRIMARY KEY, TITLE TEXT, COMPANY_TYPE TEXT, INDUSTRY TEXT,
            REVENUE TEXT, EMAIL TEXT, PHONE TEXT, DATE_MODIFY TEXT
        );
        CREATE TABLE IF NOT EXISTS contacts (
            ID TEXT PRIMARY KEY, NAME TEXT, LAST_NAME TEXT, NAME_LAST TEXT,
            COMPANY_ID TEXT, COMPANY_TITLE TEXT, EMAIL TEXT, PHONE TEXT,
            DATE_MODIFY TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_deals_company ON deals(COMPANY_ID);
        CREATE INDEX IF NOT EXISTS idx_deals_contact ON deals(CONTACT_ID);
    """)
    conn.commit()


def load_companies(client, conn, max_rec=None, resume=0):
    cols = ["ID", "TITLE", "COMPANY_TYPE", "INDUSTRY", "REVENUE", "EMAIL",
            "PHONE", "DATE_MODIFY"]
    insert = ("INSERT OR IGNORE INTO companies (ID,TITLE,COMPANY_TYPE,"
              "INDUSTRY,REVENUE,EMAIL,PHONE,DATE_MODIFY) VALUES (?,?,?,?,?,?,?,?)")
    update = ("UPDATE companies SET TITLE=?,COMPANY_TYPE=?,INDUSTRY=?,REVENUE=?,"
              "EMAIL=?,PHONE=?,DATE_MODIFY=? WHERE ID=?")
    n = 0

    def save_off(off):
        conn.execute("INSERT OR REPLACE INTO kb_meta (key,value) VALUES ('comp_offset',?)",
                     (str(off),))
        conn.commit()

    for items, total in client.paged_gentle(
            "crm.company.list", {}, step=50, max_deals=(
                (max_rec - resume) if max_rec is not None else None),
            start_offset=resume, select=COMPANY_FIELDS):
        buf = []
        for it in items:
            row = (it.get("ID"), it.get("TITLE"), it.get("COMPANY_TYPE"),
                   it.get("INDUSTRY"), it.get("REVENUE"),
                   _join_multi(it.get("EMAIL")), _join_multi(it.get("PHONE")),
                   it.get("DATE_MODIFY"))
            buf.append(row)
        if buf:
            ids = [r[0] for r in buf]
            ph = ",".join("?" * len(ids))
            existing = {r[0] for r in conn.execute(
                f"SELECT ID FROM companies WHERE ID IN ({ph})", ids)}
            for row in buf:
                if row[0] in existing:
                    conn.execute(update, (*row[1:], row[0]))
                else:
                    conn.execute(insert, row)
            conn.commit()
            n += len(buf)
    # сохранить финальный offset
    return n, total


def load_contacts(client, conn, max_rec=None, resume=0):
    conn.execute("CREATE TABLE IF NOT EXISTS contacts (ID TEXT PRIMARY KEY, "
                 "NAME TEXT, LAST_NAME TEXT, NAME_LAST TEXT, COMPANY_ID TEXT, "
                 "COMPANY_TITLE TEXT, EMAIL TEXT, PHONE TEXT, DATE_MODIFY TEXT);")
    col = ["ID", "NAME", "LAST_NAME", "NAME_LAST", "COMPANY_ID",
           "COMPANY_TITLE", "EMAIL", "PHONE", "DATE_MODIFY"]
    insert = ("INSERT OR IGNORE INTO contacts (ID,NAME,LAST_NAME,NAME_LAST,"
              "COMPANY_ID,COMPANY_TITLE,EMAIL,PHONE,DATE_MODIFY) "
              "VALUES (?,?,?,?,?,?,?,?,?)")
    update = ("UPDATE contacts SET NAME=?,LAST_NAME=?,NAME_LAST=?,COMPANY_ID=?,"
              "COMPANY_TITLE=?,EMAIL=?,PHONE=?,DATE_MODIFY=? WHERE ID=?")
    # кэш названий компаний
    comp_title = {}
    for r in conn.execute("SELECT ID, TITLE FROM companies").fetchall():
        comp_title[r[0]] = r[1]

    def title(comp_id):
        if comp_id in comp_title:
            return comp_title[comp_id]
        row = conn.execute("SELECT TITLE FROM companies WHERE ID=?", (comp_id,)).fetchone()
        t = row[0] if row else None
        comp_title[comp_id] = t
        return t

    n = 0
    for items, total in client.paged_gentle("crm.contact.list", {}, step=50,
                                            max_deals=(max_rec - resume) if max_rec is not None else None,
                                            start_offset=resume, select=CONTACT_FIELDS):
        buf = []
        new_comp = set()
        for it in items:
            cid = it.get("COMPANY_ID")
            if cid:
                new_comp.add(cid)
            name = it.get("NAME") or ""
            last = it.get("LAST_NAME") or ""
            buf.append([it.get("ID"), name, last, f"{name} {last}".strip(),
                        cid, None, _join_multi(it.get("EMAIL")),
                        _join_multi(it.get("PHONE")), it.get("DATE_MODIFY")])
        # подтянем недостающие названия компаний
        missing = {c for c in new_comp if c not in comp_title}
        for cid in missing:
            r = conn.execute("SELECT TITLE FROM companies WHERE ID=?", (cid,)).fetchone()
            comp_title[cid] = r[0] if r else None
        for row in buf:
            row[5] = comp_title.get(row[4])
        ids = [row[0] for row in buf]
        ph = ",".join("?" * len(ids))
        existing = {r[0] for r in conn.execute(
            f"SELECT ID FROM contacts WHERE ID IN ({ph})", ids)}
        for row in buf:
            if row[0] in existing:
                conn.execute(update, (*row[1:], row[0]))
                existing.add(row[0])
            else:
                conn.execute(insert, row)
        conn.commit()
        n += len(buf)
    return n, total


def main():
    ap = argparse.ArgumentParser(description="Обогащение БД компаниями и контактами")
    ap.add_argument("--segment", choices=["companies", "contacts", "all"],
                    default="all")
    ap.add_argument("--max-rec", type=int, default=None)
    ap.add_argument("--rebuild-refs", action="store_true")
    args = ap.parse_args()

    client = B24Client()
    conn = connect()
    ensure_schema(conn)

    if args.segment in ("companies", "all"):
        row = conn.execute("SELECT value FROM kb_meta WHERE key='comp_offset'").fetchone()
        resume = int(row[0]) if row and row[0] else 0
        print(f"Выгрузка компаний (резюм с {resume})...")
        t0 = time.time()
        n, total = load_companies(client, conn, args.max_rec, resume)
        cur = resume + n
        conn.execute("INSERT OR REPLACE INTO kb_meta (key,value) VALUES ('comp_offset',?)",
                     (str(cur),))
        conn.commit()
        print(f"   компаний обработано: {n}, всего в БД: "
              f"{conn.execute('SELECT COUNT(*) FROM companies').fetchone()[0]}, "
              f"за {time.time()-t0:.0f}с")

    if args.segment in ("contacts", "all"):
        row = conn.execute("SELECT value FROM kb_meta WHERE key='cont_offset'").fetchone()
        resume = int(row[0]) if row and row[0] else 0
        print(f"Выгрузка контактов (резюм с {resume})...")
        t0 = time.time()
        n, total = load_contacts(client, conn, args.max_rec, resume)
        cur = resume + n
        conn.execute("INSERT OR REPLACE INTO kb_meta (key,value) VALUES ('cont_offset',?)",
                     (str(cur),))
        conn.commit()
        print(f"   контактов обработано: {n}, всего в БД: "
              f"{conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]}, "
              f"за {time.time()-t0:.0f}с")

    # связать контакты с компаниями, если ещё не связаны
    conn.execute("UPDATE contacts SET COMPANY_TITLE = (SELECT TITLE FROM companies "
                 "WHERE companies.ID = contacts.COMPANY_ID) "
                 "WHERE COMPANY_ID IS NOT NULL")
    conn.commit()
    print("Готово.")
    conn.close()


if __name__ == "__main__":
    main()
