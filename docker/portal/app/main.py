"""隔離CTF用：公開情報、認証付き目録、検索SQLインジェクション。"""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

APP_DIR = Path(__file__).parent
DB_PATH = Path("/tmp/kaiiki-documents.db")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
SESSION_COOKIE = "kaiiki_session"
SESSIONS: dict[str, str] = {}
MIGRATION_CODE = "E6N4-P9R2-T3M5"

REGISTRY = [
    ("A-01", "火山活動に伴う新島地形変動", "自然災害"), ("A-02", "台風・高潮による低潮線損壊", "自然災害"),
    ("A-03", "大規模漂流物の離島接近", "航行・施設リスク"), ("A-04", "外国公船の継続航行", "安全保障"),
    ("A-05", "違法操業船団の反復出現", "海上取締り"), ("A-06", "海底通信ケーブル障害", "基盤障害"),
    ("A-07", "管理対象（詳細非公開）", "特異事象"), ("A-08", "船舶燃料等の海上流出", "海洋汚染"),
    ("A-09", "無人島斜面の大規模崩落", "自然災害"), ("A-10", "危険物の継続漂着", "海岸保全"),
    ("A-11", "衛星測位信号への妨害", "航行・通信障害"), ("A-12", "定点観測記録の時刻不整合", "特異事象"),
    ("A-13", "サンゴ礁の急速な衰退", "海洋環境"),
]

SECRET_DOCUMENTS = [
    ("a07-observation", "観測調整係／継続観測票 A-07", "A-07 継続観測", """管理番号：A-07　観測点：南方第3点
2024年8月18日 23:40　岩礁の輪郭を確認。
2024年8月19日 04:10　同岩礁を確認できず。地震・波浪の基準超過なし。
2024年8月20日 02:00　定例提供を実施。
2024年8月20日 04:10　水位の上昇停止。

照合資料：民俗資料抄録 F-03／実施要領 H-02
備考：機器交換後も欠測範囲は一致。故障として閉じないこと。"""),
    ("folklore", "資料室／沿岸伝承採録 F-03", "F-03 沿岸伝承", """聞き取り台帳からの転記。採録地名は原本による。

甲地区：『オオクチ様』。海の底におり、腹が空くと島を食うという。
乙地区：岩礁が一夜でなくなることを『島食い』と呼ぶ。
祭礼記録：『身の肥えたる子を海へ差し出す』。翌朝、潮は静まったと記す。

呼称整理：甲地区の呼称を統一名称として採用。
注：本抄録は伝承の採録であり、現代の観測を記載したものではない。"""),
    ("a07-policy", "輸送調整係／実施要領 H-02", "H-02 実施要領", """適用：南方第3点の継続保全

定例提供後の観測値が基準内へ戻ることを確認し、次期提供まで監視を継続する。
保全対象の島礁が消失した場合、同島を根拠とする排他的経済水域（EEZ）の維持に支障が生じる。
提供の中断は認めない。

民間協力者は対象の選定と確保、当室は受入と輸送を所管する。
民間協力者：御厨水産（代表：御厨岩男）。仲介は御厨家が継承。
現地で用いる呼称は『特別メニュー』。月次の受入照合簿により受入番号を確認すること。
本人氏名は輸送関係帳票へ転記しない。"""),
    ("transfer-settings", "情報管理係／夜間出力処理の保守引継", "出力 設定 保守", """取扱：情報管理係内
文書目録と輸送原簿は別管理。月次原簿の出力は下記ジョブを使用する。
配車担当による当日修正は共有側にのみ反映されるため、目録へ写した古い原簿を使用しないこと。

旧ジョブ設定（移行元から転記）
server = kaiiki-hozen.local
share = handoff
username = hozen_sync
password = TideLog_2024

移行後も旧ジョブとの併用期間中は同じ接続設定を使用する。
参照担当のアカウントには原簿の書込権限を付与しない。"""),
]

