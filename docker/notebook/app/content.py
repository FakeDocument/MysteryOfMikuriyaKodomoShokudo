"""JSONから調査ノートの章・ブロック・設問・正解を読み込む。"""

from __future__ import annotations

import json
import re
import unicodedata
from copy import deepcopy
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).parent / "data"
CHAPTERS_DIR = DATA_DIR / "chapters"
CHAPTERS_MANIFEST_PATH = CHAPTERS_DIR / "manifest.json"
ANSWERS_PATH = DATA_DIR / "answers.json"
ANSWER_ONLY_KEYS = {"accepted", "validation", "required_terms", "incorrect_message"}
ALLOWED_VALIDATIONS = {"one_of", "exact", "contains_all"}
ALLOWED_SPEAKERS = {"director", "player"}
ALLOWED_VISIBILITY_EVENTS = {"note_saved", "question_solved"}
ALLOWED_TOP_LEVEL_BLOCKS = {"dialogue", "document", "evidence_note", "questions"}
ALLOWED_QUESTION_BLOCKS = {"hints", "dialogue"}


class ContentConfigurationError(ValueError):
    """調査ノートのJSON設定に矛盾がある。"""


def _load_json(path: Path, version: int) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ContentConfigurationError(f"データファイルが見つかりません: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContentConfigurationError(
            f"{path.name} のJSON構文エラー: {exc.lineno}行{exc.colno}列 ({exc.msg})"
        ) from exc

    if not isinstance(data, dict):
        raise ContentConfigurationError(f"{path.name} のルートはJSONオブジェクトにしてください。")
    if data.get("version") != version:
        raise ContentConfigurationError(f"{path.name} の version は {version} にしてください。")
    return data


