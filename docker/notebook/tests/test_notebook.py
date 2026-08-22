import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from app.content import (
    ANSWERS_PATH,
    CHAPTERS,
    CHAPTERS_MANIFEST_PATH,
    QUESTIONS_BY_ID,
    ContentConfigurationError,
    load_content,
    public_chapters,
    validate_answer,
)
from app.store import get_progress, initialize_database, save_answer, save_note


def block_of_type(chapter, block_type):
    return next(block for block in chapter["blocks"] if block["type"] == block_type)


def questions_in(chapter):
    for block in chapter["blocks"]:
        if block["type"] == "questions":
            return block["items"]
    return []


class AnswerValidationTest(unittest.TestCase):
    def test_japanese_name_accepts_spacing_and_kana(self):
        question = QUESTIONS_BY_ID["prologue_requester"]
        self.assertTrue(validate_answer(question, " 遠藤　美咲 "))
        self.assertTrue(validate_answer(question, "エンドウミサキ"))

    def test_password_is_case_sensitive(self):
        question = QUESTIONS_BY_ID["ch1_samba_password"]
        self.assertTrue(validate_answer(question, "Kanzaki2019"))
        self.assertFalse(validate_answer(question, "kanzaki2019"))

    def test_reasoning_answer_requires_both_terms(self):
        question = QUESTIONS_BY_ID["ch2_selection_conditions"]
        self.assertTrue(validate_answer(question, "孤立していて、肉付きが良いこと"))
        self.assertFalse(validate_answer(question, "孤立していること"))

    def test_public_data_does_not_expose_answers_or_unsolved_dialogue(self):
        chapters = public_chapters()
        prologue = chapters[0]
        document = block_of_type(prologue, "document")["content"]
        opening = prologue["blocks"][0]
        self.assertEqual(document["signature"], "遠藤美咲")
        self.assertIn("佐々木笑真", "".join(document["body"]))
        self.assertIn("御厨水産の寿司", opening["messages"][0]["text"])
        self.assertIn("この手紙を出した", "".join(document["body"]))
        self.assertNotIn("ここに来た", "".join(document["body"]))

        for chapter in chapters:
            self.assertNotIn("_question_ids", chapter)
            for question in questions_in(chapter):
                for key in ("accepted", "validation", "required_terms", "chapter_id"):
                    self.assertNotIn(key, question)
                self.assertNotIn("dialogue", [block["type"] for block in question["blocks"]])
        self.assertEqual(chapters[1]["blocks"], [])


class ContentFileTest(unittest.TestCase):
    def test_manifest_splits_one_chapter_per_file(self):
        manifest = json.loads(CHAPTERS_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["chapter_files"]), 7)
        chapter_ids = []
        for filename in manifest["chapter_files"]:
            data = json.loads((CHAPTERS_MANIFEST_PATH.parent / filename).read_text(encoding="utf-8"))
            self.assertEqual(set(data), {"version", "chapter"})
            chapter_ids.append(data["chapter"]["id"])
        self.assertEqual(chapter_ids, [chapter["id"] for chapter in CHAPTERS])

    def test_chapter_files_contain_no_answer_configuration(self):
        manifest = json.loads(CHAPTERS_MANIFEST_PATH.read_text(encoding="utf-8"))
        for filename in manifest["chapter_files"]:
            source = (CHAPTERS_MANIFEST_PATH.parent / filename).read_text(encoding="utf-8")
            for key in ('"accepted"', '"validation"', '"required_terms"'):
                self.assertNotIn(key, source)

    def test_dialogue_can_be_changed_only_in_chapter_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_chapters = Path(temp_dir) / "chapters"
            shutil.copytree(CHAPTERS_MANIFEST_PATH.parent, temp_chapters)
            prologue_path = temp_chapters / "prologue.json"
            prologue_data = json.loads(prologue_path.read_text(encoding="utf-8"))
            prologue_data["chapter"]["blocks"][2]["messages"][0]["text"] = "差し替えたセリフ"
            prologue_path.write_text(
                json.dumps(prologue_data, ensure_ascii=False), encoding="utf-8"
            )

            chapters, _ = load_content(temp_chapters / "manifest.json", ANSWERS_PATH)
            self.assertEqual(chapters[0]["blocks"][2]["messages"][0]["text"], "差し替えたセリフ")

    def test_blocks_define_display_order_and_renderer(self):
        self.assertEqual(
            [block["type"] for block in CHAPTERS[0]["blocks"][:3]],
            ["dialogue", "document", "dialogue"],
        )
        app_dir = CHAPTERS_MANIFEST_PATH.parent.parent.parent
        template = (app_dir / "templates" / "index.html").read_text(encoding="utf-8")
        script = (app_dir / "static" / "notebook.js").read_text(encoding="utf-8")
        self.assertIn('id="chapter-blocks"', template)
        self.assertNotIn('id="opening-scene"', template)
        self.assertIn("const blockRenderers", script)
        self.assertIn("renderBlocks(chapter.blocks", script)

    def test_public_site_address_and_scan_ip_are_both_explained(self):
        opening = CHAPTERS[1]["blocks"][0]
        dialogue = "".join(message["text"] for message in opening["messages"])
        self.assertIn("http://www.mikuriya-suisan.local/", dialogue)
        self.assertIn("172.30.0.10", dialogue)

    def test_missing_answer_configuration_has_clear_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            answers_data = json.loads(ANSWERS_PATH.read_text(encoding="utf-8"))
            answers_data["answers"].pop("prologue_requester")
            answers_path = Path(temp_dir) / "answers.json"
            answers_path.write_text(
                json.dumps(answers_data, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ContentConfigurationError,
                "prologue_requester の正解設定がありません",
            ):
                load_content(CHAPTERS_MANIFEST_PATH, answers_path)


class ProgressStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["NOTEBOOK_DB_PATH"] = str(Path(self.temp_dir.name) / "progress.db")
        initialize_database()

    def tearDown(self):
        os.environ.pop("NOTEBOOK_DB_PATH", None)
        self.temp_dir.cleanup()

    def test_chapters_unlock_in_order(self):
        progress = get_progress(CHAPTERS)
        self.assertEqual(progress["unlocked_chapter_ids"], ["prologue"])

        save_answer("prologue_requester", "遠藤美咲")
        save_answer("prologue_missing", "佐々木笑真")
        progress = get_progress(CHAPTERS)
        self.assertEqual(progress["unlocked_chapter_ids"], ["prologue", "chapter-1"])
        self.assertIn("prologue", progress["completed_chapter_ids"])

        for question_id in CHAPTERS[1]["_question_ids"]:
            save_answer(question_id, "test")
        progress = get_progress(CHAPTERS)
        self.assertEqual(
            progress["unlocked_chapter_ids"],
            ["prologue", "chapter-1", "chapter-2"],
        )

    def test_note_is_persisted_and_acknowledged(self):
        save_note("prologue", "依頼書を確認した。", acknowledged=True)
        progress = get_progress(CHAPTERS)
        self.assertEqual(progress["notes"]["prologue"]["content"], "依頼書を確認した。")
        self.assertIn("prologue", progress["acknowledged_note_chapter_ids"])


if __name__ == "__main__":
    unittest.main()
