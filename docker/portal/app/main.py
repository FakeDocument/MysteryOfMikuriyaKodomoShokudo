"""海域保全対策室 内部ポータル(骨格)

現時点ではヘルスチェックとプレースホルダーのトップページのみを提供する。
ログイン機能・組織概要ページ・隠しバックアップ・文書検索機能の実装は別途行う。
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="海域保全対策室 内部ポータル")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
