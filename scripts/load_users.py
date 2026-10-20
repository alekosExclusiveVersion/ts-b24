import argparse
import html
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"
SRC = Path(__file__).resolve().parent.parent / "users.xls"


def extract_rows(path):
    s = open(path, encoding="utf-8").read()
    rows = re.findall(r"<tr>(.*?)</tr>", s, re.S)
    seen = {}
    for r in rows:
        tds = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)
        cells = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in tds]
        if len(cells) >= 6 and cells[3].isdigit():
            uid = cells[3]
            seen[uid] = {
                "FULL": cells[0],
                "DEPARTMENT": cells[1],
                "LOGIN": cells[4],
                "POSITION": cells[5],
            }
    return seen


def split_name(full):
    parts = full.split()
    last = parts[0] if parts else None
    first = parts[1] if len(parts) > 1 else None
    return last, first


def main():
    ap = argparse.ArgumentParser(description="Загрузка списка сотрудников из users.xls")
    ap.add_argument("--src", default=str(SRC))
    args = ap.parse_args()

    if not Path(args.src).exists():
        print(f"Файл не найден: {args.src}")
        sys.exit(1)

    employees = extract_rows(args.src)
    print(f"Сотрудников извлечено: {len(employees)}")

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    # расширим схему users
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)")]
    if "DEPARTMENT" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN DEPARTMENT TEXT")
    if "POSITION" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN POSITION TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_deals_assigned ON deals(ASSIGNED_BY_ID)")

    insert = ("INSERT OR IGNORE INTO users (ID, LAST_NAME, NAME, LOGIN, DEPARTMENT, POSITION) "
              "VALUES (?,?,?,?,?,?)")
    update = ("UPDATE users SET LAST_NAME=?, NAME=?, LOGIN=?, DEPARTMENT=?, POSITION=? "
              "WHERE ID=?")
    existing = {r[0] for r in conn.execute("SELECT ID FROM users")}
    added = 0
    updated = 0
    for uid in sorted(employees):
        e = employees[uid]
        last, first = split_name(e["FULL"])
        vals = (uid, last, first, e["LOGIN"], e["DEPARTMENT"], e["POSITION"])
        if uid in existing:
            conn.execute(update, (last, first, e["LOGIN"], e["DEPARTMENT"], e["POSITION"], uid))
            updated += 1
        else:
            conn.execute(insert, vals)
            added += 1
    conn.commit()
    total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    print(f"Добавлено: {added}, обновлено: {updated}, всего в users: {total}")

    # ФИО короче? покажем примеры из ТП-отдела
    print("\nПримеры (поддержка):")
    for r in conn.execute(
        "SELECT ID, LAST_NAME, NAME, LOGIN, POSITION FROM users "
        "WHERE DEPARTMENT LIKE '%технической поддержки%' ORDER BY ID LIMIT 6").fetchall():
        print("  ", r)
    conn.close()


if __name__ == "__main__":
    main()
