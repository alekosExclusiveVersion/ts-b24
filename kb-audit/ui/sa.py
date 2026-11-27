"""Мини-хелпер: выполнение JS в Safari (окно 1)."""
import subprocess, time, json
from pathlib import Path

def _ap(js: str, how: str = "document of window 1") -> str:
    js = js.replace("\\", "\\\\").replace('"', '\\"')
    return f'tell application "Safari"\n  do JavaScript "{js}" in {how}\nend tell\n'

def js(code: str, wait: float = 1.5) -> str:
    p = Path("/tmp/sa_js.applescript")
    p.write_text(_ap(code), encoding="utf-8")
    r = subprocess.run(["/usr/bin/osascript", str(p)], capture_output=True, text=True)
    time.sleep(wait)
    return (r.stdout + r.stderr).strip()

def go(url: str, wait: float = 12) -> str:
    p = Path("/tmp/sa_go.applescript")
    p.write_text(f'tell application "Safari"\n  set URL of document of window 1 to "{url}"\nend tell\n', encoding="utf-8")
    subprocess.run(["/usr/bin/osascript", str(p)], capture_output=True, text=True)
    time.sleep(wait)
    return js("location.href", 0.2)

def async_js(code: str, wait: float = 8, tries: int = 20):
    """Запускает код, результат ждёт в window.__r (строка)."""
    js(code, 0.2)
    for _ in range(tries):
        time.sleep(wait / tries)
        r = js("String(window.__r)", 0.1)
        if r and r not in ("undefined", "wait"):
            return r
    return "TIMEOUT"
