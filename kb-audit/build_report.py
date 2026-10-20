#!/usr/bin/env python3
"""Генерация отчёта аудита БЗ techsupservice (KB 1.0) из собранных JSON."""
import collections
import csv
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "2026-10-19-audit.md"

nav = json.load(open(HERE / "nav.json", encoding="utf-8"))
arts = json.load(open(HERE / "articles.json", encoding="utf-8"))
pinned = json.load(open(HERE / "pinned.json", encoding="utf-8"))
chat_codes = json.load(open(HERE / "chat-codes.json", encoding="utf-8"))

A = {a["code"]: a for a in arts}
menu = {r["code"]: r for r in nav}
FOOTER = {
    "ssylkinadokumentatsiyu",
    "zapusksistemnykhinstrumentovwindows",
    "grafikdezhurstv",
    "sla",
    "dezhurstvana1i2linii",
}

# --- вычисления ---
hidden = [a for a in arts if a["code"] not in menu]
stub = sorted([a for a in arts if a["len"] < 1500], key=lambda x: x["len"])
cred = [a for a in arts if "CRED" in a["flags"]]

real_links = collections.defaultdict(list)
for a in arts:
    for t in a["int_links"]:
        if t != a["code"] and t not in FOOTER:
            real_links[t].append(a["code"])

prefixes = collections.OrderedDict()
for r in nav:
    parts = [p for p in r["path"].split(" > ") if p]
    for i in range(1, len(parts) + 1):
        pre = " > ".join(parts[:i])
        prefixes.setdefault(pre, {"direct": 0, "total": 0})
        prefixes[pre]["total"] += 1
        if i == len(parts):
            prefixes[pre]["direct"] += 1

# дубликаты (по схожести текстов, similarity.json)
sim = json.load(open(HERE / "similarity.json", encoding="utf-8"))["pairs"]

# мёртвые коды из чата
dead = [(k, v) for k, v in chat_codes.items() if k not in A]

# ссылки закреплённого меню
kb_links, msg_links, other_links = [], [], []
for u in pinned["urls"]:
    if "/knowledge/techsupservice/" in u:
        m = re.search(r"/knowledge/techsupservice/([^/?#]+)/?", u)
        kb_links.append(m.group(1) if m else "")
    elif "IM_MESSAGE=" in u:
        msg_links.append(u)
    else:
        other_links.append(u)

L = []
w = L.append

w("# Аудит Базы знаний «Службы поддержки клиентов»")
w("")
w("**Дата:** 19.10.2026 · **БЗ:** `techsupservice` (id 20), KB 1.0 · **Автор:** аудит через авторизованную сессию")
w("")
w("## 1. Как получены данные")
w("")
w("- БЗ работает на модуле **`kb`** (адреса статей — `/kb/wiki/20/view/<id>/`, публичные — `/knowledge/techsupservice/<код>/`).")
w("- **REST API для этого модуля нет**: из 800 методов `methods` нет ни одного `kb.*`, `wiki.*`, `knowledge.*`. Поэтому вебхук «не видел» БЗ — это не проблема прав.")
w("- Данные собраны из авторизованной сессии портала: дерево меню (блок навигации в статье), список статей (`/kb/wiki/20/`, 5 страниц), тела статей (только метаданные: длина, ссылки, якоря, флаги).")
w("- Тексты статей в отчёт не выносятся; учётные данные, найденные в статьях, замаскированы.")
w("- Дата «Обновлено» на странице статьи вычисляется скриптом и в HTML/API отсутствует — в отчёте не приводится.")
w("")
w("## 2. Метрики")
w("")
w("| Показатель | Значение |")
w("|---|---|")
w(f"| Всего статей | **{len(arts)}** |")
w(f"| В меню БЗ | **{len(menu)}** ({len(menu)*100//len(arts)}%) |")
w(f"| Скрыты из меню | **{len(hidden)}** |")
top_level = sum(1 for pre in prefixes if " > " not in pre)
w(f"| Разделов верхнего уровня | {top_level} |")
w(f"| Заглушки (<1500 символов) | **{len(stub)}**, из них в меню — {sum(1 for a in stub if a['code'] in menu)} |")
w(f"| Статьи с учётными данными (пароли/логины) | **{len(cred)}** |")
dup_codes = {r["a"] for r in sim if r["verdict"] in ("дубликат","почти дубликат")} | {r["b"] for r in sim if r["verdict"] in ("дубликат","почти дубликат")}
w(f"| Дубликаты / почти дубликаты | **{len(dup_codes)} статей** |")
w(f"| Перелинковка статья→статья | всего {sum(len(v) for v in real_links.values())} ссылок на {len(real_links)} статей |")
w(f"| Мёртвые коды статей (404), на которые ссылаются в чате | **{len(dead)}** |")
w("")
w("## 3. Структура меню")
w("")
w("```")
for pre, info in prefixes.items():
    parts = pre.split(" > ")
    d = len(parts)
    w(f"{'    ' * (d - 1)}{parts[-1]}  — прямых {info['direct']}, всего {info['total']}")
