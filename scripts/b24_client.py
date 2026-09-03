import json
import random
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RETRY_CODES = {
    "QUERY_LIMIT_EXCEEDED",       # 503 — перегрузка запросов
    "OPERATION_TIME_LIMIT",       # 429 — лимит ресурсоёмкости
    "OVERLOAD_LIMIT",             # 503 — ручная блокировка REST
}
RETRY_HTTP = {429, 500, 502, 503, 504}


def _is_retriable(body, http_code):
    if isinstance(body, dict):
        err = body.get("error")
        if err in RETRY_CODES:
            return True
    return http_code in RETRY_HTTP


class B24Error(Exception):
    pass


class _RetryableError(Exception):
    def __init__(self, body, http_code):
        super().__init__(body.get("error_description") or body.get("error"))
        self.body = body
        self.http_code = http_code


class B24Client:
    def __init__(self, env_file=None):
        self.base_url, self.token = self._load_config(env_file)
        self._cache = {}

    def _load_config(self, env_file):
        env_file = env_file or Path(__file__).resolve().parent.parent / ".env"
        env = {}
        if Path(env_file).exists():
            for line in Path(env_file).read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
        base = env.get(
            "B24_BASE_URL", "https://b24.tradesoft.ru/rest/176/"
        )
        token = env.get("B24_WEBHOOK_TOKEN", "")
        if not token:
            raise B24Error("B24_WEBHOOK_TOKEN не найден в .env")
        return base.rstrip("/") + "/", token

    def call(self, method, params=None):
        url = f"{self.base_url}{self.token}/{method}"
        data = json.dumps(params or {}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            http_code = e.code
            try:
                body = json.loads(e.read().decode("utf-8"))
            except Exception:
                body = {"error": "HTTP", "error_description": e.reason}
            if _is_retriable(body, http_code):
                raise _RetryableError(body, http_code)
            if "error" in body:
                raise B24Error(
                    f"{body.get('error')}: {body.get('error_description')}"
                )
            raise B24Error(f"HTTP {e.code}: {e.reason}")
        except urllib.error.URLError as e:
            raise _RetryableError(
                {"error": "NETWORK", "error_description": str(e.reason)}, 0
            )

    def call_gentle(self, method, params=None, pause=0.4, jitter=(0.3, 0.8),
                    max_wait=60):
        wait = pause
        attempt = 0
        while True:
            if attempt == 0:
                if jitter:
                    time.sleep(pause + random.uniform(*jitter))
            try:
                body = self.call(method, params)
                break
            except _RetryableError as e:
                attempt += 1
                if attempt > 8:
                    raise B24Error(
                        f"Слишком много повторов: "
                        f"{e.body.get('error_description') or e.body.get('error')}"
                    )
                wait = min(wait * 2, max_wait)
                time.sleep(wait)
        if "error" in body:
            raise B24Error(
                f"{body.get('error')}: {body.get('error_description')}"
            )
        return body

    def paged_gentle(self, method, params=None, step=50, pause=0.4,
                     jitter=(0.3, 0.8), max_wait=60, max_deals=None,
                     on_progress=None, select=None, start_offset=0):
        params = dict(params or {})
        if select:
            params["select"] = select
        offset = start_offset
        total = None
        fetched = 0
        while True:
            if max_deals is not None and fetched >= max_deals:
                break
            batch_params = {**params, "start": offset, "limit": step}
            body = self.call_gentle(method, batch_params, pause, jitter, max_wait)
            items = body.get("result") or []
            if total is None:
                total = body.get("total")
            if not items:
                break
            yield items, total
            fetched += len(items)
            nxt = body.get("next")
            if nxt is None:
                break
            offset = nxt
            if on_progress:
                on_progress(fetched, total)

    def batch(self, commands):
        params = {"cmd": commands}
        resp = self.call("batch", params)
        return resp.get("result", {}).get("result", {})

    def get_all(self, method, params=None, chunk=50):
        return [i for pg, _ in self.paged_gentle(method, params, step=chunk)
                for i in pg]
