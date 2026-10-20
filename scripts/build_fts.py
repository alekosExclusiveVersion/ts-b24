import argparse
import sqlite3
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import PROJECT_ROOT
from sync_logger import acquire_lock, get_logger
from sync_alert import alert_completed, alert_failed

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"

_log = get_logger("fts", "sync_fts.log")

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
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


WATERMARK_KEY = "fts_last_date_modify"

FTS_SELECT = """
    SELECT d.ID, COALESCE(d.TITLE,''), COALESCE(d.COMMENTS,''),
           COALESCE(c.TITLE,''), d.CATEGORY_ID, d.STAGE_ID,
           d.ASSIGNED_BY_ID, d.DATE_CREATE, d.STAGE_SEMANTIC_ID
    FROM deals d
    LEFT JOIN companies c ON c.ID = d.COMPANY_ID
"""


def get_watermark(conn):
    row = conn.execute("SELECT value FROM kb_meta WHERE key=?",
                       (WATERMARK_KEY,)).fetchone()
    return row[0] if row else None


def set_watermark(conn, value):
    if value:
        conn.execute("INSERT OR REPLACE INTO kb_meta (key, value) VALUES (?, ?)",
                     (WATERMARK_KEY, value))
        conn.commit()


def rebuild(conn):
    conn.execute("DROP TABLE IF EXISTS deals_fts")
    conn.executescript(FTS_SCHEMA)
    conn.execute("DELETE FROM kb_meta WHERE key=?", (WATERMARK_KEY,))
    conn.commit()
    _log.info("deals_fts создана")


def fill(conn, batch=500):
    # Инкремент по watermark: переиндексируем только сделки,
    # изменённые после прошлой сборки. Без watermark — полная заливка.
    conn.executescript(FTS_SCHEMA)
    wm = get_watermark(conn)
    if wm:
        query = FTS_SELECT + "WHERE d.DATE_MODIFY > ?"
        args = (wm,)
        _log.info("Инкрементальный FTS: DATE_MODIFY > %s", wm)
    else:
        query = FTS_SELECT
        args = ()
        _log.info("Полный FTS: watermark нет, индексирую всё")
    rows = conn.execute(query, args)
    buf = []
    t0 = time.time()
    n = 0
    for r in rows:
        buf.append(r)
        if len(buf) >= batch:
            flush_buf(conn, buf)
            n += len(buf)
            buf.clear()
    if buf:
        flush_buf(conn, buf)
        n += len(buf)
    conn.commit()
    new_wm = conn.execute("SELECT MAX(DATE_MODIFY) FROM deals").fetchone()[0]
    set_watermark(conn, new_wm)
    _log.info("В FTS проиндексировано: %d сделок за %.1fс (watermark %s)",
              n, time.time() - t0, new_wm)


def flush_buf(conn, buf):
    # идемпотентность: удаляем индексируемые записи, затем вставляем заново
    ids = [r[0] for r in buf]
    placeholders = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM deals_fts WHERE deal_id IN ({placeholders})", ids)
    conn.executemany(
        "INSERT INTO deals_fts (deal_id,title,comments,company_title,"
        "category_id,stage_id,assigned_by_id,date_create,stage_semantic) "
        "VALUES (?,?,?,?,?,?,?,?,?)", buf)


def main():
    ap = argparse.ArgumentParser(description="Построение FTS5-индекса по сделкам")
    ap.add_argument("--rebuild", action="store_true",
                    help="Пересоздать индекс с нуля")
    args = ap.parse_args()

    if not acquire_lock("fts"):
        print("build_fts уже запущен, выхожу")
        return

    t_start = time.time()
    mode = "rebuild" if args.rebuild else "fill"
    _log.info("=== Запуск build_fts (mode=%s) ===", mode)

    try:
        conn = connect()
        if args.rebuild:
            rebuild(conn)
        fill(conn)
        count = conn.execute("SELECT COUNT(*) FROM deals_fts").fetchone()[0]
        _log.info("Итого записей в deals_fts: %d", count)
        conn.close()
        metrics = {
            "mode": mode,
            "status": "OK",
            "rows": count,
            "duration_sec": round(time.time() - t_start, 1),
        }
        alert_completed("fts", metrics)
        _log.info("=== Завершено за %.1fс ===", time.time() - t_start)
    except Exception as e:
        tb = traceback.format_exc()
        _log.error("Перевод прерван: %s", e)
        _log.error("%s", tb)
        alert_failed("fts", str(e), tb)
        raise


if __name__ == "__main__":
    main()
