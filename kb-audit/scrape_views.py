#!/usr/bin/env python3
"""Сбор счётчиков просмотров статей БЗ (landing-pub-top-panel).

Счётчик рендерится сервером в HTML публичной страницы статьи, поэтому
забираем её прямо из браузерной сессии (cookie + sessid портала) и парсим:
    .landing-pub-top-panel-total-view   — всего просмотров
    .landing-pub-top-panel-unique-view  — уникальных посетителей

Результат: kb-audit/views.json + таблица в stdout (топ по просмотрам).
"""
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "views.json"
BATCH = 8
JSFILE = Path("/tmp/kb_views.applescript")

URL = "/knowledge/techsupservice/{code}/?bitrix_include_areas=Y&IFRAME=Y&IFRAME_TYPE=SIDE_SLIDER"


def run_osascript(applescript: str):
    JSFILE.write_text(applescript, encoding="utf-8")
    r = subprocess.run(
        ["/usr/bin/osascript", str(JSFILE)], capture_output=True, text=True, timeout=180
    )
    return (r.stdout or "").strip(), (r.stderr or "").strip()


def make_applescript(js: str) -> str:
    js = js.replace("\\", "\\\\").replace('"', '\\"')
    return (
        'tell application "Safari"\n'
        f'  do JavaScript "{js}" in front document\n'
        "end tell\n"
    )


def start_batch(codes):
    arr = "[" + ",".join("'" + c + "'" for c in codes) + "]"
    js = (
        "(function(){var codes=" + arr + ";window.__v=window.__v||{};window.__vdone=0;var i=0;"
        "function step(){if(i>=codes.length){window.__vdone=1;return}"
        "var c=codes[i++];"
        "fetch('/knowledge/techsupservice/'+c+'/?bitrix_include_areas=Y&IFRAME=Y&IFRAME_TYPE=SIDE_SLIDER',"
        "{credentials:'same-origin'}).then(function(r){return r.text()}).then(function(h){"
        "var d=new DOMParser().parseFromString(h,'text/html');"
        "var t=d.querySelector('.landing-pub-top-panel-total-view');"
        "var u=d.querySelector('.landing-pub-top-panel-unique-view');"
        "function num(el){if(!el)return null;var k=el.querySelectorAll('div');"
        "for(var j=0;j<k.length;j++){var s=(k[j].textContent||'').trim();"
        "if(/^[0-9 ]+$/.test(s)&&s.length){return parseInt(s.replace(/[^0-9]/g,''),10)}}return null}"
        "window.__v[c]=[num(t),num(u)];step()}).catch(function(e){window.__v[c]=['ERR',null];step()})}"
        "step();return 'started'})()"
    )
    return make_applescript(js)


def read_result():
    js = "JSON.stringify([window.__vdone||0,window.__v||{}])"
    return run_osascript(make_applescript(js))


def main():
    articles = json.load(open(HERE / "articles.json", encoding="utf-8"))
    codes = [a["code"] for a in articles]
    views = {}
    if OUT.exists() and "--fresh" not in sys.argv:
        views = json.load(open(OUT, encoding="utf-8"))
    todo = [c for c in codes if c not in views]
    print(f"к опросу: {len(todo)} из {len(codes)}")

    for i in range(0, len(todo), BATCH):
        chunk = todo[i : i + BATCH]
        run_osascript(make_applescript("window.__v={};window.__vdone=0;'reset'"))
        run_osascript(start_batch(chunk))
        for _ in range(40):
            time.sleep(1.5)
            out, err = read_result()
            if not out:
                continue
            try:
                data = json.loads(out)
            except json.JSONDecodeError:
                continue
            done, got = data[0], data[1]
            if done:
                views.update({k: v for k, v in got.items()})
                break
        json.dump(views, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"  собрано {len(views)}/{len(codes)}", file=sys.stderr)

    json.dump(views, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    rows = []
    for a in articles:
        v = views.get(a["code"]) or [None, None]
        rows.append((v[0] or 0, v[1] or 0, a["code"], a["title"]))
    rows.sort(reverse=True)
    print(f"\n{'всего':>6} {'уник':>6}  код / статья")
    for total, uniq, code, title in rows[:30]:
        print(f"{total:>6} {uniq:>6}  {code[:40]:<40} {title[:44]}")
    print(f"\nстатей без счётчика: {sum(1 for r in rows if r[0] == 0)} из {len(rows)}")
    print("файл:", OUT)


if __name__ == "__main__":
    main()
