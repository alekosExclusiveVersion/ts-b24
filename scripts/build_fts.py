import argparse
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"

FTS_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS deals_fts USING fts5(
    deal_id UNINDEXED,
    title,
    comments,
    company_title,
    category_id UNINDEXED,
    stage_id UNINDEXED,
    assigned_by_id UNINDEXED,
    date_create UNINDEXED,
    stage_semantic UNINDEXED
);
"""


def connect():
    return sqlite3.connect(DB_PATH)


def rebuild(conn):
    conn.execute("DROP TABLE IF EXISTS deals_fts")
    conn.executescript(FTS_SCHEMA)
    conn.commit()
    print("deals_fts создана")


def fill(conn, batch=500):
    # собираем данные для индекса: title, comments, название компании
    rows = conn.execute("""
        SELECT d.ID, COALESCE(d.TITLE,''), COALESCE(d.COMMENTS,''),
               COALESCE(c.TITLE,''), d.CATEGORY_ID, d.STAGE_ID,
               d.ASSIGNED_BY_ID, d.DATE_CREATE, d.STAGE_SEMANTIC_ID
        FROM deals d
        LEFT JOIN companies c ON c.ID = d.COMPANY_ID
    """)
    buf = []
    t0 = time.time()
    n = 0
    for r in rows:
        buf.append(r)
        if len(buf) >= batch:
            conn.executemany(
                "INSERT INTO deals_fts (deal_id,title,comments,company_title,"
                "category_id,stage_id,assigned_by_id,date_create,stage_semantic) "
                "VALUES (?,?,?,?,?,?,?,?,?)", buf)
            n += len(buf)
            buf.clear()
    if buf:
        conn.executemany(
            "INSERT INTO deals_fts (deal_id,title,comments,company_title,"
            "category_id,stage_id,assigned_by_id,date_create,stage_semantic) "
            "VALUES (?,?,?,?,?,?,?,?,?)", buf)
        n += len(buf)
    conn.commit()
    print(f"В FTS проиндексировано: {n} сделок за {time.time()-t0:.1f}с")


def main():
    ap = argparse.ArgumentParser(description="Построение FTS5-индекса по сделкам")
    ap.add_argument("--rebuild", action="store_true",
                    help="Пересоздать индекс с нуля")
    args = ap.parse_args()

    conn = connect()
    if args.rebuild:
        rebuild(conn)
        fill(conn)
    else:
        # дополняем недостающее
        fill(conn)
    count = conn.execute("SELECT COUNT(*) FROM deals_fts").fetchone()[0]
    print(f"Итого записей в deals_fts: {count}")
    conn.close()


if __name__ == "__main__":
    main()
