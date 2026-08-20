"""九十九探偵事務所 調査ノートUI(骨格)

現時点ではヘルスチェックとトップページのみを提供する。
進捗保存・Flag判定・章立ての実装は別途行う。
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="九十九探偵事務所 調査ノート")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
