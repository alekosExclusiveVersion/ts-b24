import json
import os
import re
import subprocess
import sys
import ssl
import time
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import B24Client, PROJECT_ROOT
from sync_logger import get_logger

ALERT_LOG = PROJECT_ROOT / "data" / "alerts.log"

_EMOJI = {"COMPLETED": "\u2705", "FAILED": "\u274c", "WARNING": "\u26a0\ufe0f"}
_SERVICE_USER_ID = "176"

# Прямой IP Telegram API + Host-заголовок (SNI-обход), как в telegram_bot.py
TG_API_IP = os.environ.get("TG_API_IP", "149.154.167.220")

_log = get_logger("alert")


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write_fallback(text):
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(f"{_ts()} {text}\n")
    _log.warning("Alert written to fallback log %s", ALERT_LOG)


def _esc_osascript(text):
    return re.sub(r'([\\"])', r"\\\1", str(text))


def _send_macos(body, sync_type, status):
    sound = {"COMPLETED": "Glass", "FAILED": "Basso"}.get(status)
    title = f"ts-b24: {sync_type} {status}"
    subtitle = body.splitlines()[1] if body.count("\n") else body
    subtitle = subtitle[:90]
    script = (
        f'display notification "{_esc_osascript(body)}" '
        f'with title "{_esc_osascript(title)}" '
        f'subtitle "{_esc_osascript(subtitle)}"'
    )
    if sound:
        script += f' sound name "{sound}"'
    res = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(
            f"osascript rc={res.returncode}: {res.stderr.strip()[:120]}")
    return True


def _send_b24(msg):
    client = B24Client()
    client.call("im.message.add", {
        "fields": {
            "FROM_USER_ID": 0,
            "TO_USER_ID": int(_SERVICE_USER_ID),
            "MESSAGE_TYPE": "P",
            "TEXT": msg,
        }
    })
    return True


def _send_telegram(msg):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TG_ALERT_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN/TG_ALERT_CHAT_ID not set")
    payload = json.dumps({"chat_id": chat_id, "text": msg}).encode("utf-8")
    url = f"https://{TG_API_IP}/bot{token}/sendMessage"
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Host": "api.telegram.org"},
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
        resp.read()
    return True


def send_alert(sync_type, status, message, details=None):
    emoji = _EMOJI.get(status, "")
    header = f"{emoji} [{sync_type}] {status}"
    body = f"{header}\n{message}"
    if details:
        body += f"\n\n{details}"
    body += f"\n{_ts()}"

    channels = {
        "macos": lambda m: _send_macos(m, sync_type, status),
        "file": _write_fallback,
    }
    if os.environ.get("ALERT_DISABLE_B24") != "1":
        channels["b24"] = _send_b24
    if os.environ.get("TG_ALERT_CHAT_ID"):
        channels["telegram"] = _send_telegram

    sent = False
    errors = []
    for name, fn in channels.items():
        if name == "file":
            continue
        try:
            fn(body)
            _log.info("Alert delivered via %s: %s %s", name, sync_type, status)
            sent = True
            break
        except Exception as e:
            errors.append(f"{name}: {str(e)[:120]}")
            _log.warning("Alert channel %s failed: %s", name, str(e)[:120])

    if not sent and errors:
        _write_fallback(f"{body}\n(channels unavailable: {'; '.join(errors)})")


def alert_completed(sync_type, metrics):
    lines = []
    for k, v in metrics.items():
        lines.append(f"  {k}: {v}")
    details = "\n".join(lines)
    send_alert(sync_type, "COMPLETED", "Sync finished successfully", details)


def alert_failed(sync_type, error, traceback_str=None):
    details = f"Error: {error}"
    if traceback_str:
        details += f"\n\nTraceback:\n{traceback_str}"
    send_alert(sync_type, "FAILED", "Sync failed", details)


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="Отправка синх-алерта")
    ap.add_argument("--type", required=True, help="deals|timeline")
    ap.add_argument("--status", required=True,
                    choices=["COMPLETED", "FAILED", "WARNING"])
    ap.add_argument("--message", required=True)
    args = ap.parse_args()
    send_alert(args.type, args.status, args.message)


if __name__ == "__main__":
    _cli()