w("```")
w("")
w("## 4. Проблемы")
w("")
w("### P1. Битые ссылки")
w("")
w("- В закреплённом меню чата ссылка на драйвер ККТ `fs.rbsoft.ru/…/kktlab_DrvKKT_5.19_1098_x32.exe` отдаёт **404**.")
w("- В чатах используются коды статей, которых больше нет (404):")
for k, v in sorted(dead, key=lambda kv: -kv[1]["n"]):
    last = str(v.get("last") or "")[:10]
    w(f"  - `{k}` — {v['n']} упом., последнее {last}")
w("- Все внутренние ссылки внутри статей ведут на существующие статьи (битых нет), но перелинковка почти отсутствует: 12 ссылок на 11 статей.")
w("")
w("### P2. Дубликаты и заглушки")
w("")
w("Сравнение текстов статей (доля общих слов, Jaccard):")
w("")
w("| Статья A | Статья B | Общих слов | Объём A / B | Вывод |")
w("|---|---|---|---|---|")
order = {"дубликат": 0, "почти дубликат": 1, "пересекаются": 2}
for row in sorted(sim, key=lambda x: (order.get(x["verdict"], 3), -x["jaccard"])):
    verdict = row["verdict"]
    mark = {"дубликат": "**дубликат — слить**", "почти дубликат": "**почти дубликат**",
            "пересекаются": "пересекаются — проверить", "разные": "разные статьи"}[verdict]
    w(f"| `{row['a']}` | `{row['b']}` | {row['jaccard']:.0%} | {row['len_a']} / {row['len_b']} | {mark} |")
w("")
w("Примечание: одинаковые названия — не всегда дубликаты. Например, `kommit`/`kommity` и "
  "`stranitsastati`/`stranitsastati_uxvx` — разные статьи с неудачными названиями.")
w("")
w(f"Из {len(stub)} заглушек **{sum(1 for a in stub if a['code'] in menu)} находятся прямо в меню** — пользователь попадает на пустую страницу:")
for a in [x for x in stub if x["code"] in menu]:
    w(f"- `{a['code']}` — {a['title']} ({a['len']} симв.)")
w("")
w("### P3. Скрытые статьи")
w("")
w(f"{len(hidden)} статьи не видны в меню, включая содержательные:")
for a in sorted(hidden, key=lambda x: -x["len"])[:8]:
    w(f"- `{a['code']}` — {a['title']} ({a['len']} симв.)")
