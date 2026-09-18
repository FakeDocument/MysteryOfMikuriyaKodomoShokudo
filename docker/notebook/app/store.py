"""攻略対象環境から分離した調査ノート進捗ストア。"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def database_path() -> Path:
    explicit_path = os.environ.get("NOTEBOOK_DB_PATH")
    if explicit_path:
        return Path(explicit_path)
    return Path(os.environ.get("NOTEBOOK_DATA_DIR", "/data")) / "progress.db"


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    with connect() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS answers (
                question_id TEXT PRIMARY KEY,
                answer TEXT NOT NULL,
                solved_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notes (
                chapter_id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                acknowledged INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL
            )
            """
        )


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def save_answer(question_id: str, answer: str) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO answers (question_id, answer, solved_at)
            VALUES (?, ?, ?)
            ON CONFLICT(question_id) DO UPDATE SET
                answer = excluded.answer,
                solved_at = excluded.solved_at
            """,
            (question_id, answer, now_iso()),
        )


def save_note(chapter_id: str, content: str, acknowledged: bool) -> None:
    with connect() as connection:
        connection.execute(
            """
            INSERT INTO notes (chapter_id, content, acknowledged, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chapter_id) DO UPDATE SET
                content = excluded.content,
                acknowledged = MAX(notes.acknowledged, excluded.acknowledged),
                updated_at = excluded.updated_at
            """,
            (chapter_id, content, int(acknowledged), now_iso()),
        )


def get_progress(chapters: list[dict[str, Any]]) -> dict[str, Any]:
    initialize_database()
    with connect() as connection:
        answer_rows = connection.execute(
            "SELECT question_id, answer, solved_at FROM answers"
        ).fetchall()
        note_rows = connection.execute(
            "SELECT chapter_id, content, acknowledged, updated_at FROM notes"
        ).fetchall()

    current_question_ids = {
        question_id
        for chapter in chapters
        if chapter.get("available", True)
        for question_id in chapter.get("_question_ids", [])
    }
    answers = {
        row["question_id"]: {
            "answer": row["answer"],
            "solved_at": row["solved_at"],
        }
        for row in answer_rows
        if row["question_id"] in current_question_ids
    }
    notes = {
        row["chapter_id"]: {
            "content": row["content"],
            "acknowledged": bool(row["acknowledged"]),
            "updated_at": row["updated_at"],
        }
        for row in note_rows
    }

    solved_ids = set(answers)
    unlocked_ids: list[str] = []
    completed_ids: list[str] = []
    previous_complete = True

    for chapter in chapters:
        if not chapter.get("available", True):
            continue
        question_ids = chapter.get("_question_ids", [])
        unlocked = chapter["id"] == "prologue" or previous_complete
        if unlocked:
            unlocked_ids.append(chapter["id"])
        complete = unlocked and all(question_id in solved_ids for question_id in question_ids)
        if complete:
            completed_ids.append(chapter["id"])
        previous_complete = unlocked and complete

    total_questions = sum(
        len(chapter.get("_question_ids", []))
        for chapter in chapters
        if chapter.get("available", True)
    )

    return {
        "answers": answers,
        "notes": notes,
        "solved_question_ids": sorted(solved_ids),
        "acknowledged_note_chapter_ids": sorted(
            chapter_id for chapter_id, note in notes.items() if note["acknowledged"]
        ),
        "unlocked_chapter_ids": unlocked_ids,
        "completed_chapter_ids": completed_ids,
        "solved_count": len(solved_ids),
        "total_questions": total_questions,
    }
