import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import B24Client, PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"

# Пользовательские file-поля сделок (из crm.item.fields, entityTypeId=2)
FILE_FIELDS = [
    "ufCrm_1750424044", "ufCrm_1613540481", "ufCrm_1611564211204",
    "ufCrm_1612697545967", "ufCrm_1635849030184", "ufCrm_634D12F9F11EF",
    "ufCrm_634D5C590B487", "ufCrm_6384B973AD315", "ufCrm_64369F742F892",
    "ufCrm_64369F744C2D1", "ufCrm_1684444873362", "ufCrmFilecEmployee",
]

DEAL_FIELDS = [
    "ID", "TITLE", "TYPE_ID", "STAGE_ID", "PREVIOUS_STAGE_ID", "PROBABILITY",
    "CURRENCY_ID", "OPPORTUNITY", "IS_MANUAL_OPPORTUNITY", "TAX_VALUE",
    "LEAD_ID", "COMPANY_ID", "CONTACT_ID", "MYCOMPANY_ID", "QUOTE_ID",
    "BEGINDATE", "CLOSEDATE", "ASSIGNED_BY_ID", "CREATED_BY_ID",
    "MODIFY_BY_ID", "DATE_CREATE", "DATE_MODIFY", "OPENED", "CLOSED",
    "COMMENTS", "ADDITIONAL_INFO", "LOCATION_ID", "CATEGORY_ID",
    "STAGE_SEMANTIC_ID", "IS_NEW", "IS_RECURRING", "IS_RETURN_CUSTOMER",
    "IS_REPEATED_APPROACH", "SOURCE_ID", "SOURCE_DESCRIPTION",
    "ORIGINATOR_ID", "ORIGIN_ID", "MOVED_BY_ID", "MOVED_TIME",
    "LAST_ACTIVITY_TIME", "UTM_SOURCE", "UTM_MEDIUM", "UTM_CAMPAIGN",
    "UTM_CONTENT", "UTM_TERM", "PARENT_ID_141", "PARENT_ID_166",
    "PARENT_ID_177", "PARENT_ID_1038", "LAST_COMMUNICATION_TIME",
    "LAST_ACTIVITY_BY",
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    ID TEXT PRIMARY KEY,
    %(deal_cols)s
);

CREATE TABLE IF NOT EXISTS deal_categories (
    ID TEXT PRIMARY KEY,
    NAME TEXT
);

CREATE TABLE IF NOT EXISTS deal_stages (
    STATUS_ID TEXT,
    CATEGORY_ID TEXT,
    NAME TEXT,
    SEMANTIC_ID TEXT,
    PRIMARY KEY (STATUS_ID, CATEGORY_ID)
);

CREATE TABLE IF NOT EXISTS sources (
    ID TEXT PRIMARY KEY,
    NAME TEXT
);

CREATE TABLE IF NOT EXISTS deal_types (
    ID TEXT PRIMARY KEY,
    NAME TEXT
);

CREATE TABLE IF NOT EXISTS users (
    ID TEXT PRIMARY KEY,
    NAME TEXT,
    LAST_NAME TEXT,
    LOGIN TEXT
);

CREATE TABLE IF NOT EXISTS deal_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id TEXT,
    field_name TEXT,
    file_id TEXT,
    file_name TEXT,
    file_url TEXT,
    local_path TEXT,
    fetched_at TEXT,
    status TEXT
);

CREATE TABLE IF NOT EXISTS companies (
    ID TEXT PRIMARY KEY,
    TITLE TEXT,
    COMPANY_TYPE TEXT,
    INDUSTRY TEXT,
    REVENUE TEXT,
    EMAIL TEXT,
    PHONE TEXT,
    DATE_MODIFY TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    ID TEXT PRIMARY KEY,
    NAME TEXT,
    LAST_NAME TEXT,
    NAME_LAST TEXT,
    COMPANY_ID TEXT,
    COMPANY_TITLE TEXT,
    EMAIL TEXT,
    PHONE TEXT,
    DATE_MODIFY TEXT
);

CREATE TABLE IF NOT EXISTS kb_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def deal_cols_sql():
    cols = [f'"{f}" TEXT' for f in DEAL_FIELDS if f != "ID"]
    return ", ".join(cols)


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)


