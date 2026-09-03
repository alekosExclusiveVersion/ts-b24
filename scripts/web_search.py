import argparse
import json
import sqlite3
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"


class SearchApp:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or DB_PATH)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._categories = None
        self._stages = None

    def categories(self):
        if self._categories is None:
            self._categories = [dict(r) for r in self.conn.execute(
                "SELECT ID, NAME FROM deal_categories ORDER BY ID")]
        return self._categories

    def _user_name(self, uid):
        if not uid:
            return None
        row = self.conn.execute(
            "SELECT LAST_NAME, NAME FROM users WHERE ID=?", (str(uid),)).fetchone()
        if not row:
            return str(uid)
        return f"{row[0]} {row[1]}".strip() or str(uid)

    def search(self, params):
        q = (params.get("q") or "").strip()
        category = params.get("category") or ""
        assigned = params.get("assigned") or ""
        date_from = params.get("date_from") or ""
        date_to = params.get("date_to") or ""
        limit = min(int(params.get("limit") or 50), 200)
        offset = max(int(params.get("offset") or 0), 0)

        where = []
        args = []

        if q:
            # Подбор фрагмента: FTS (точные слова) для ранжирования + LIKE (и фрагменты).
            # LIKE нужен для частичных слов на русском, которые FTS5 не находит как токен.
            like_where = "((d.TITLE LIKE ?) OR (COALESCE(d.COMMENTS,'') LIKE ?) OR (COALESCE(c.TITLE,'') LIKE ?))"
            like_args = ["%" + q + "%"] * 3
            where.append(like_where)
            args.extend(like_args)
        if category:
            where.append("d.CATEGORY_ID = ?")
            args.append(category)
        if assigned:
            where.append("d.ASSIGNED_BY_ID = ?")
            args.append(assigned)
        if date_from:
            where.append("d.DATE_CREATE >= ?")
            args.append(date_from + " 00:00:00")
        if date_to:
            where.append("d.DATE_CREATE <= ?")
            args.append(date_to + " 23:59:59")

        where_sql = (" WHERE " + " AND ".join(where)) if where else ""

        total = self.conn.execute(
            f"SELECT COUNT(*) FROM deals d "
            f"LEFT JOIN companies c ON c.ID = d.COMPANY_ID{where_sql}",
            args).fetchone()[0]

        rows = self.conn.execute(f"""
            SELECT d.ID, d.TITLE, d.COMPANY_ID, c.TITLE AS company_title,
                   d.CATEGORY_ID, d.STAGE_ID, s.NAME AS stage_name,
                   d.ASSIGNED_BY_ID, d.DATE_CREATE, d.OPPORTUNITY,
                   COALESCE(d.COMMENTS,'') AS comments
            FROM deals d
            LEFT JOIN deal_stages s ON s.STATUS_ID = d.STAGE_ID
            LEFT JOIN companies c ON c.ID = d.COMPANY_ID
            {where_sql}
            ORDER BY d.DATE_CREATE DESC
            LIMIT ? OFFSET ?
        """, args + [limit, offset]).fetchall()

        items = [dict(r) for r in rows]
        for it in items:
            it["assigned_name"] = self._user_name(it.get("ASSIGNED_BY_ID"))
        return {"total": total, "items": items,
                "offset": offset, "limit": limit}

    def deal_detail(self, deal_id):
        deal = self.conn.execute("""
            SELECT d.*, c.TITLE AS company_title
            FROM deals d
            LEFT JOIN companies c ON c.ID = d.COMPANY_ID
            WHERE d.ID = ?
        """, (deal_id,)).fetchone()
        if not deal:
            return None
        d = dict(deal)
        d["assigned_name"] = self._user_name(d.get("ASSIGNED_BY_ID"))
        d["category_name"] = self.conn.execute(
            "SELECT NAME FROM deal_categories WHERE ID=?",
            (d.get("CATEGORY_ID"),)).fetchone()[0] if d.get("CATEGORY_ID") else None
        d["stage_name"] = self.conn.execute(
            "SELECT NAME FROM deal_stages WHERE STATUS_ID=?",
            (d.get("STAGE_ID"),)).fetchone()[0] if d.get("STAGE_ID") else None
        # связанные контакты
        d["contacts"] = [dict(r) for r in self.conn.execute(
            "SELECT ID, NAME_LAST, PHONE, EMAIL, COMPANY_TITLE FROM contacts WHERE ID = ?",
            (self._contact_for_deal(d),))]
        # история сделок по той же компании
        d["company_deals"] = [dict(r) for r in self.conn.execute(
            "SELECT ID, TITLE, DATE_CREATE, CATEGORY_ID FROM deals "
            "WHERE COMPANY_ID=? ORDER BY DATE_CREATE DESC LIMIT 20",
            (d.get("COMPANY_ID"),))] if d.get("COMPANY_ID") else []
        return d

    def _contact_for_deal(self, d):
        # у deal может быть CONTACT_ID; если нет — ищем контакт по компании
        return d.get("CONTACT_ID")

    def assigned_users(self):
        return [{"id": str(r[0]), "name": self._user_name(r[0])} for r in self.conn.execute(
            "SELECT DISTINCT ASSIGNED_BY_ID AS id FROM deals "
            "WHERE ASSIGNED_BY_ID IS NOT NULL ORDER BY ASSIGNED_BY_ID")]


class Handler(BaseHTTPRequestHandler):
    app = None

    def log_message(self, *a):
        pass

    def _send(self, code, body_bytes, ctype="text/html; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html"):
            body = (TEMPLATE_DIR / "index.html").read_bytes()
            self._send(200, body)
            return
        if path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            params = {k: (v[0] if v else "") for k, v in qs.items()}
            try:
                res = self.app.search(params)
                self._send(200, json.dumps(res, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}).encode(),
                           "application/json; charset=utf-8")
            return
        if path == "/api/deal":
            qs = urllib.parse.parse_qs(parsed.query)
            deal_id = (qs.get("id") or [""])[0]
            d = self.app.deal_detail(deal_id)
            if d is None:
                self._send(404, json.dumps({"error": "not found"}).encode(),
                           "application/json; charset=utf-8")
            else:
                self._send(200, json.dumps(d, ensure_ascii=False).encode(),
                           "application/json; charset=utf-8")
            return
        if path == "/api/meta":
            self._send(200, json.dumps({
                "categories": self.app.categories(),
                "assigned": self.app.assigned_users(),
            }, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            return
        self._send(404, b"Not found")


def main():
    ap = argparse.ArgumentParser(description="Веб-интерфейс поиска по базе знаний")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--db", default=str(DB_PATH))
    args = ap.parse_args()

    Handler.app = SearchApp(args.db)
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Сервер запущен: http://{args.host}:{args.port}")
    print("Нажмите Ctrl+C для остановки")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено")
        srv.shutdown()


if __name__ == "__main__":
    main()
