#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import http.cookies
import os
import secrets
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape


APP_HOST = "127.0.0.1"
APP_PORT = 8000
APP_DIR = Path(__file__).parent
DB_PATH = Path(os.environ.get("WEBMAIL_DB_PATH", "/tmp/mikuriya-webmail.db"))
STYLE_PATH = APP_DIR / "static" / "style.css"

KANZAKI_EMAIL = "hitomi.kanzaki@mikuriya-suisan.local"
MIKURIYA_EMAIL = "iwao.mikuriya@mikuriya-suisan.local"

TEMPLATES = Environment(
    loader=FileSystemLoader(APP_DIR / "templates"),
    autoescape=select_autoescape(("html", "xml")),
)
TEMPLATES.filters["urlencode"] = lambda value: urlencode({"id": value})

SESSIONS: dict[str, str] = {}
SESSIONS_LOCK = threading.Lock()


def password_digest(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def db_connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    DB_PATH.unlink(missing_ok=True)
    connection = db_connect()
    connection.executescript(
        """
        CREATE TABLE users (
            email TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            mailbox_owner TEXT NOT NULL,
            folder TEXT NOT NULL,
            sent_at TEXT NOT NULL,
            sender TEXT NOT NULL,
            recipient TEXT NOT NULL,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            search_text TEXT NOT NULL
        );
        """
    )

    connection.executemany(
        "INSERT INTO users(email, display_name, password_hash) VALUES (?, ?, ?)",
        [
            (KANZAKI_EMAIL, "神崎 仁美", password_digest("Kanzaki2019")),
            (MIKURIYA_EMAIL, "御厨 岩男", password_digest("Iw40-N0t-Guessable")),
        ],
    )

    messages = [
        (
            1,
            KANZAKI_EMAIL,
            "inbox",
            "2026-09-09 14:20",
            MIKURIYA_EMAIL,
            KANZAKI_EMAIL,
            "9月後半の勤務表について",
            "神崎さん\n\n9月後半の勤務表を共有フォルダへ置きました。\n04_store_operations/shift_schedule_2026-09-late.txt\n確認をお願いします。\n\n御厨",
        ),
        (
            2,
            KANZAKI_EMAIL,
            "inbox",
            "2026-09-08 09:05",
            "system@mikuriya-suisan.local",
            KANZAKI_EMAIL,
            "【連絡】社内メール定期保守",
            "社内メール利用者各位\n\n9月15日 22:00より定期保守を実施します。\n作業中は検索機能が一時的に利用できません。",
        ),
        (
            3,
            KANZAKI_EMAIL,
            "sent",
            "2026-09-06 18:12",
            KANZAKI_EMAIL,
            MIKURIYA_EMAIL,
            "子ども食堂の食材発注",
            "御厨さん\n\n来週分の食材発注表を共有フォルダへ置きました。\n04_store_operations/kodomo_shokudo_order_2026-09-week2.txt\nご確認ください。\n\n神崎",
        ),
        (
            10,
            MIKURIYA_EMAIL,
            "inbox",
            "2026-09-09 17:40",
            "shuji.katayanagi@kaiiki-hozen.local",
            MIKURIYA_EMAIL,
            "Re: 海域保全対策室ポータルのご案内",
            """御厨様

いつもご協力いただきありがとうございます。
先日ご相談の件、こちらのポータルから進捗をご確認いただけるようになりました。

URL: http://portal.kaiiki-hozen.local/
ユーザー名: mikuriya-partner
パスワード: %XO1AEFmvwHqmdik

外部協力者アカウントですので、閲覧・報告以外の操作はお控えください。
次回の「特別おまかせ」のスケジュールも、上記ポータルにて追ってご連絡します。

片柳修治
国土保全庁 海洋管理局 離島保全課 海域保全対策室""",
        ),
        (
            11,
            MIKURIYA_EMAIL,
            "sent",
            "2026-09-08 11:15",
            MIKURIYA_EMAIL,
            "shuji.katayanagi@kaiiki-hozen.local",
            "特別おまかせ 候補者の件",
            """片柳様

いつもお世話になっております。
今回もこちらで候補を選定いたしましたので、詳細はポータルにてご確認をお願いいたします。

御厨岩男""",
        ),
        (
            12,
            MIKURIYA_EMAIL,
            "inbox",
            "2026-09-05 08:30",
            "orders@toyosu-example.local",
            MIKURIYA_EMAIL,
            "9月第2週 入荷予定表",
            "御厨水産 御中\n\n9月第2週の入荷予定表を送付します。\n内容をご確認ください。",
        ),
    ]

    connection.executemany(
        """
        INSERT INTO messages(
            id, mailbox_owner, folder, sent_at, sender, recipient, subject, body, search_text
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [message + (" ".join(message[4:8]),) for message in messages],
    )
    connection.commit()
    connection.close()


def render_template(template_name: str, **context: object) -> str:
    context.setdefault("folder_labels", {"inbox": "受信箱", "sent": "送信済み"})
    return TEMPLATES.get_template(template_name).render(**context)


class WebmailHandler(BaseHTTPRequestHandler):
    server_version = "MikuriyaWebMail/2.4"

    def log_message(self, format_string: str, *args: object) -> None:
        print(f"webmail: {self.address_string()} - {format_string % args}", flush=True)

    def send_bytes(
        self,
        content: bytes,
        content_type: str,
        status: int = 200,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for name, value in extra_headers:
                self.send_header(name, value)
        self.end_headers()
        self.wfile.write(content)

    def send_html(
        self,
        content: str,
        status: int = 200,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        self.send_bytes(
            content.encode("utf-8"), "text/html; charset=utf-8", status, extra_headers
        )

    def redirect(
        self, location: str, headers: list[tuple[str, str]] | None = None
    ) -> None:
        response_headers = [("Location", location)]
        if headers:
            response_headers.extend(headers)
        self.send_html("", HTTPStatus.SEE_OTHER, response_headers)

    def current_user(self) -> sqlite3.Row | None:
        cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get("mikuriya_session")
        if session_cookie is None:
            return None

        with SESSIONS_LOCK:
            email = SESSIONS.get(session_cookie.value)
        if email is None:
            return None

        connection = db_connect()
        user = connection.execute(
            "SELECT email, display_name FROM users WHERE email = ?", (email,)
        ).fetchone()
        connection.close()
        return user

    def require_user(self) -> sqlite3.Row | None:
        user = self.current_user()
        if user is None:
            self.redirect("/")
        return user

    def get_mailbox(self, user: sqlite3.Row, folder: str) -> None:
        if folder not in {"inbox", "sent"}:
            folder = "inbox"

        connection = db_connect()
        messages = connection.execute(
            """
            SELECT id, sent_at, sender, recipient, subject
            FROM messages
            WHERE mailbox_owner = ? AND folder = ?
            ORDER BY sent_at DESC, id DESC
            """,
            (user["email"], folder),
        ).fetchall()
        connection.close()

        self.send_html(
            render_template(
                "mailbox.html",
                user=user,
                folder=folder,
                messages=messages,
            )
        )

    def get_message(self, user: sqlite3.Row, raw_message_id: str) -> None:
        try:
            message_id = int(raw_message_id)
        except ValueError:
            self.send_html(
                render_template(
                    "error.html", user=user, message="メール番号が不正です。"
                ),
                400,
            )
            return

        connection = db_connect()
        message = connection.execute(
            """
            SELECT sent_at, sender, recipient, subject, body
            FROM messages
            WHERE id = ? AND mailbox_owner = ?
            """,
            (message_id, user["email"]),
        ).fetchone()
        connection.close()

        if message is None:
            self.send_html(
                render_template(
                    "error.html", user=user, message="指定されたメールはありません。"
                ),
                404,
            )
            return
        self.send_html(render_template("message.html", user=user, message=message))

    def get_search(self, user: sqlite3.Row, query: str | None) -> None:
        messages: list[sqlite3.Row] | None = None
        database_error: str | None = None

        if query is not None:
            connection = db_connect()
            try:
                # CTF用に意図的に脆弱な検索処理としている。
                # ログイン処理や個別メール表示には同じ不備を持たせない。
                sql = (
                    "SELECT id, mailbox_owner, folder, sent_at, sender, recipient, subject, body "
                    "FROM messages "
                    f"WHERE mailbox_owner = '{user['email']}' "
                    f"AND search_text LIKE '%{query}%' "
                    "ORDER BY sent_at DESC, id DESC"
                )
                messages = connection.execute(sql).fetchall()
            except sqlite3.Error as exc:
                database_error = f"SQLite Error: {exc}"
            finally:
                connection.close()

        self.send_html(
            render_template(
                "search.html",
                user=user,
                query=query,
                messages=messages,
                database_error=database_error,
            )
        )

    def do_GET(self) -> None:
        request = urlparse(self.path)
        path = request.path
        params = parse_qs(request.query, keep_blank_values=True)

        if path == "/healthz":
            self.send_bytes(b"ok\n", "text/plain; charset=utf-8")
            return
        if path == "/static/style.css":
            self.send_bytes(STYLE_PATH.read_bytes(), "text/css; charset=utf-8")
            return
        if path == "/":
            if self.current_user() is not None:
                self.redirect("/inbox")
            else:
                self.send_html(
                    render_template("login.html", user=None, login_error=None)
                )
            return
        if path == "/logout":
            self.logout()
            return

        user = self.require_user()
        if user is None:
            return

        if path == "/inbox":
            self.get_mailbox(user, params.get("folder", ["inbox"])[0])
        elif path == "/message":
            self.get_message(user, params.get("id", [""])[0])
        elif path == "/search":
            self.get_search(user, params["q"][0] if "q" in params else None)
        else:
            self.send_html(
                render_template(
                    "error.html", user=user, message="ページが見つかりません。"
                ),
                404,
            )

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/login":
            self.send_html(
                render_template("error.html", user=None, message="不正な操作です。"),
                404,
            )
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        email = form.get("email", [""])[0].strip().lower()
        password = form.get("password", [""])[0]

        connection = db_connect()
        user = connection.execute(
            """
            SELECT email, display_name
            FROM users
            WHERE email = ? AND password_hash = ?
            """,
            (email, password_digest(password)),
        ).fetchone()
        connection.close()

        if user is None:
            self.send_html(
                render_template(
                    "login.html",
                    user=None,
                    login_error="メールアドレスまたはパスワードが違います。",
                ),
                401,
            )
            return

        session_id = secrets.token_urlsafe(24)
        with SESSIONS_LOCK:
            SESSIONS[session_id] = user["email"]
        self.redirect(
            "/inbox",
            [
                (
                    "Set-Cookie",
                    f"mikuriya_session={session_id}; Path=/; HttpOnly; SameSite=Lax",
                )
            ],
        )

    def logout(self) -> None:
        cookie = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get("mikuriya_session")
        if session_cookie is not None:
            with SESSIONS_LOCK:
                SESSIONS.pop(session_cookie.value, None)
        self.redirect(
            "/",
            [
                (
                    "Set-Cookie",
                    "mikuriya_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
                )
            ],
        )


def main() -> None:
    initialize_database()
    server = ThreadingHTTPServer((APP_HOST, APP_PORT), WebmailHandler)
    print(f"Mikuriya WebMail listening on http://{APP_HOST}:{APP_PORT}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
