#!/usr/bin/env python3
"""Сбор метаданных статей БЗ techsupservice через авторизованную сессию Safari.

Данные берутся из iframe-версии статьи (?IFRAME=Y&IFRAME_TYPE=SIDE_SLIDER).
Из DOM удаляется блок навигации (ul.landing-block-node-list), затем считаются
длина текста, ссылки и якоря. Текст статей НЕ выводится.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEP = "|||"


def codes():
    import json

    lst = json.load(open(HERE / "kblist.json", encoding="utf-8"))["list"]
    return sorted(lst)


JS_TMPL = """(function(){{
var codes={codes};
window.__res='pending';
Promise.all(codes.map(function(c){{
 return fetch('/knowledge/techsupservice/'+c+'/?IFRAME=Y&IFRAME_TYPE=SIDE_SLIDER',{{redirect:'follow'}})
  .then(function(r){{return r.text().then(function(t){{
    var i=t.indexOf('<title>'),j=t.indexOf('</title>');
    var title=(i>=0&&j>i)?t.slice(i+7,j):'';
    var k=t.indexOf('/kb/wiki/20/view/'),id='';
    if(k>=0){{var s=t.slice(k+17);id=s.slice(0,s.indexOf('/'))}}
    var d=document.createElement('div');d.innerHTML=t;
    var junk=d.querySelectorAll('script,style,noscript,template');
    for(var z=junk.length-1;z>=0;z--){{junk[z].parentNode.removeChild(junk[z])}}
    var navs=d.querySelectorAll('ul.landing-block-node-list');
    for(var n=navs.length-1;n>=0;n--){{navs[n].parentNode.removeChild(navs[n])}}
    var txt=d.textContent||'';
    var links=d.querySelectorAll('a');
    var inn=[],ext=0;
    for(var n2=0;n2<links.length;n2++){{var h=links[n2].getAttribute('href')||'';
      if(h.indexOf('/knowledge/techsupservice/')>=0)inn.push(h);
      else if(h.indexOf('http')===0)ext=ext+1}}
    var u=[];inn.forEach(function(v){{var m=v.split('/knowledge/techsupservice/')[1]||'';
      m=m.split('/')[0].split('?')[0];if(m&&u.indexOf(m)<0)u.push(m)}});
    var anchors=[];var avec=d.querySelectorAll('[id]');
    for(var n3=0;n3<avec.length&&anchors.length<25;n3++){{var aid=avec[n3].id||'';
      if(aid&&aid.indexOf('bxid')<0&&anchors.indexOf(aid)<0)anchors.push(aid)}}
    var low=txt.toLowerCase();
    var flags=[];
    if(low.indexOf('парол')>=0)flags.push('CRED');
    if(low.indexOf('устарел')>=0||low.indexOf('deprecated')>=0)flags.push('OLD');
    var years=[];['2019','2020','2021','2022','2023','2024','2025','2026'].forEach(function(y){{if(txt.indexOf(y)>=0)years.push(y)}});
    return [c,r.status,title,id,txt.replace(/ +/g,' ').trim().length,u.length,ext,flags.join(','),u.join(' '),years.join(','),anchors.join(' ')].join('{sep}');
  }})}});
}})).then(function(a){{window.__res=a.join(String.fromCharCode(10))}});
return 'started';
}})()"""


def run_chunk(chunk):
    codes_js = "[" + ",".join("'" + c + "'" for c in chunk) + "]"
    js_raw = JS_TMPL.format(codes=codes_js, sep=SEP)
    js = " ".join(line.strip() for line in js_raw.splitlines() if line.strip())
    ascript = (
        'tell application "Safari"\n'
        f'  set js to "{js}"\n'
        '  do JavaScript js in front document\n'
        '  delay 9\n'
        '  return (do JavaScript "String(window.__res)" in front document)\n'
        'end tell\n'
    )
    out = subprocess.run(
        ["osascript", "-"], input=ascript, capture_output=True, text=True, timeout=180
    )
    if out.returncode != 0:
        print("osc error:", out.stderr[:300], file=sys.stderr)
    return out.stdout


def main():
    cs = codes()
    out_path = HERE / "raw-articles.txt"
    done = set()
    if out_path.exists():
        for line in open(out_path, encoding="utf-8"):
            if SEP in line:
                done.add(line.split(SEP)[0])
    todo = [c for c in cs if c not in done]
    print(f"всего статей: {len(cs)}, уже собрано: {len(done)}, осталось: {len(todo)}", flush=True)
    chunk_size = 8
    with open(out_path, "a", encoding="utf-8") as fh:
        for i in range(0, len(todo), chunk_size):
            chunk = todo[i : i + chunk_size]
            res = run_chunk(chunk)
            lines = [l for l in res.splitlines() if SEP in l]
            for l in lines:
                fh.write(l + "\n")
            fh.flush()
            print(f"  {i+len(chunk)}/{len(todo)} — получено {len(lines)}", flush=True)
    print("готово")


if __name__ == "__main__":
    main()
