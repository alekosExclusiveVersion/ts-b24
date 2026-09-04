#!/usr/bin/env python3
"""Загрузка «переписок» по сделкам b24 (комментарии ленты + активности) в БД.

Источники (REST-вебхук):
  - crm.timeline.comment.list  — комментарии в ленте сделки (переписка)
  - crm.activity.list          — активности: звонки, письма, встречи, заметки

Обрабатываются только сделки, изменённые/созданные за последние N дней
(по умолчанию 365). Инкрементальный запуск (--since-days) добавляет сделки,
появившиеся с прошлого запуска. Прогресс хранится в kb_meta
(timeline_deal_offset — количество сделок, по которым переписки уже загружены).

Используется batch-API b24 (несколько команд за один HTTP-запрос), чтобы
щадить портал и не упираться в лимиты запросов.
"""

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import B24Client, PROJECT_ROOT, _RetryableError

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"

ACTIVITY_FIELDS = [
    "ID", "OWNER_ID", "OWNER_TYPE_ID", "TYPE_ID", "SUBJECT", "DESCRIPTION",
    "DESCRIPTION_TYPE", "START_TIME", "END_TIME", "COMPLETED", "DIRECTION",
    "PROVIDER_ID", "PROVIDER_TYPE_ID", "PROVIDER_DATA", "AUTHOR_ID",
    "RESPONSIBLE_ID", "CREATED", "DEADLINE", "STATUS",
]

