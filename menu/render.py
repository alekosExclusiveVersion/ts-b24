#!/usr/bin/env python3
"""Рендер меню БЗ для чата из chat920.json.

Выходы:
  out/chat920.bb.txt        — текст сообщения в BB-коде (для B24)
  out/chat920.html          — HTML-вариант (для вставки в статью БЗ)
  out/chat920.keyboard.json — кнопки под сообщением
  out/chat920.menu.json     — контекстное меню чата
  out/chat920.preview.md    — превью для чтения глазами

Проверяет, что каждый код статьи существует в БЗ (по kb-audit/articles.json).
Раскладка: каждый пункт — отдельной строкой списка.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
ARTICLES = HERE.parent / "kb-audit" / "articles.json"

BASE = "https://b24.tradesoft.ru/knowledge/techsupservice/"
BULLET = "• "


def load_cfg():
    return json.load(open(HERE / "chat920.json", encoding="utf-8"))


def known_codes():
    if not ARTICLES.exists():
        return None
    return {a["code"] for a in json.load(open(ARTICLES, encoding="utf-8"))}


def url(code):
    return BASE + code + "/"


def item_url(item):
    """Адрес пункта: либо абсолютный url (статьи из других БЗ), либо код статьи."""
    return item["url"] if item.get("url") else url(item["code"])


def bb_link(item):
    return f"[URL={item_url(item)}]{item['label']}[/URL]"


def html_link(item):
    return f'<a href="{item_url(item)}">{item["label"]}</a>'


def md_link(item):
    return f"[{item['label']}]({item_url(item)})"


def bb_list(items):
    return "\n".join(BULLET + bb_link(i) for i in items)


def html_list(items):
    return "<ul>" + "".join(f"<li>{html_link(i)}</li>" for i in items) + "</ul>"


def md_list(items):
    return "\n".join("- " + md_link(i) for i in items)


def render_bb(cfg):
    if cfg.get("compact"):
        line = f"{cfg['emoji']} [B]{cfg['title']}[/B]"
        if cfg.get("compact_link", True):
            line += f" · [URL={cfg['kb_root']}]все статьи[/URL]"
        return line

    L = [f"{cfg['emoji']} [B]{cfg['title']}[/B]", "", cfg["lead"], ""]

    hot = cfg["hot"]
    L.append(f"{hot['emoji']} [B]{hot['title']}[/B]")
    L.append(bb_list(hot["items"]))
    L.append("")

    for sec in cfg["sections"]:
        total = len({i["code"] for g in sec["groups"] for i in g["items"]})
        L.append(f"{sec['emoji']} [B]{sec['title']}[/B] · {total}")
        for g in sec["groups"]:
            if g["title"]:
                L.append(f"[B]{g['title']}[/B]")
            L.append(bb_list(g["items"]))
        L.append("")

    more = cfg["more"]
    L.append(f"{more['emoji']} [B]{more['title']}[/B]")
    L.append(bb_list(more["items"]))
    L.append("")

    L.append(f"📚 [URL={cfg['kb_root']}][B]Открыть всю базу знаний[/B][/URL]")
    L.append(cfg["footer_note"])
    return "\n".join(L)


def render_html(cfg):
    if cfg.get("compact"):
        line = f'<p>{cfg["emoji"]} <b>{cfg["title"]}</b>'
        if cfg.get("compact_link", True):
            line += f' · <a href="{cfg["kb_root"]}">все статьи</a>'
        return line + "</p>"
    L = [f"<h3>{cfg['emoji']} {cfg['title']}</h3>", f"<p>{cfg['lead']}</p>"]
    hot = cfg["hot"]
    L.append(f"<h4>{hot['emoji']} {hot['title']}</h4>" + html_list(hot["items"]))
    for sec in cfg["sections"]:
        total = len({i["code"] for g in sec["groups"] for i in g["items"]})
        L.append(f"<h4>{sec['emoji']} {sec['title']} <small>({total})</small></h4>")
        for g in sec["groups"]:
            if g["title"]:
                L.append(f"<p><b>{g['title']}</b></p>")
            L.append(html_list(g["items"]))
    more = cfg["more"]
    L.append(f"<h4>{more['emoji']} {more['title']}</h4>" + html_list(more["items"]))
    L.append(
        f'<p><a href="{cfg["kb_root"]}"><b>Открыть всю базу знаний</b></a><br>{cfg["footer_note"]}</p>'
    )
    return "\n".join(L)


def render_preview(cfg):
    if cfg.get("compact"):
        line = f"{cfg['emoji']} **{cfg['title']}**"
        if cfg.get("compact_link", True):
            line += f" · [все статьи]({cfg['kb_root']})"
        return line
    L = [f"{cfg['emoji']} **{cfg['title']}**", "", cfg["lead"], ""]
    hot = cfg["hot"]
    L.append(f"{hot['emoji']} **{hot['title']}**")
    L.append(md_list(hot["items"]))
    L.append("")
    for sec in cfg["sections"]:
        total = len({i["code"] for g in sec["groups"] for i in g["items"]})
        L.append(f"{sec['emoji']} **{sec['title']}** · {total}")
        for g in sec["groups"]:
            if g["title"]:
                L.append(f"**{g['title']}**")
            L.append(md_list(g["items"]))
        L.append("")
    more = cfg["more"]
    L.append(f"{more['emoji']} **{more['title']}**")
    L.append(md_list(more["items"]))
    L.append("")
    L.append(f"📚 [Открыть всю базу знаний]({cfg['kb_root']})")
    L.append(cfg["footer_note"])
    return "\n".join(L)


def all_items(cfg):
    yield from cfg["hot"]["items"]
    for sec in cfg["sections"]:
        for g in sec["groups"]:
            yield from g["items"]
    yield from cfg["more"]["items"]


def main():
    cfg = load_cfg()
    known = known_codes()

    problems = []
    if known is not None:
        for it in all_items(cfg):
            if it.get("url"):
                continue
            if it["code"] not in known:
                problems.append(it["code"])

    bb = render_bb(cfg)
    html = render_html(cfg)
    prev = render_preview(cfg)

    OUT.mkdir(exist_ok=True)
    (OUT / "chat920.bb.txt").write_text(bb, encoding="utf-8")
    (OUT / "chat920.html").write_text(html, encoding="utf-8")
    (OUT / "chat920.preview.md").write_text(prev, encoding="utf-8")
    (OUT / "chat920.keyboard.json").write_text(json.dumps(cfg["keyboard"], ensure_ascii=False), encoding="utf-8")
    (OUT / "chat920.menu.json").write_text(json.dumps(cfg["menu"], ensure_ascii=False), encoding="utf-8")

    uniq = {it.get("code") or it.get("url") for it in all_items(cfg)}
    ext = [it for it in all_items(cfg) if it.get("url")]
    print(f"ссылок в сообщении: {sum(1 for _ in all_items(cfg))} (уникальных статей: {len(uniq)})")
    if ext:
        print("внешние ссылки (другие БЗ): " + ", ".join(it["label"] for it in ext))
    print(f"длина BB-текста: {len(bb)} символов, строк: {bb.count(chr(10)) + 1} (лимит B24 — 20000)")
    print(f"кнопок: {sum(1 for b in cfg['keyboard'] if b.get('TEXT'))} | пунктов меню: {len(cfg['menu'])}")
    if problems:
        print("ОШИБКА: коды не найдены в БЗ:", ", ".join(sorted(set(problems))))
        sys.exit(2)
    print("валидация кодов: OK")
    print("файлы:", OUT)


if __name__ == "__main__":
    main()
