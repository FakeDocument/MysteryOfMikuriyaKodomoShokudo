"""九十九探偵事務所の調査ノートUI。"""

import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParameter, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .content import CHAPTERS, QUESTIONS_BY_ID, public_chapters, validate_answer
from .store import get_progress, initialize_database, save_answer, save_note


APP_DIR = Path(__file__).parent
ASSET_VERSION = hashlib.sha256(
    b"".join(
        (APP_DIR / "static" / filename).read_bytes()
        for filename in ("notebook.css", "markdown.js", "notebook.js")
    )
).hexdigest()[:12]


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="九十九探偵事務所 調査ノート",
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:6901", "http://localhost:6901"],
    allow_methods=["GET", "PUT"],
    allow_headers=["Content-Type"],
)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))
NOTE_SUBSCRIBERS: set[asyncio.Queue[dict]] = set()


class AnswerSubmission(BaseModel):
    answer: str = Field(max_length=500)


class NoteSubmission(BaseModel):
    content: str = Field(max_length=12000)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    current_progress = get_progress(CHAPTERS)
    response = templates.TemplateResponse(
        request,
        "index.html",
        {
            "chapters": public_chapters(current_progress),
            "progress": current_progress,
            "asset_version": ASSET_VERSION,
        },
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/progress")
def progress() -> dict:
    return get_progress(CHAPTERS)


@app.post("/api/answers/{question_id}")
def submit_answer(
    question_id: Annotated[str, PathParameter(pattern=r"^[a-z0-9_-]+$")],
    submission: AnswerSubmission,
) -> dict:
    question = QUESTIONS_BY_ID.get(question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="設問が見つかりません。")

    current_progress = get_progress(CHAPTERS)
    if question["chapter_id"] not in current_progress["unlocked_chapter_ids"]:
        raise HTTPException(status_code=403, detail="この章はまだ開かれていません。")

    if not submission.answer.strip():
        return {
            "correct": False,
            "message": "空欄のままでは記録できません。",
            "progress": current_progress,
        }

    if not validate_answer(question, submission.answer):
        return {
            "correct": False,
            "message": question.get("incorrect_message", "証拠と少し食い違うようだ。もう一度確かめよう。"),
            "progress": current_progress,
        }

    was_solved = question_id in current_progress["solved_question_ids"]
    save_answer(question_id, submission.answer.strip())
    updated_progress = get_progress(CHAPTERS)
    return {
        "correct": True,
        "newly_solved": not was_solved,
        "message": "証拠と一致した。調査ノートに記録した。",
        "progress": updated_progress,
        "chapters": public_chapters(updated_progress),
    }


@app.get("/api/note")
def get_note() -> dict:
    return get_progress(CHAPTERS)["note"]


def publish_note(note: dict) -> None:
    """接続中の画面へ最新のメモだけを配信する。"""
    for queue in tuple(NOTE_SUBSCRIBERS):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        queue.put_nowait(note)


@app.put("/api/note")
async def submit_note(submission: NoteSubmission) -> dict:
    save_note(submission.content)
    updated_progress = get_progress(CHAPTERS)
    publish_note(updated_progress["note"])
    return {
        "saved": True,
        "message": "調査メモを保存しました。",
        "note": updated_progress["note"],
        "progress": updated_progress,
    }


@app.get("/api/note/events")
async def note_events(request: Request) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=1)
        NOTE_SUBSCRIBERS.add(queue)
        try:
            yield f"data: {json.dumps(get_note(), ensure_ascii=False)}\n\n"
            while not await request.is_disconnected():
                try:
                    note = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {json.dumps(note, ensure_ascii=False)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            NOTE_SUBSCRIBERS.discard(queue)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