COMMENT_FIELDS = ["ID", "ENTITY_ID", "ENTITY_TYPE", "CREATED", "COMMENT",
                 "AUTHOR_ID"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS deal_comments (
    id TEXT PRIMARY KEY,
    deal_id TEXT,
    created TEXT,
    comment TEXT,
    author_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_comments_deal ON deal_comments(deal_id);

CREATE TABLE IF NOT EXISTS deal_activities (
    id TEXT PRIMARY KEY,
    deal_id TEXT,
    type_id TEXT,
    subject TEXT,
    description TEXT,
    description_type TEXT,
    start_time TEXT,
    end_time TEXT,
    completed TEXT,
    direction TEXT,
    provider_id TEXT,
    provider_type_id TEXT,
    provider_data TEXT,
    author_id TEXT,
    responsible_id TEXT,
    created TEXT,
    deadline TEXT,
    status TEXT
);
CREATE INDEX IF NOT EXISTS idx_activities_deal ON deal_activities(deal_id);
CREATE INDEX IF NOT EXISTS idx_activities_created ON deal_activities(created);
"""


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _since_days_to_filter(since_days):
    dt = datetime.now() - timedelta(days=since_days)
    return dt.strftime("%Y-%m-%dT00:00:00")


def fetch_deal_ids(conn, since_days, offset, limit):
    since = _since_days_to_filter(since_days)
    rows = conn.execute(
        "SELECT ID FROM deals WHERE DATE_CREATE >= ? "
        "ORDER BY DATE_CREATE, ID LIMIT ? OFFSET ?",
        (since, limit, offset)).fetchall()
    return [r[0] for r in rows]


def fetch_deal_ids_last_modify(conn, since_days, offset, limit):
    since = _since_days_to_filter(since_days)
    rows = conn.execute(
        "SELECT ID FROM deals WHERE DATE_MODIFY >= ? "
        "ORDER BY DATE_MODIFY, ID LIMIT ? OFFSET ?",
        (since, limit, offset)).fetchall()
    return [r[0] for r in rows]


def build_batch_cmds(deal_ids):
    """Формирует batch-команды: для каждой сделки comment.list + activity.list."""
    cmds = {}
    for i, did in enumerate(deal_ids):
        cmds[f"c{i}"] = (
            "crm.timeline.comment.list?filter[ENTITY_TYPE]=deal"
            f"&filter[ENTITY_ID]={did}&order[CREATED]=asc")
        cmds[f"a{i}"] = (
            "crm.activity.list?filter[OWNER_TYPE_ID]=2"
            f"&filter[OWNER_ID]={did}"
            + "".join(f"&select[]={f}" for f in ACTIVITY_FIELDS)
            + "&order[START_TIME]=asc")
    return cmds


def upsert_comments(conn, deal_id, items):
    if not items:
        return 0
    rows = [(
        str(i.get("ID")), deal_id, i.get("CREATED"), i.get("COMMENT"),
        str(i.get("AUTHOR_ID")) if i.get("AUTHOR_ID") is not None else None
    ) for i in items]
    conn.executemany(
        "INSERT OR REPLACE INTO deal_comments "
        "(id, deal_id, created, comment, author_id) VALUES (?,?,?,?,?)", rows)
    return len(rows)


def upsert_activities(conn, deal_id, items):
    if not items:
        return 0
    rows = [(
        str(i.get("ID")), deal_id, str(i.get("TYPE_ID")) if i.get("TYPE_ID") else None,
        i.get("SUBJECT"), i.get("DESCRIPTION"), i.get("DESCRIPTION_TYPE"),
        i.get("START_TIME"), i.get("END_TIME"), i.get("COMPLETED"),
        str(i.get("DIRECTION")) if i.get("DIRECTION") is not None else None,
        i.get("PROVIDER_ID"), i.get("PROVIDER_TYPE_ID"),
        i.get("PROVIDER_DATA"), str(i.get("AUTHOR_ID")) if i.get("AUTHOR_ID") else None,
        str(i.get("RESPONSIBLE_ID")) if i.get("RESPONSIBLE_ID") else None,
        i.get("CREATED"), i.get("DEADLINE"), i.get("STATUS")
    ) for i in items]
    conn.executemany(
        "INSERT OR REPLACE INTO deal_activities "
        "(id, deal_id, type_id, subject, description, description_type, "
        "start_time, end_time, completed, direction, provider_id, "
        "provider_type_id, provider_data, author_id, responsible_id, "
        "created, deadline, status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(
        description="Загрузка переписок (комментарии + активности) по сделкам b24")
    ap.add_argument("--since-days", type=int, default=365,
                    help="Обрабатывать сделки, созданные за последние N дней")
    ap.add_argument("--by-modify", action="store_true",
                    help="Отбирать сделки по DATE_MODIFY (а не DATE_CREATE)")
    ap.add_argument("--deals-per-batch", type=int, default=5,
                    help="Сделок за один batch-запрос (команд = 2x сделок)")
    ap.add_argument("--max-deals", type=int, default=None,
                    help="Ограничить общее число обработанных сделок за запуск")
    ap.add_argument("--reset", action="store_true",
                    help="Сбросить прогресс и начать заново")
    args = ap.parse_args()

    client = B24Client()
    conn = connect()

    since = _since_days_to_filter(args.since_days)
    if args.by_modify:
        total = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE DATE_MODIFY >= ?",
            (since,)).fetchone()[0]
        mode = "DATE_MODIFY"
        id_sel = fetch_deal_ids_last_modify
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE DATE_CREATE >= ?",
            (since,)).fetchone()[0]
        mode = "DATE_CREATE"
        id_sel = fetch_deal_ids

    if args.reset:
        conn.execute("DELETE FROM kb_meta WHERE key='timeline_deal_offset'")
        conn.commit()
    row = conn.execute(
        "SELECT value FROM kb_meta WHERE key='timeline_deal_offset'").fetchone()
    offset = int(row[0]) if row and row[0] else 0
    if args.max_deals is not None:
        total = min(total, offset + args.max_deals)
    print(f"Сделок за последние {args.since_days} дн (по {mode}): {total}")
    print(f"Начинаю с offset={offset}")

    t0 = time.time()
    processed = 0
    n_comments = 0
    n_acts = 0
    batch = args.deals_per_batch

    def save_offset(val):
        conn.execute(
            "INSERT OR REPLACE INTO kb_meta (key, value) "
            "VALUES ('timeline_deal_offset', ?)", (str(val),))
        conn.commit()

    while True:
        if offset >= total:
            break
        deal_ids = id_sel(conn, args.since_days, offset, batch)
        if not deal_ids:
            break
        cmds = build_batch_cmds(deal_ids)
        ok = False
        try:
            resp = client.batch(cmds)
            ok = True
        except (_RetryableError, Exception) as e:
            print(f"  batch offset={offset} ошибка: {str(e)[:150]} "
                  f"— повтор через 2с", flush=True)
            time.sleep(2)
        if ok:
            for i, did in enumerate(deal_ids):
                comments = resp.get(f"c{i}") or []
                acts = resp.get(f"a{i}") or []
                n_comments += upsert_comments(conn, did, comments)
                n_acts += upsert_activities(conn, did, acts)
            conn.commit()
            processed += len(deal_ids)
            offset += len(deal_ids)
            save_offset(offset)
            if processed == 0 or processed % (batch * 40) == 0:
                el = time.time() - t0
                print(f"  ... обработано {offset} / {total} сделок "
                      f"(комментарии {n_comments}, активности {n_acts}) "
                      f"за {el:.0f}с", flush=True)
        # щадящая пауза между batch-запросами
        time.sleep(0.5)

    el = time.time() - t0
    print(f"Готово. Обработано сделок: {processed}. "
          f"Комментариев: {n_comments}, активностей: {n_acts}. За {el:.0f}с")
    conn.close()


if __name__ == "__main__":
    main()