def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def password_digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def initialize_database() -> None:
    DB_PATH.unlink(missing_ok=True)
    SESSIONS.clear()
    with connect() as connection:
        connection.execute("CREATE TABLE access_codes (code_hash TEXT PRIMARY KEY, username TEXT NOT NULL)")
        connection.execute("INSERT INTO access_codes VALUES (?, ?)", (password_digest(MIGRATION_CODE), "katayanagi"))
        connection.execute("CREATE TABLE documents (slug TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL, owner TEXT NOT NULL, search_text TEXT NOT NULL, body TEXT NOT NULL)")
        connection.executemany("INSERT INTO documents VALUES (?, ?, ?, 'common', ?, ?)", [
            (number.lower(), f"{number} {title}", category, f"{number} {title} {category}", "共通管理簿に登録された概要情報です。")
            for number, title, category in REGISTRY
        ])
        connection.execute("INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?)", (
            "monthly-contact", "連絡調整係／9月連絡業務", "連絡調整", "katayanagi", "連絡 月次 9月",
            "9月分の民間協力者への照会は片柳が担当する。\n輸送原簿の管理と配車の確定は輸送調整係が行う。\n本目録の通常照会範囲は、共通管理簿と本人の担当文書。"
        ))
        connection.executemany("INSERT INTO documents VALUES (?, ?, '係内限り', 'records', ?, ?)", SECRET_DOCUMENTS)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="海域保全対策室", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")


def is_catalog(request: Request) -> bool:
    # nginxが受信ヘッダーを上書きし、実際の待受ポートからサービスを選ぶ。
    return request.headers.get("x-kaiiki-service") == "catalog"


def current_user(request: Request) -> str | None:
    return SESSIONS.get(request.cookies.get(SESSION_COOKIE, ""))


def require_user(request: Request) -> str:
    if not is_catalog(request):
        raise HTTPException(status_code=404)
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="ログインが必要です。")
    return user


def redeem_code(code: str) -> str | None:
    with connect() as connection:
        row = connection.execute(
            "SELECT username FROM access_codes WHERE code_hash = ?",
            (password_digest(code),),
        ).fetchone()
        return row["username"] if row else None


def search_documents(keyword: str, username: str) -> list[sqlite3.Row]:
    """CTFの意図した脆弱性：検索語によって本人の担当範囲を突破できる。"""
    with connect() as connection:
        query = "SELECT * FROM documents WHERE (owner = ? OR owner = 'common') AND search_text LIKE '%" + keyword + "%' ORDER BY slug"
        try:
            return connection.execute(query, (username,)).fetchall()
        except sqlite3.Error:
            return []


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    if not is_catalog(request):
        return templates.TemplateResponse(request, "public.html")
    user = current_user(request)
    if user is None:
        return templates.TemplateResponse(request, "login.html")
    keyword = request.query_params.get("keyword", "")
    return templates.TemplateResponse(request, "catalog.html", {
        "user": user, "keyword": keyword, "results": search_documents(keyword, user),
        "access_query": urlencode({"keyword": keyword}),
    })


@app.post("/login")
async def login(request: Request):
    if not is_catalog(request):
        raise HTTPException(status_code=404)
    form = parse_qs((await request.body()).decode(), keep_blank_values=True)
    code = form.get("code", [""])[0].strip()
    username = redeem_code(code)
    if username is None:
        return templates.TemplateResponse(request, "login.html", {
            "error": "閲覧コードを確認してください。"
        }, status_code=401)
    old_token = request.cookies.get(SESSION_COOKIE, "")
    SESSIONS.pop(old_token, None)
    token = secrets.token_urlsafe(32)
    SESSIONS[token] = username
    response = RedirectResponse("/", status_code=303)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="strict")
    return response


@app.post("/logout")
def logout(request: Request):
    require_user(request)
    SESSIONS.pop(request.cookies.get(SESSION_COOKIE, ""), None)
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/archive/", response_class=HTMLResponse)
def archive(request: Request) -> HTMLResponse:
    if is_catalog(request):
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "archive.html")


@app.post("/search", response_class=HTMLResponse)
async def search(request: Request) -> HTMLResponse:
    user = require_user(request)
    form = parse_qs((await request.body()).decode(), keep_blank_values=True)
    keyword = form.get("keyword", [""])[0]
    return templates.TemplateResponse(request, "catalog.html", {
        "results": search_documents(keyword, user), "keyword": keyword, "user": user,
        "access_query": urlencode({"keyword": keyword}),
    })


@app.get("/documents/{slug}", response_class=HTMLResponse)
def document(request: Request, slug: str) -> HTMLResponse:
    user = require_user(request)
    keyword = request.query_params.get("keyword", "")
    # 検索結果をそのまま閲覧権限に使う旧実装。単純なID変更では非担当文書へ入れない。
    rows = {row["slug"]: row for row in search_documents(keyword, user)}
    if slug not in rows:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "document.html", {
        "document": rows[slug], "user": user, "access_query": urlencode({"keyword": keyword}),
    })