def rebuild(conn):
    conn.executescript("DROP TABLE IF EXISTS deals;")
    conn.executescript(f"DROP TABLE IF EXISTS deal_categories;")
    conn.executescript("DROP TABLE IF EXISTS deal_stages;")
    conn.executescript("DROP TABLE IF EXISTS sources;")
    conn.executescript("DROP TABLE IF EXISTS deal_types;")
    conn.executescript("DROP TABLE IF EXISTS users;")
    conn.executescript("DROP TABLE IF EXISTS deal_files;")
    conn.executescript("DROP TABLE IF EXISTS companies;")
    conn.executescript("DROP TABLE IF EXISTS contacts;")
    conn.executescript("DROP TABLE IF EXISTS kb_meta;")
    conn.executescript(SCHEMA % {"deal_cols": deal_cols_sql()})
    conn.commit()


def ensure_schema(conn):
    conn.executescript(
        "CREATE TABLE IF NOT EXISTS deals (\n"
        f"  ID TEXT PRIMARY KEY, {deal_cols_sql()}\n);"
    )
    for name in ("deal_categories", "deal_stages", "sources", "deal_types",
                 "users", "deal_files", "companies", "contacts", "kb_meta"):
        conn.execute(f"SELECT name FROM sqlite_master WHERE name='{name}'")
    conn.commit()


def load_categories(client):
    res = client.call("crm.dealcategory.list", {}).get("result") or []
    return [(str(c.get("ID")), c.get("NAME")) for c in res]


def load_stages(client, categories):
    rows = []
    for cat_id, _cat_name in categories:
        res = client.call("crm.dealcategory.stage.list", {"id": int(cat_id)}) \
            .get("result") or []
        for s in res:
            rows.append((s.get("STATUS_ID"), cat_id,
                         s.get("NAME"), s.get("SEMANTIC_ID")))
    return rows


def load_status(client, entity_id):
    res = client.call("crm.status.list",
                      {"filter": {"ENTITY_ID": entity_id}, "limit": 500}) \
        .get("result") or []
    return [(str(s.get("STATUS_ID")), s.get("NAME")) for s in res]


def collect_user_ids(deals):
    ids = set()
    for d in deals:
        for f in ("ASSIGNED_BY_ID", "CREATED_BY_ID", "MODIFY_BY_ID",
                  "MOVED_BY_ID", "LAST_ACTIVITY_BY"):
            v = d.get(f)
            if v:
                ids.add(str(v))
    return ids


def load_users(client, user_ids):
    ids = sorted(user_ids)
    out = {}
    # вебхук может не иметь прав на user.get -> graceful: пропускаем, не падаем
    try:
        for i in range(0, len(ids), 50):
            chunk = ids[i:i + 50]
            resp = client.call("user.get", {"ID": chunk, "limit": 50})
            for u in resp.get("result") or []:
                out[str(u.get("ID"))] = (
                    u.get("NAME"), u.get("LAST_NAME"), u.get("LOGIN"))
    except Exception as e:
        print(f"   (!) Нет прав на user.get — расшифровка пользователей "
              f"пропущена. Ошибка: {str(e)[:100]}")
    return out


def insert_ref(conn, table, rows, cols):
    if not rows:
        return
    placeholders = ", ".join(["?"] * len(cols))
    insert = f"INSERT OR IGNORE INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
    conn.executemany(insert, rows)


def load_deal_files(conn, items, deal_columns):
    """Извлекает значения file-полей сделок в таблицу deal_files."""
    rows = []
    for d in items:
        deal_id = d.get("ID")
        for fname in FILE_FIELDS:
            v = d.get(fname)
            if v in (None, "", [], {}):
                continue
            if isinstance(v, list):
                vals = v
            else:
                vals = [v]
            for fv in vals:
                if isinstance(fv, dict):
                    file_id = fv.get("id") or fv.get("fileId")
                    file_name = fv.get("name") or fv.get("filename")
                    file_url = fv.get("url") or fv.get("linkUrl") or fv.get("downloadUrl")
                    status = "ok" if (file_url or file_name) else "no_url"
                else:
                    file_id = str(fv)
                    file_name = None
                    file_url = None
                    status = "id_only"
                rows.append((deal_id, fname, str(file_id) if file_id else None,
                             file_name, file_url, None, None, status))
    if rows:
        conn.executemany(
            "INSERT INTO deal_files (deal_id, field_name, file_id, file_name, "
            "file_url, local_path, fetched_at, status) "
            "VALUES (?,?,?,?,?,?,?,?)", rows)
        conn.commit()
    return len(rows)


