#!/usr/bin/env python3
"""Точный подсчёт упоминаний статей БЗ в чате920.

По каждому коду статьи ищутся сообщения чата со ссылкой на статью в двух
вариантах адреса: актуальном `knowledge/techsupservice/<code>/` и старом
`knowledge/baza_tp/<code>/` (старые сообщения 2024 года).

Вес:  вес = 3 * (упоминания в 2026) + 1 * (упоминания в 2025)

Служебное отбрасывается:
  * 20341631 — старое закреплённое меню (30 ссылок);
  * сообщения с 5+ ссылками на БЗ (копии меню, дайджесты);
  * сообщения от ботов/системы (author_id == 0).

Результат: kb-audit/chat-mentions.json + таблица в stdout.
"""
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
from b24_client import B24Client  # noqa: E402

CHAT_ID = 920
PINNED_MSG = "20341631"
CACHE = HERE / "chat-mentions-cache.json"
OUT = HERE / "chat-mentions.json"

PREFIXES = ("techsupservice", "baza_tp")
MENU_LIKE = 5  # сколько ссылок на БЗ делает сообщение «меню»


def load_cache():
    if CACHE.exists():
        return json.load(open(CACHE, encoding="utf-8"))
    return {}


def save_cache(c):
    json.dump(c, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)


def search_code(client, code):
    seen = {}
    for pref in PREFIXES:
        r = client.call(
            "im.dialog.messages.search",
            {"CHAT_ID": CHAT_ID, "SEARCH_MESSAGE": f"{pref}/{code}", "LIMIT": 50},
        )
        if "error" in r:
            seen[f"error:{pref}"] = r.get("error_description") or r.get("error")
            continue
        for m in (r.get("result") or {}).get("messages") or []:
            seen[str(m.get("id"))] = {
                "id": str(m.get("id")),
                "date": (m.get("date") or "")[:10],
                "author": m.get("author_id"),
                "text": m.get("text") or "",
            }
        time.sleep(0.4)
    return {"messages": list(seen.values())}


def is_mention(text, code):
    """Сообщение содержит ссылку именно на эту статью."""
    pat = r"knowledge/(?:" + "|".join(PREFIXES) + r")/" + re.escape(code) + r"(?![\w.-])"
    return re.search(pat, text) is not None


def count_links(text):
    return len(set(re.findall(r"knowledge/(?:techsupservice|baza_tp)/([\w.-]+)", text)))


def main():
    articles = json.load(open(HERE / "articles.json", encoding="utf-8"))
    codes = [a["code"] for a in articles]
    cache = load_cache()
    client = B24Client()

    for i, code in enumerate(codes, 1):
        if code in cache:
            continue
        cache[code] = search_code(client, code)
        if i % 10 == 0:
            save_cache(cache)
            print(f"  ... {i}/{len(codes)}", file=sys.stderr)
    save_cache(cache)

    rows = []
    for a in articles:
        code = a["code"]
        data = cache.get(code) or {}
        kept = []
        for m in data.get("messages") or []:
            if not m.get("id"):
                continue
            if m["id"] == PINNED_MSG:
                continue
            if (m.get("author") or 0) == 0:
                continue
            if not is_mention(m["text"], code):
                continue
            if count_links(m["text"]) >= MENU_LIKE:
                continue
            kept.append(m)
        years = Counter(m["date"][:4] for m in kept)
        weight = 3 * years.get("2026", 0) + years.get("2025", 0)
        rows.append(
            {
                "code": code,
                "title": a["title"],
                "n": len(kept),
                "w2026": years.get("2026", 0),
                "w2025": years.get("2025", 0),
                "w2024": years.get("2024", 0),
                "weight": weight,
                "first": min((m["date"] for m in kept), default=""),
                "last": max((m["date"] for m in kept), default=""),
                "authors": len({m["author"] for m in kept}),
                "in_menu": a.get("in_menu"),
                "len": a.get("len"),
                "ids": [m["id"] for m in kept],
            }
        )

    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    rows.sort(key=lambda r: (-r["weight"], -r["n"], r["last"]))
    print(f"\n{'вес':>4} {'2026':>5} {'2025':>5} {'2024':>5} {'авт':>4}  код / статья")
    for r in rows:
        if r["weight"] == 0:
            continue
        print(
            f"{r['weight']:>4} {r['w2026']:>5} {r['w2025']:>5} {r['w2024']:>5} {r['authors']:>4}  "
            f"{r['code'][:42]:<42} {r['title'][:46]}"
        )
    print(f"\nвсего статей с упоминаниями: {sum(1 for r in rows if r['n'])} из {len(rows)}")
    print("файл:", OUT)


if __name__ == "__main__":
    main()
