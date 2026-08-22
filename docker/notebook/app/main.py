"""九十九探偵事務所の調査ノートUI。"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Path as PathParameter, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .content import CHAPTERS, QUESTIONS_BY_ID, public_chapters, validate_answer
from .store import get_progress, initialize_database, save_answer, save_note


APP_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(title="九十九探偵事務所 調査ノート", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=APP_DIR / "static"), name="static")
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


class AnswerSubmission(BaseModel):
    answer: str = Field(max_length=500)


class NoteSubmission(BaseModel):
    content: str = Field(max_length=4000)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index(request: Request) -> HTMLResponse:
    current_progress = get_progress(CHAPTERS)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "chapters": public_chapters(current_progress),
            "progress": current_progress,
        },
    )


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


@app.post("/api/notes/{chapter_id}")
def submit_note(
    chapter_id: Annotated[str, PathParameter(pattern=r"^[a-z0-9_-]+$")],
    submission: NoteSubmission,
) -> dict:
    chapter = next((item for item in CHAPTERS if item["id"] == chapter_id), None)
    if chapter is None:
        raise HTTPException(status_code=404, detail="章が見つかりません。")

    current_progress = get_progress(CHAPTERS)
    if chapter_id not in current_progress["unlocked_chapter_ids"]:
        raise HTTPException(status_code=403, detail="この章はまだ開かれていません。")

    content = submission.content.strip()
    if not content:
        return {
            "saved": False,
            "message": "証拠欄が空です。見つけた事実を書き留めましょう。",
            "progress": current_progress,
        }

    first_note = chapter_id not in current_progress["acknowledged_note_chapter_ids"]
    save_note(chapter_id, content, acknowledged=True)
    updated_progress = get_progress(CHAPTERS)
    return {
        "saved": True,
        "first_note": first_note,
        "message": "証拠メモを保存しました。",
        "progress": updated_progress,
        "chapters": public_chapters(updated_progress),
    }