def load_deals(client, conn, max_deals=None, progress_every=10,
               since_date_modify=None, collect_files=True,
               resume_offset=0, save_offset_cb=None):
    deal_columns = ["ID"] + [f for f in DEAL_FIELDS if f != "ID"]
    insert_sql = (f"INSERT OR IGNORE INTO deals ({', '.join(deal_columns)}) "
                  f"VALUES ({', '.join('?' * len(deal_columns))})")
    update_sql = (f"UPDATE deals SET "
                  f"{', '.join(f'{c}=?' for c in deal_columns if c != 'ID')} "
                  f"WHERE ID=?")
    select = DEAL_FIELDS[:]
    file_queried = False
    if collect_files:
        try:
            probe = client.call("crm.deal.list",
                                {"limit": 1, "select": [FILE_FIELDS[0], "ID"]})
            if FILE_FIELDS[0] in (probe.get("result") or [{}])[0]:
                select += FILE_FIELDS
                file_queried = True
        except Exception:
            file_queried = False

    params = {}
    if since_date_modify:
        params[">DATE_MODIFY"] = since_date_modify

    inserted = updated = 0
    files_total = 0
    page = 0
    buffer = []

    def flush():
        nonlocal inserted, updated
        ids = [row[0] for row in buffer]
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        existing = {r[0] for r in conn.execute(
            f"SELECT ID FROM deals WHERE ID IN ({placeholders})", ids)}
        for row in buffer:
            if row[0] in existing:
                conn.execute(update_sql, (*row[1:], row[0]))
                updated += 1
            else:
                inserted += 1
        conn.executemany(insert_sql, buffer)
        conn.commit()
        buffer.clear()

    def on_progress(fetched, total):
        nonlocal page
        page += 1
        cur_offset = resume_offset + fetched
        if save_offset_cb and (page == 1 or page % progress_every == 0):
            save_offset_cb(cur_offset)
        if page % progress_every == 0:
            print(f"   ... получено {cur_offset} / {total} сделок", flush=True)

    for items, total in client.paged_gentle(
            "crm.deal.list", params, step=50, max_deals=max_deals,
            on_progress=on_progress, select=select,
            start_offset=resume_offset):
        for d in items:
            row = tuple(d.get(f) or None for f in deal_columns)
            buffer.append(row)
            if len(buffer) >= 500:
                flush()
        if file_queried:
            files_total += load_deal_files(conn, items, deal_columns)
    if buffer:
        flush()
    return inserted, updated, files_total


def build_indexes(conn):
    for col in ("CATEGORY_ID", "STAGE_ID", "ASSIGNED_BY_ID", "DATE_CREATE",
                "TITLE"):
        try:
            conn.execute(f"CREATE INDEX IF NOT EXISTS idx_deals_{col} "
                         f"ON deals ({col})")
        except Exception as e:
            print(f"  (индекс {col}: {e})")
    conn.commit()