def _require_text(value: Any, location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ContentConfigurationError(f"{location} は空でない文字列にしてください。")


def _validate_heading(heading: Any, location: str) -> None:
    if not isinstance(heading, dict):
        raise ContentConfigurationError(f"{location} はオブジェクトにしてください。")
    for key in ("kicker", "title"):
        _require_text(heading.get(key), f"{location}.{key}")
    if "number" in heading:
        _require_text(heading["number"], f"{location}.number")


def _validate_dialogue(messages: Any, location: str) -> None:
    if not isinstance(messages, list) or not messages:
        raise ContentConfigurationError(f"{location} は空でない配列にしてください。")
    for index, item in enumerate(messages):
        item_location = f"{location}[{index}]"
        if not isinstance(item, dict):
            raise ContentConfigurationError(f"{item_location} はオブジェクトにしてください。")
        if item.get("speaker") not in ALLOWED_SPEAKERS:
            raise ContentConfigurationError(
                f"{item_location}.speaker は director または player にしてください。"
            )
        _require_text(item.get("text"), f"{item_location}.text")


def _validate_visibility(value: Any, location: str, allowed_event: str) -> None:
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {"event"}:
        raise ContentConfigurationError(
            f"{location} は event だけを持つオブジェクトにしてください。"
        )
    event = value.get("event")
    if event not in ALLOWED_VISIBILITY_EVENTS:
        raise ContentConfigurationError(
            f"{location}.event は {', '.join(sorted(ALLOWED_VISIBILITY_EVENTS))} のいずれかにしてください。"
        )
    if event != allowed_event:
        raise ContentConfigurationError(f"{location}.event に {event} は使用できません。")


def _validate_answer(question_id: str, answer: Any) -> None:
    if not isinstance(answer, dict):
        raise ContentConfigurationError(
            f"answers.json の {question_id} はオブジェクトにしてください。"
        )

    unknown_keys = set(answer).difference(ANSWER_ONLY_KEYS)
    if unknown_keys:
        raise ContentConfigurationError(
            f"{question_id} に未対応の正解設定があります: {', '.join(sorted(unknown_keys))}"
        )

    validation = answer.get("validation", "one_of")
    if validation not in ALLOWED_VALIDATIONS:
        raise ContentConfigurationError(
            f"{question_id}.validation は {', '.join(sorted(ALLOWED_VALIDATIONS))} のいずれかにしてください。"
        )

    if validation in {"one_of", "exact"}:
        accepted = answer.get("accepted")
        if not isinstance(accepted, list) or not accepted:
            raise ContentConfigurationError(
                f"{question_id} には1件以上の accepted が必要です。"
            )
        for index, value in enumerate(accepted):
            _require_text(value, f"{question_id}.accepted[{index}]")

    if validation == "contains_all":
        required_terms = answer.get("required_terms")
        if not isinstance(required_terms, list) or not required_terms:
            raise ContentConfigurationError(
                f"{question_id} には1件以上の required_terms が必要です。"
            )
        for index, value in enumerate(required_terms):
            _require_text(value, f"{question_id}.required_terms[{index}]")

    if "incorrect_message" in answer:
        _require_text(answer["incorrect_message"], f"{question_id}.incorrect_message")


def _validate_question_blocks(blocks: Any, location: str) -> None:
    if not isinstance(blocks, list):
        raise ContentConfigurationError(f"{location} は配列にしてください。")

    block_ids: set[str] = set()
    for index, block in enumerate(blocks):
        block_location = f"{location}[{index}]"
        if not isinstance(block, dict):
            raise ContentConfigurationError(f"{block_location} はオブジェクトにしてください。")
        block_type = block.get("type")
        if block_type not in ALLOWED_QUESTION_BLOCKS:
            raise ContentConfigurationError(
                f"{block_location}.type は hints または dialogue にしてください。"
            )
        block_id = block.get("id")
        _require_text(block_id, f"{block_location}.id")
        if block_id in block_ids:
            raise ContentConfigurationError(f"{location} のブロックIDが重複しています: {block_id}")
        block_ids.add(block_id)

        if block_type == "hints":
            hints = block.get("items")
            if not isinstance(hints, list) or not hints:
                raise ContentConfigurationError(f"{block_location}.items は空でない配列にしてください。")
            for hint_index, hint in enumerate(hints):
                _require_text(hint, f"{block_location}.items[{hint_index}]")
        else:
            _validate_visibility(
                block.get("visible_when"),
                f"{block_location}.visible_when",
                "question_solved",
            )
            _validate_heading(block.get("heading"), f"{block_location}.heading")
            _validate_dialogue(block.get("messages"), f"{block_location}.messages")


def _validate_question(
    question: Any,
    location: str,
    chapter_id: str,
    question_ids: set[str],
    questions_by_id: dict[str, dict[str, Any]],
    answers: dict[str, Any],
) -> None:
    if not isinstance(question, dict):
        raise ContentConfigurationError(f"{location} はオブジェクトにしてください。")
    if question.get("type") != "question":
        raise ContentConfigurationError(f"{location}.type は question にしてください。")

    leaked_keys = ANSWER_ONLY_KEYS.intersection(question)
    if leaked_keys:
        raise ContentConfigurationError(
            f"{location} の {', '.join(sorted(leaked_keys))} は answers.json へ移してください。"
        )

    question_id = question.get("id")
    _require_text(question_id, f"{location}.id")
    if question_id in question_ids:
        raise ContentConfigurationError(f"設問IDが重複しています: {question_id}")
    question_ids.add(question_id)

    for key in ("label", "prompt", "placeholder", "input_mode"):
        _require_text(question.get(key), f"{question_id}.{key}")
    _validate_question_blocks(question.get("blocks"), f"{question_id}.blocks")

    answer = answers.get(question_id)
    if answer is None:
        raise ContentConfigurationError(
            f"answers.json に設問 {question_id} の正解設定がありません。"
        )
    _validate_answer(question_id, answer)
    question["chapter_id"] = chapter_id
    question.update(deepcopy(answer))
    questions_by_id[question_id] = question


def _validate_chapter_blocks(
    blocks: Any,
    chapter_id: str,
    question_ids: set[str],
    questions_by_id: dict[str, dict[str, Any]],
    answers: dict[str, Any],
) -> list[str]:
    if not isinstance(blocks, list):
        raise ContentConfigurationError(f"{chapter_id}.blocks は配列にしてください。")

    block_ids: set[str] = set()
    chapter_question_ids: list[str] = []
    for index, block in enumerate(blocks):
        location = f"{chapter_id}.blocks[{index}]"
        if not isinstance(block, dict):
            raise ContentConfigurationError(f"{location} はオブジェクトにしてください。")
        block_type = block.get("type")
        if block_type not in ALLOWED_TOP_LEVEL_BLOCKS:
            raise ContentConfigurationError(
                f"{location}.type は {', '.join(sorted(ALLOWED_TOP_LEVEL_BLOCKS))} のいずれかにしてください。"
            )
        block_id = block.get("id")
        _require_text(block_id, f"{location}.id")
        if block_id in block_ids:
            raise ContentConfigurationError(f"{chapter_id} のブロックIDが重複しています: {block_id}")
        block_ids.add(block_id)
        _validate_heading(block.get("heading"), f"{location}.heading")

        if block_type == "dialogue":
            _validate_visibility(
                block.get("visible_when"),
                f"{location}.visible_when",
                "note_saved",
            )
            _validate_dialogue(block.get("messages"), f"{location}.messages")
        elif block_type == "document":
            content = block.get("content")
            if not isinstance(content, dict):
                raise ContentConfigurationError(f"{location}.content はオブジェクトにしてください。")
            for key in ("kicker", "title", "received_stamp", "date", "signature"):
                _require_text(content.get(key), f"{location}.content.{key}")
            body = content.get("body")
            if not isinstance(body, list) or not body:
                raise ContentConfigurationError(f"{location}.content.body は空でない配列にしてください。")
            for paragraph_index, paragraph in enumerate(body):
                _require_text(paragraph, f"{location}.content.body[{paragraph_index}]")
        elif block_type == "evidence_note":
            for key in ("label", "placeholder", "action_label"):
                _require_text(block.get(key), f"{location}.{key}")
        else:
            items = block.get("items")
            if not isinstance(items, list) or not items:
                raise ContentConfigurationError(f"{location}.items は空でない配列にしてください。")
            for question_index, question in enumerate(items):
                _validate_question(
                    question,
                    f"{location}.items[{question_index}]",
                    chapter_id,
                    question_ids,
                    questions_by_id,
                    answers,
                )
                chapter_question_ids.append(question["id"])
    return chapter_question_ids


def _load_chapter_files(manifest_path: Path) -> list[dict[str, Any]]:
    manifest = _load_json(manifest_path, version=2)
    chapter_files = manifest.get("chapter_files")
    if not isinstance(chapter_files, list) or not chapter_files:
        raise ContentConfigurationError(
            "manifest.json の chapter_files は空でない配列にしてください。"
        )

    chapters: list[dict[str, Any]] = []
    seen_files: set[str] = set()
    for index, filename in enumerate(chapter_files):
        _require_text(filename, f"manifest.json.chapter_files[{index}]")
        path_part = Path(filename)
        if path_part.name != filename or path_part.suffix != ".json" or filename == "manifest.json":
            raise ContentConfigurationError(
                f"manifest.json.chapter_files[{index}] は同じフォルダ内の章JSON名にしてください。"
            )
        if filename in seen_files:
            raise ContentConfigurationError(f"章ファイルが重複しています: {filename}")
        seen_files.add(filename)
        chapter_data = _load_json(manifest_path.parent / filename, version=2)
        chapter = chapter_data.get("chapter")
        if not isinstance(chapter, dict):
            raise ContentConfigurationError(f"{filename} の chapter はオブジェクトにしてください。")
        chapters.append(chapter)
    return chapters


def load_content(
    chapters_manifest_path: Path = CHAPTERS_MANIFEST_PATH,
    answers_path: Path = ANSWERS_PATH,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """章ファイル群と正解JSONを検証し、サーバー内部用データへ結合する。"""

    chapters = _load_chapter_files(chapters_manifest_path)
    answers_data = _load_json(answers_path, version=1)
    answers = answers_data.get("answers")
    if not isinstance(answers, dict):
        raise ContentConfigurationError("answers.json の answers はオブジェクトにしてください。")

    chapter_ids: set[str] = set()
    question_ids: set[str] = set()
    questions_by_id: dict[str, dict[str, Any]] = {}

    for chapter_index, chapter in enumerate(chapters):
        location = f"chapters[{chapter_index}]"
        chapter_id = chapter.get("id")
        _require_text(chapter_id, f"{location}.id")
        if chapter_id in chapter_ids:
            raise ContentConfigurationError(f"章IDが重複しています: {chapter_id}")
        chapter_ids.add(chapter_id)

        for key in (
            "number",
            "nav_title",
            "title",
            "date",
            "eyebrow",
            "status_label",
            "objective",
            "lead",
        ):
            _require_text(chapter.get(key), f"{chapter_id}.{key}")
        if not isinstance(chapter.get("available"), bool):
            raise ContentConfigurationError(
                f"{chapter_id}.available は true または false にしてください。"
            )

        chapter["_question_ids"] = _validate_chapter_blocks(
            chapter.get("blocks"),
            chapter_id,
            question_ids,
            questions_by_id,
            answers,
        )

    orphan_answers = set(answers).difference(question_ids)
    if orphan_answers:
        raise ContentConfigurationError(
            "設問に対応しない正解設定があります: " + ", ".join(sorted(orphan_answers))
        )
    if "prologue" not in chapter_ids:
        raise ContentConfigurationError("章ID prologue が必要です。")

    return chapters, questions_by_id


CHAPTERS, QUESTIONS_BY_ID = load_content()


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s\u3000]+", "", value).rstrip("/")


def validate_answer(question: dict[str, Any], answer: str) -> bool:
    validation = question.get("validation", "one_of")
    if validation == "exact":
        normalized_answer = unicodedata.normalize("NFKC", answer.strip())
        return any(
            normalized_answer == unicodedata.normalize("NFKC", accepted)
            for accepted in question["accepted"]
        )

    if validation == "contains_all":
        normalized_answer = normalize(answer)
        return all(normalize(term) in normalized_answer for term in question["required_terms"])

    normalized_answer = normalize(answer)
    return any(normalized_answer == normalize(accepted) for accepted in question["accepted"])


def _public_question(question: dict[str, Any], solved_ids: set[str]) -> None:
    for key in ANSWER_ONLY_KEYS | {"chapter_id"}:
        question.pop(key, None)
    public_blocks = []
    for block in question.get("blocks", []):
        visibility = block.get("visible_when")
        if visibility and visibility.get("event") == "question_solved":
            if question["id"] not in solved_ids:
                continue
        block.pop("visible_when", None)
        public_blocks.append(block)
    question["blocks"] = public_blocks


def public_chapters(progress: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """ブラウザへ渡せる範囲だけに絞り、正解と未解放の内容を除く。"""

    solved_ids = set(progress["solved_question_ids"]) if progress else set()
    acknowledged_notes = set(progress["acknowledged_note_chapter_ids"]) if progress else set()
    unlocked_ids = set(progress["unlocked_chapter_ids"]) if progress else {"prologue"}
    chapters = deepcopy(CHAPTERS)
    for chapter in chapters:
        chapter.pop("_question_ids", None)
        if chapter["id"] not in unlocked_ids:
            chapter["objective"] = "前の章の調査を完了すると開封されます。"
            chapter["lead"] = "このページは、まだ封が切られていない。"
            chapter["blocks"] = []
            continue

        public_blocks = []
        for block in chapter["blocks"]:
            visibility = block.get("visible_when")
            if visibility and visibility.get("event") == "note_saved":
                if chapter["id"] not in acknowledged_notes:
                    continue
            block.pop("visible_when", None)
            if block["type"] == "questions":
                for question in block["items"]:
                    _public_question(question, solved_ids)
            public_blocks.append(block)
        chapter["blocks"] = public_blocks
    return chapters


def main() -> None:
    print(f"調査ノートデータ: OK ({len(CHAPTERS)}章 / {len(QUESTIONS_BY_ID)}設問)")


if __name__ == "__main__":
    main()
