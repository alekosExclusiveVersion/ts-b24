#!/usr/bin/env python3
"""Сводка по использованию статей БЗ: просмотры + упоминания в чате.

Вход:  kb-audit/views.json          (счётчики landing-pub-top-panel)
       kb-audit/chat-mentions.json  (упоминания ссылок в чате 920)
       kb-audit/articles.json       (метаданные 94 статей)
Выход: kb-audit/2026-10-19-usage.md
"""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "2026-10-19-usage.md"

V = json.load(open(HERE / "views.json", encoding="utf-8"))
A = {a["code"]: a for a in json.load(open(HERE / "articles.json", encoding="utf-8"))}
M = {r["code"]: r for r in json.load(open(HERE / "chat-mentions.json", encoding="utf-8"))}

codes = list(A)


def stat(c):
    v = V.get(c) or [0, 0]
    m = M.get(c) or {}
    return (v[0] or 0, v[1] or 0, m.get("weight", 0), m.get("w2026", 0), m.get("w2025", 0), m.get("last", ""))


rt = {c: i for i, c in enumerate(sorted(codes, key=lambda c: -stat(c)[0]), 1)}
ru = {c: i for i, c in enumerate(sorted(codes, key=lambda c: -stat(c)[1]), 1)}
rc = {c: i for i, c in enumerate(sorted(codes, key=lambda c: -stat(c)[2]), 1)}
rows = sorted(codes, key=lambda c: (rt[c] + ru[c] + rc[c], -stat(c)[0]))

L = []
L.append("# Использование статей БЗ: просмотры и упоминания в чате")
L.append("")
L.append("Дата: 2026-10-19. Источник данных — портал Битрикс24 (счётчик `landing-pub-top-panel`)")
L.append("и история чата «ЧАТ СП» (chat920).")
L.append("")
L.append("## Как считали")
L.append("")
L.append("- **Просмотры.** На публичной странице статьи отображается панель `.landing-pub-top-panel`:")
L.append("  `.landing-pub-top-panel-total-view` (всего открытий) и `.landing-pub-top-panel-unique-view`")
L.append("  (уникальных посетителей). Счётчик приходит в HTML сервером; собран по всем 94 статьям")
L.append("  (`views.json`). Значения накопительные — с момента создания статьи, даты создания в БЗ 1.0 нет.")
L.append("- **Упоминания в чате.** Поиск по chat920 ссылок вида `/knowledge/techsupservice/<код>/` и")
L.append("  `/knowledge/baza_tp/<код>/` (старый адрес 2024 г.). Исключены: закреплённое меню (#20341631),")
L.append("  сообщения-«меню» (5+ ссылок на БЗ), сообщения ботов. Вес = 3×(упоминания 2026) + 1×(2025).")
L.append("- **Сводный рейтинг** — сумма мест по трём метрикам (всего / уникальные / вес в чате).")
L.append("")
L.append("## Сводный топ-20")
L.append("")
L.append("| сумма мест | просмотры | уник. | вес чата | 2026 | 2025 | статья |")
L.append("|---|---|---|---|---|---|---|")
for c in rows[:20]:
    t, u, w, y26, y25, _ = stat(c)
    L.append(f"| {rt[c]+ru[c]+rc[c]} | {t} | {u} | {w} | {y26} | {y25} | [{A[c]['title']}](https://b24.tradesoft.ru/knowledge/techsupservice/{c}/) |")
L.append("")
L.append("## Топ-15 по просмотрам")
L.append("")
L.append("| просмотры | уник. | код | статья |")
L.append("|---|---|---|---|")
for c in sorted(codes, key=lambda c: -stat(c)[0])[:15]:
    t, u, *_ = stat(c)
    L.append(f"| {t} | {u} | `{c}` | {A[c]['title']} |")
L.append("")
L.append("## Топ-15 по упоминаниям в чате (вес)")
L.append("")
L.append("| вес | 2026 | 2025 | последнее | статья |")
L.append("|---|---|---|---|---|")
for c in sorted(codes, key=lambda c: -stat(c)[2])[:15]:
    _, _, w, y26, y25, last = stat(c)
    if w == 0:
        continue
    L.append(f"| {w} | {y26} | {y25} | {last} | {A[c]['title']} |")
L.append("")
L.append("## Текущий блок «Самое нужное» в меню и его метрики")
L.append("")
L.append("| статья | просмотры | уник. | вес чата |")
L.append("|---|---|---|---|")
for c in [
    "partscatalogs",
    "exportTo1C",
    "Parts.Index_сatalogs",
    "autoinstaller_mssql_server",
    "setting_network_receipts_printing_service",
    "calls_chats",
]:
    t, u, w, *_ = stat(c)
    L.append(f"| {A[c]['title']} | {t} | {u} | {w} |")
L.append("")
L.append("## Ограничения")
L.append("")
L.append("- Просмотры накопительные и не разбиты по времени: старые статьи заведомо впереди. Разбивку")
L.append("  по датам портал не отдаёт (попап «Просмотры» подгружается лениво и пуст без доп. запроса).")
L.append("- Упоминания в чате видны только по тем сообщениям, которые находит поиск; «хвост» истории")
L.append("  и удалённые сообщения не учитываются.")
L.append("- Счётчик считает открытия, а не полезность: статья-«заглушка» с частыми переходами из меню")
L.append("  может обгонять большую инструкцию.")
L.append("")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
print("записано:", OUT)