def main():
    ap = argparse.ArgumentParser(description="Сборка/пополнение KB-базы сделок b24")
    ap.add_argument("--max-deals", type=int, default=None,
                    help="Абсолютная цель по числу сделок (кумулятивный offset). "
                         "Возобновление берёт от текущего прогресса до цели.")
    ap.add_argument("--rebuild", action="store_true",
                    help="Пересоздать схему с нуля (разово)")
    ap.add_argument("--update", action="store_true",
                    help="Инкрементальный режим: догрузить только изменённые "
                         "после last_date_modify сделки (для регулярного пополнения)")
    args = ap.parse_args()

    client = B24Client()
    conn = connect()

    if args.rebuild:
        print("Пересоздание схемы БД...")
        rebuild(conn)
        resume_offset = 0
        since_date_modify = None
    else:
        ensure_schema(conn)
        row = conn.execute(
            "SELECT value FROM kb_meta WHERE key='last_offset'"
        ).fetchone()
        resume_offset = int(row[0]) if row and row[0] else 0
        row = conn.execute(
            "SELECT value FROM kb_meta WHERE key='last_date_modify'"
        ).fetchone()
        last_date_modify = row[0] if row else None
        # режим: --update => инкремент по DATE_MODIFY; иначе resume-by-offset
        since_date_modify = last_date_modify if args.update else None
        if args.update:
            resume_offset = 0

    # сколько добрать за этот запуск (абсолютный целевой offset)
    fetch_target = args.max_deals
    if fetch_target is not None and fetch_target <= resume_offset:
        fetch_target = None
    run_max = (fetch_target - resume_offset) if fetch_target is not None else None

    print("Загрузка справочников...")
    categories = load_categories(client)
    insert_ref(conn, "deal_categories", categories, ["ID", "NAME"])
    stages = load_stages(client, categories)
    insert_ref(conn, "deal_stages", stages,
               ["STATUS_ID", "CATEGORY_ID", "NAME", "SEMANTIC_ID"])
    insert_ref(conn, "sources", load_status(client, "SOURCE"), ["ID", "NAME"])
    insert_ref(conn, "deal_types", load_status(client, "DEAL_TYPE"),
               ["ID", "NAME"])
    conn.commit()
    print(f"   категорий: {len(categories)}, стадий: {len(stages)}")
    print(f"   предыдущий прогресс: {resume_offset} сделок")

    def save_offset(cur):
        conn.execute(
            "INSERT OR REPLACE INTO kb_meta (key, value) VALUES ('last_offset', ?)",
            (str(cur),))
        conn.commit()

    if resume_offset and not args.rebuild:
        print(f"Режим возобновления с offset={resume_offset}...")
    elif since_date_modify:
        print(f"Инкрементальный режим: сделки изменённые после "
              f"{since_date_modify}...")
    else:
        print("Выгрузка сделок (щадящий режим)...")
    t0 = time.time()
    inserted, updated, files_total = load_deals(
        client, conn, max_deals=run_max,
        since_date_modify=since_date_modify,
        resume_offset=resume_offset, save_offset_cb=save_offset)
    print(f"   сделок: вставлено {inserted}, обновлено {updated}, "
          f"файлов: {files_total}, за {time.time()-t0:.1f} с", flush=True)

    if inserted or updated:
        max_dm = conn.execute(
            "SELECT MAX(DATE_MODIFY) FROM deals").fetchone()[0]
        if max_dm:
            conn.execute(
                "INSERT OR REPLACE INTO kb_meta (key, value) "
                "VALUES ('last_date_modify', ?)", (max_dm,))
            conn.commit()

    print("Загрузка пользователей...")
    all_deals = conn.execute("SELECT ID, ASSIGNED_BY_ID, CREATED_BY_ID, "
                             "MODIFY_BY_ID, MOVED_BY_ID, LAST_ACTIVITY_BY "
                             "FROM deals").fetchall()
    ids = set()
    for row in all_deals:
        for v in row[1:]:
            if v:
                ids.add(v)
    users = load_users(client, ids)
    insert_ref(conn, "users", [(k, v[0], v[1], v[2]) for k, v in users.items()],
               ["ID", "NAME", "LAST_NAME", "LOGIN"])
    # если прав на user.get нет, добавляем хотя бы самого пользователя (profile)
    if not users:
        try:
            prof = client.call("profile").get("result", {})
            prof_id = str(prof.get("ID"))
            insert_ref(conn, "users",
                       [(prof_id, prof.get("NAME"), prof.get("LAST_NAME"),
                         prof.get("LOGIN"))],
                       ["ID", "NAME", "LAST_NAME", "LOGIN"])
            print("   добавлен профиль текущего пользователя (ID "
                  f"{prof_id}) из profile")
        except Exception as e:
            print(f"   (!) profile недоступен: {str(e)[:80]}")
    conn.commit()
    if users:
        print(f"   пользователей: {len(users)}")
    else:
        print("   пользователей: недоступно (нет прав) — сохранены только ID")

    print("Создание индексов...")
    build_indexes(conn)

    count = conn.execute("SELECT COUNT(*) FROM deals").fetchone()[0]
    files = conn.execute("SELECT COUNT(*) FROM deal_files").fetchone()[0]
    conn.execute("INSERT OR REPLACE INTO kb_meta (key, value) VALUES ('deal_count', ?)",
                 (str(count),))
    conn.commit()
    print(f"Готово. Всего сделок в БД: {count}, файлов в deal_files: {files}")
    conn.close()


if __name__ == "__main__":
    main()
