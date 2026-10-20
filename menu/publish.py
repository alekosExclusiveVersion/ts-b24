#!/usr/bin/env python3
"""Публикация меню БЗ в «Заметки» (диалог 176) через вебхук ts-b24.

Читает out/chat920.bb.txt + out/chat920.keyboard.json + out/chat920.menu.json.
Печатает id сообщения и проверяет, что оно легло в диалог.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))

from b24_client import B24Client  # noqa: E402

DIALOG = "176"  # «Заметки»
OUT = HERE / "out"


def main():
    if "--dry-run" in sys.argv:
        print("dry-run: отправка не выполняется")
        return

    text = (OUT / "chat920.bb.txt").read_text(encoding="utf-8")
    keyboard = (OUT / "chat920.keyboard.json").read_text(encoding="utf-8")
    menu = (OUT / "chat920.menu.json").read_text(encoding="utf-8")

    # publish.py update <MESSAGE_ID> — переписать существующее сообщение
    method = "im.message.add"
    params = {
        "DIALOG_ID": DIALOG,
        "MESSAGE": text,
        "KEYBOARD": keyboard,
        "MENU": menu,
        "URL_PREVIEW": "N",
    }
    if len(sys.argv) > 2 and sys.argv[1] == "update":
        method = "im.message.update"
        params.pop("DIALOG_ID")
        params["MESSAGE_ID"] = sys.argv[2]

    c = B24Client()
    r = c.call(method, params)
    if "error" in r:
        print("ОШИБКА:", r.get("error"), r.get("error_description"))
        sys.exit(1)
    res = r.get("result")
    msg_id = res.get("id") if isinstance(res, dict) else res
    print("отправлено, id:", msg_id)

    back = c.call("im.dialog.messages.get", {"DIALOG_ID": DIALOG, "MESSAGE_ID": msg_id})
    msgs = (back.get("result") or {}).get("messages") or []
    if isinstance(msgs, dict):
        msgs = list(msgs.values())
    got = [m for m in msgs if str(m.get("id")) == str(msg_id)]
    if got:
        m = got[0]
        t = (m.get("text") or "")
        print(f"проверка: сообщение найдено, длина текста {len(t)} (отправлено {len(text)}), "
              f"кнопок в params: {'keyboard' in (m.get('params') or {})}")
    else:
        print("проверка: сообщение в выдаче не найдено (но отправка вернула id)")


if __name__ == "__main__":
    main()