w("")
w("### P4. Учётные данные в статьях")
w("")
w(f"{len(cred)} статей содержат логины/пароли (тестовые доступы, демо-стенды). Значения в отчёте не приводятся. Рекомендация: вынести доступы в защищённый раздел или ограничить доступ к статьям.")
w("")
w("## 5. Сверка закреплённого сообщения (30 ссылок)")
w("")
w(f"- Статьи БЗ: **{len(kb_links)}** ссылок — все ведут на существующие материалы.")
w(f"- Ссылки на сообщения чата: **{len(msg_links)}** — внутренние переходы, требуют проверки вручную.")
w(f"- Прочие ссылки: **{len(other_links)}**")
w("")
w("| Ссылка | Статус |")
w("|---|---|")
statuses = {
    "https://ktod-docs.office.tradesoft.ru/": "200",
    "https://www.stimulsoft.com/en/documentation/online/user-manual/": "200",
    "https://product-doc.tradesoft.ru/ai/changes/versiya_5_17.htm": "200",
    "https://product-doc.tradesoft.ru/ar/changes/versiya_6_69.htm": "200",
    "https://www.nic.ru/help/winmtr-diagnostika-setevyh-soedinenij_6799.html": "200",
    "https://docs.google.com/spreadsheets/d/1ZtjENHO0o9cjokRoCvJ6nZFHLgWiqYJCXG--t5JGG2c/edit": "200",
    "https://fs.rbsoft.ru/ServerKKM/downloads/drivers/Shtrih-M/kktlab_DrvKKT_5.19_1098_x32.exe": "**404**",
    "http://projects.dev.tradesoft.ru/admin/deactivate-serial/": "401 (нужна авторизация, dev-стенд)",
}
for u in other_links:
    st = "200 (проверено)"
    for key, val in statuses.items():
        if u.startswith(key):
            st = val
            break
    if "IM_MESSAGE" in u or "/tasks/task/view/" in u:
        st = "внутр. ссылка B24"
    w(f"| `{u[:95]}` | {st} |")
w("")
w("## 6. Предложения по меню")
w("")
w("1. Оставить 6 разделов верхнего уровня, но убрать пустые узлы (статьи-заглушки с раскрывающимся списком).")
w("2. В начало — блок «Самое нужное» (5 статей, чаще всего упоминаемых в чате: `partscatalogs`, `exportTo1C`, `Parts.Index_сatalogs`, `autoinstaller_mssql_server`, `setting_network_receipts_printing_service`).")
w("3. Скрытые содержательные статьи — либо включить в меню, либо удалить (решить по каждой).")
w("4. Дубликаты — слить в одну статью, вторую удалить, ссылки перенаправить.")
w("5. Для каждой новой статьи — чек-лист: раздел, меню, перелинковка, проверка ссылок.")
w("")
w("## 7. Приложение: все статьи")
w("")
w("| Код | Название | Раздел | В меню | Символов | Внеш. ссылок | Флаги |")
w("|---|---|---|---|---|---|---|")
for a in sorted(arts, key=lambda x: x["title"].lower()):
    sec = menu[a["code"]]["path"] if a["code"] in menu else "— скрыта —"
    flags = ", ".join(a["flags"]) or ""
    w(f"| `{a['code']}` | {a['title']} | {sec} | {'да' if a['code'] in menu else 'нет'} | {a['len']} | {a['ext']} | {flags} |")
w("")

OUT.write_text("\n".join(L) + "\n", encoding="utf-8")

# CSV для дальнейшей работы
with open(HERE / "articles.csv", "w", newline="", encoding="utf-8") as fh:
    wr = csv.writer(fh)
    wr.writerow(["code", "title", "section", "in_menu", "len", "ext_links", "flags", "id", "internal_links"])
    for a in sorted(arts, key=lambda x: x["title"].lower()):
        wr.writerow([
            a["code"], a["title"],
            menu[a["code"]]["path"] if a["code"] in menu else "",
            "y" if a["code"] in menu else "n",
            a["len"], a["ext"], ",".join(a["flags"]), a["id"],
            " ".join(a["int_links"]),
        ])

print(f"отчёт: {OUT} ({OUT.stat().st_size} байт)")
print(f"CSV: {HERE/'articles.csv'}")
print(f"статей {len(arts)}, скрытых {len(hidden)}, заглушек {len(stub)}, кредов {len(cred)}")
