import argparse
import html
import json
import os
import re
import sqlite3
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from b24_client import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "ts_b24.db"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"

# crm.enum.activitytype: тип активности сделки
ACTIVITY_TYPES = {
    "1": "Встреча", "2": "Звонок", "3": "Задача", "4": "Письмо",
    "5": "Действие", "6": "Пользовательское действие",
    "0": "",
}

# Системный автор авто-комментариев портала — скрыт из переписки сделки.
# Переопределение без правки кода: env B24_HIDDEN_AUTHOR_ID.
HIDDEN_AUTHOR_ID = os.environ.get("B24_HIDDEN_AUTHOR_ID", "13797")


_BB_ONLY = re.compile(r"\[(/?)(p|b|i|u|s|table|tr|td|th|div|span|br)([^\[\]]*)\]", re.I)
_BB_URL = re.compile(r"\[URL(?:=[^\]]*)?\](.*?)\[/URL\]", re.I | re.S)
_BB_IMG = re.compile(r"\[IMG[^\]]*\].*?\[/IMG\]", re.I | re.S)
_BB_ANY = re.compile(r"\[[a-zA-Z/][a-zA-Z0-9_ ='\"\.\-:/]*\]")


def clean_bb(text):
    if not text:
        return text
    t = _BB_URL.sub(lambda m: m.group(1), text)
    t = _BB_IMG.sub("", t)
    t = _BB_ONLY.sub("", t)
    t = _BB_ANY.sub("", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
_DIV_RE = re.compile(r"</?(?:div|p|span|table|tr|td|th|tbody|thead|blockquote|section|article|header|footer|ul|ol|li|dl|dt|dd|h[1-6])[^>]*>", re.I)
_STYLE_RE = re.compile(r"<style[^>]*>.*?</style>", re.I | re.S)
_SCRIPT_RE = re.compile(r"<script[^>]*>.*?</script>", re.I | re.S)
_TRACKING_RE = re.compile(r'<img[^>]+(?:width|height)\s*=\s*["\']?1["\']?[^>]*>', re.I)
_MULTI_NL = re.compile(r"\n{3,}")


def strip_html(text):
    if not text:
        return text
    t = _STYLE_RE.sub("", text)
    t = _SCRIPT_RE.sub("", t)
    t = _TRACKING_RE.sub("", t)
    t = _BR_RE.sub("\n", t)
    t = _DIV_RE.sub("\n", t)
    t = _TAG_RE.sub("", t)
    t = html.unescape(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()



class SearchApp:
    def __init__(self, db_path=None):
        self.db_path = str(db_path or DB_PATH)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False,
                                     timeout=30)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA busy_timeout=30000;")
        self.conn.row_factory = sqlite3.Row
        self._categories = None
        self._stages = None

    def categories(self):
        if self._categories is None:
            self._categories = [dict(r) for r in self.conn.execute(
                "SELECT ID, NAME FROM deal_categories ORDER BY ID")]
        return self._categories

    def _stage_name(self, status_id, category_id):
        # STATUS_ID неуникален между воронками — ищем в паре с CATEGORY_ID,
        # при промахе откатываемся на STATUS_ID, затем на сырой ID.
        if not status_id:
            return None
        row = None
        if category_id:
            row = self.conn.execute(
                "SELECT NAME FROM deal_stages WHERE STATUS_ID=? AND CATEGORY_ID=?",
                (status_id, category_id)).fetchone()
        if row is None:
            row = self.conn.execute(
                "SELECT NAME FROM deal_stages WHERE STATUS_ID=?",
                (status_id,)).fetchone()
        return row[0] if row else status_id

    def _user_name(self, uid):
        if not uid:
            return None
        row = self.conn.execute(
            "SELECT LAST_NAME, NAME FROM users WHERE ID=?", (str(uid),)).fetchone()
        if not row:
            return str(uid)
        return f"{row[0]} {row[1]}".strip() or str(uid)

    # Имя ответственного одним JOIN вместо N запросов _user_name.
    _ASSIGNED_SQL = (
        "COALESCE(NULLIF(TRIM(COALESCE(u.LAST_NAME,'') || ' ' || "
        "COALESCE(u.NAME,'')), ''), d.ASSIGNED_BY_ID) AS assigned_name"
    )

    def _select_deals(self, where_sql, args, order_sql, limit, offset):
        rows = self.conn.execute(f"""
            SELECT d.ID, d.TITLE, d.COMPANY_ID, c.TITLE AS company_title,
                   d.CATEGORY_ID, d.STAGE_ID, s.NAME AS stage_name,
                   d.ASSIGNED_BY_ID, {self._ASSIGNED_SQL},
                   d.DATE_CREATE, d.OPPORTUNITY,
                   COALESCE(d.COMMENTS,'') AS comments
            FROM deals d
            LEFT JOIN deal_stages s
              ON s.STATUS_ID = d.STAGE_ID AND s.CATEGORY_ID = d.CATEGORY_ID
            LEFT JOIN companies c ON c.ID = d.COMPANY_ID
            LEFT JOIN users u ON u.ID = d.ASSIGNED_BY_ID
            {where_sql}
            {order_sql}
            LIMIT ? OFFSET ?
        """, args + [limit, offset]).fetchall()
        items = [dict(r) for r in rows]
        for it in items:
            it["comments"] = strip_html(clean_bb(it.get("comments")))
        return items

    def _fts_match(self, q):
        """Преобразует запрос пользователя в FTS5 MATCH с префиксным поиском.
        Возвращает None, если токенов нет (тогда caller идёт в LIKE-фолбэк)."""
        toks = re.findall(r"[^\W_]+", q.lower(), re.U)
        toks = [t for t in toks if len(t) >= 2][:10]
        if not toks:
            return None
        return " AND ".join('"' + t.replace('"', '""') + '"*' for t in toks)

    def _search_fts(self, match, category, assigned, date_from, date_to,
                    limit, offset):
        """Поиск через deals_fts с ранжированием bm25. Возвращает None,
        если FTS неприменим (синтаксис/пусто) — тогда caller делает LIKE."""
        fts_where = ["deals_fts MATCH ?"]
        fts_args = [match]
        if category:
            fts_where.append("category_id = ?")
            fts_args.append(category)
        if assigned:
            fts_where.append("assigned_by_id = ?")
            fts_args.append(assigned)
        if date_from:
            fts_where.append("date_create >= ?")
            fts_args.append(date_from + " 00:00:00")
        if date_to:
            fts_where.append("date_create <= ?")
            fts_args.append(date_to + " 23:59:59")
        fts_sql = " WHERE " + " AND ".join(fts_where)
        try:
            total = self.conn.execute(
                f"SELECT COUNT(*) FROM deals_fts{fts_sql}", fts_args).fetchone()[0]
        except sqlite3.OperationalError:
            return None
        if not total:
            return None
        rows = self.conn.execute(
            f"SELECT deal_id FROM deals_fts{fts_sql} "
            f"ORDER BY bm25(deals_fts) LIMIT ? OFFSET ?",
            fts_args + [limit, offset]).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            return {"total": total, "items": [],
                    "offset": offset, "limit": limit}
        ph = ",".join("?" * len(ids))
        items = self._select_deals(f"WHERE d.ID IN ({ph})", ids,
                                   "", len(ids), 0)
        by_id = {it["ID"]: it for it in items}
        ordered = [by_id[i] for i in ids if i in by_id]
        return {"total": total, "items": ordered,
                "offset": offset, "limit": limit}

    def search(self, params):
        q = (params.get("q") or "").strip()
        category = params.get("category") or ""
        assigned = params.get("assigned") or ""
        date_from = params.get("date_from") or ""
        date_to = params.get("date_to") or ""
        limit = min(int(params.get("limit") or 50), 200)
        offset = max(int(params.get("offset") or 0), 0)

        if q:
            # Сначала FTS5 (ранжирование через bm25); при промахе
            # (_search_fts вернул None: синтаксис/пусто/частичные слова) —
            # LIKE-фолбэк ниже.
            fts_res = self._search_fts(self._fts_match(q) or "", category,
                                       assigned, date_from, date_to,
                                       limit, offset)
            if fts_res is not None:
                return fts_res

        where = []
        args = []
        if q:
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

        items = self._select_deals(where_sql, args,
                                   "ORDER BY d.DATE_CREATE DESC", limit, offset)
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
        d["COMMENTS"] = strip_html(clean_bb(d.get("COMMENTS")))
        try:
            d["category_name"] = self.conn.execute(
                "SELECT NAME FROM deal_categories WHERE ID=?",
                (d.get("CATEGORY_ID"),)).fetchone()[0]
        except TypeError:
            d["category_name"] = f"Категория {d.get('CATEGORY_ID')}" if d.get("CATEGORY_ID") else None
        d["stage_name"] = self._stage_name(d.get("STAGE_ID"),
                                            d.get("CATEGORY_ID"))
        # переписка: комментарии ленты + активности сделки
        d["timeline"] = {
            "comments": [dict(r) for r in self.conn.execute(
                "SELECT id, created, comment, author_id FROM deal_comments "
                "WHERE deal_id=? AND author_id != ? ORDER BY created, id",
                (d.get("ID"), HIDDEN_AUTHOR_ID))],
            "activities": [dict(r) for r in self.conn.execute(
                "SELECT id, type_id, subject, description, description_type, "
                "start_time, completed, direction, provider_type_id, author_id "
                "FROM deal_activities WHERE deal_id=? "
                "ORDER BY COALESCE(start_time, created), id", (d.get("ID"),))],
        }
        for c in d["timeline"]["comments"]:
            c["comment"] = strip_html(clean_bb(c.get("comment")))
        for a in d["timeline"]["activities"]:
            a["description"] = strip_html(clean_bb(a.get("description")))
            a["type_name"] = ACTIVITY_TYPES.get(str(a.get("type_id")), "")
        d["timeline"]["count"] = (
            len(d["timeline"]["comments"]) + len(d["timeline"]["activities"]))
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
        return [{"id": str(r[0]), "name": r[1]} for r in self.conn.execute(
            "SELECT DISTINCT d.ASSIGNED_BY_ID AS id, "
            "COALESCE(NULLIF(TRIM(COALESCE(u.LAST_NAME,'') || ' ' || "
            "COALESCE(u.NAME,'')), ''), d.ASSIGNED_BY_ID) AS name "
            "FROM deals d LEFT JOIN users u ON u.ID = d.ASSIGNED_BY_ID "
            "WHERE d.ASSIGNED_BY_ID IS NOT NULL ORDER BY d.ASSIGNED_BY_ID")]


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
