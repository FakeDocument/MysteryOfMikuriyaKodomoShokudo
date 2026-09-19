import asyncio
import json
import os
import shutil
import tempfile
import unittest
from datetime import datetime
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
from app.store import connect, get_progress, initialize_database, save_answer, save_note


def block_of_type(chapter, block_type):
    return next(block for block in chapter["blocks"] if block["type"] == block_type)


def questions_in(chapter):
    return [
        question
        for block in chapter["blocks"]
        if block["type"] == "questions"
        for question in block["items"]
    ]


class AnswerValidationTest(unittest.TestCase):
    def test_chapter_four_answers_follow_discovered_evidence(self):
        self.assertTrue(validate_answer(QUESTIONS_BY_ID["ch4_services"], "80\t8080\t445"))
        self.assertTrue(validate_answer(QUESTIONS_BY_ID["ch4_catalog_entry"], "E6N4-P9R2-T3M5"))
        self.assertFalse(validate_answer(QUESTIONS_BY_ID["ch4_catalog_entry"], "連絡調整係／9月連絡業務"))
        self.assertFalse(validate_answer(QUESTIONS_BY_ID["ch4_catalog_entry"], "E6N4-P9R2-T3M5\t連絡調整係／9月連絡業務"))
        self.assertTrue(validate_answer(QUESTIONS_BY_ID["ch4_anomaly"], "オオクチ様\t島食い"))
        self.assertFalse(validate_answer(QUESTIONS_BY_ID["ch4_anomaly"], "オオクチ様\t人身御供"))
        self.assertFalse(validate_answer(QUESTIONS_BY_ID["ch4_catalog_entry"], "katayanagi\tKatayanagi2021"))
        self.assertTrue(validate_answer(QUESTIONS_BY_ID["ch4_conservation_target"], "沖ノ鳥島\tEEZ"))
        self.assertFalse(validate_answer(QUESTIONS_BY_ID["ch4_conservation_target"], "沖ノ鳥島\tEEZ\t2026年9月11日 深夜1時"))
        self.assertTrue(validate_answer(QUESTIONS_BY_ID["ch4_file_share"], "handoff\tR-14"))
        self.assertFalse(validate_answer(QUESTIONS_BY_ID["ch4_file_share"], "handoff\thozen_sync"))
        final_evidence = QUESTIONS_BY_ID["ch4_handoff_schedule"]
        self.assertEqual(final_evidence["answer_fields"][0]["input_mode"], "datetime")
        self.assertTrue(validate_answer(final_evidence, "2026-09-11T01:00\t裏手の荷捌き所"))
        self.assertFalse(validate_answer(final_evidence, "2026-09-11T01:00\t御厨水産 裏手の荷捌き所"))
        self.assertFalse(validate_answer(final_evidence, "2026年9月11日 深夜1時\t裏手の荷捌き所"))
        self.assertFalse(validate_answer(final_evidence, "沖ノ鳥島\tEEZ"))

    def test_japanese_name_accepts_spacing_and_kana(self):
        question = QUESTIONS_BY_ID["prologue_requester"]
        self.assertTrue(validate_answer(question, " 遠藤　美咲 "))
        self.assertTrue(validate_answer(question, "エンドウミサキ"))

    def test_password_is_case_sensitive(self):
        question = QUESTIONS_BY_ID["ch1_samba_credentials"]
        self.assertTrue(validate_answer(question, "kanzaki\tKanzaki2019"))
        self.assertFalse(validate_answer(question, "kanzaki\tkanzaki2019"))

    def test_past_person_accepts_name_variants(self):
        question = QUESTIONS_BY_ID["ch2_past_person"]
        self.assertTrue(validate_answer(question, "宮田 奏太"))
        self.assertTrue(validate_answer(question, "ミヤタソウタ"))
        self.assertFalse(validate_answer(question, "佐々木笑真"))

    def test_next_access_requires_url_and_login_id(self):
        question = QUESTIONS_BY_ID["ch2_next_access"]
        self.assertTrue(
            validate_answer(
                question,
                "http://mail.mikuriya-suisan.local/\t"
                "hitomi.kanzaki@mikuriya-suisan.local",
            )
        )
        self.assertFalse(
            validate_answer(question, "hitomi.kanzaki@mikuriya-suisan.local")
        )

    def test_port_scan_answers_require_port_and_service_name(self):
        web = QUESTIONS_BY_ID["ch1_web_port_service"]
        samba = QUESTIONS_BY_ID["ch1_samba_port_service"]
        self.assertTrue(validate_answer(web, "80 http"))
        self.assertTrue(validate_answer(web, "80\thttp"))
        self.assertTrue(validate_answer(web, "80/tcp open http"))
        self.assertFalse(validate_answer(web, "80"))
        self.assertTrue(validate_answer(samba, "445 netbios-ssn"))
        self.assertTrue(validate_answer(samba, "445\tnetbios-ssn"))
        self.assertTrue(validate_answer(samba, "445/tcp open netbios-ssn"))
        self.assertFalse(validate_answer(samba, "445"))

    def test_hidden_directory_answer_requires_both_results(self):
        question = QUESTIONS_BY_ID["ch1_hidden_directories"]
        self.assertTrue(validate_answer(question, "/admin/\t/backup/"))
        self.assertTrue(validate_answer(question, "/backup/\t/admin/"))
        self.assertFalse(validate_answer(question, "/admin/"))

    def test_samba_share_answer_matches_discovered_share(self):
        question = QUESTIONS_BY_ID["ch2_samba_share"]
        self.assertTrue(validate_answer(question, "staff"))
        self.assertFalse(validate_answer(question, "IPC$"))

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
    def test_chapter_four_allows_catalog_after_port_scan(self):
        def chapter_four_with(solved_question_ids):
            progress = {
                "solved_question_ids": solved_question_ids,
                "unlocked_chapter_ids": [
                    "prologue", "chapter-1", "chapter-2", "chapter-3", "chapter-4"
                ],
            }
            return public_chapters(progress)[4]

        self.assertEqual(
            [question["id"] for question in questions_in(chapter_four_with([]))],
            ["ch4_services"],
        )
        self.assertEqual(
            [question["id"] for question in questions_in(chapter_four_with(["ch4_services"]))],
            ["ch4_services", "ch4_catalog_entry"],
        )
        catalog_question = questions_in(chapter_four_with(["ch4_services"]))[1]
        self.assertNotIn("answer_fields", catalog_question)
        self.assertIn("共有一覧", catalog_question["prompt"])
        self.assertIn("-N", "".join(catalog_question["blocks"][0]["items"]))
        solved = ["ch4_services", "ch4_catalog_entry", "ch4_anomaly"]
        self.assertEqual(
            [question["id"] for question in questions_in(chapter_four_with(solved))],
            solved + ["ch4_conservation_target"],
        )
        solved.append("ch4_conservation_target")
        self.assertEqual(
            [question["id"] for question in questions_in(chapter_four_with(solved))],
            solved + ["ch4_file_share"],
        )
        solved.append("ch4_file_share")
        self.assertEqual(
            [question["id"] for question in questions_in(chapter_four_with(solved))],
            solved + ["ch4_handoff_schedule"],
        )

    def test_finale_shows_report_and_call_without_repeating_questions(self):
        locked = public_chapters({
            "solved_question_ids": [],
            "unlocked_chapter_ids": ["prologue", "chapter-1", "chapter-2", "chapter-3", "chapter-4"],
        })[5]
        self.assertEqual(locked["blocks"], [])

        open_finale = public_chapters({
            "solved_question_ids": ["ch4_handoff_schedule"],
            "unlocked_chapter_ids": [
                "prologue", "chapter-1", "chapter-2", "chapter-3", "chapter-4", "finale"
            ],
        })[5]
        self.assertEqual([block["id"] for block in open_finale["blocks"]],
                         ["completed-report", "final-call"])
        self.assertEqual(questions_in(open_finale), [])
        report = open_finale["blocks"][0]
        self.assertIn("裏手の荷捌き所", "".join(item["value"] for item in report["items"]))

    def test_framework_documentation_routes_are_disabled(self):
        from app.main import app

        paths = {route.path for route in app.routes}
        self.assertNotIn("/docs", paths)
        self.assertNotIn("/redoc", paths)
        self.assertNotIn("/openapi.json", paths)

    def test_manifest_splits_one_chapter_per_file(self):
        manifest = json.loads(CHAPTERS_MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(manifest["chapter_files"]), 6)
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

    def test_player_commands_use_markdown_code_blocks(self):
        chapter_one = json.dumps(CHAPTERS[1], ensure_ascii=False)
        chapter_two = json.dumps(CHAPTERS[2], ensure_ascii=False)
        chapter_three = json.dumps(CHAPTERS[3], ensure_ascii=False)
        chapter_four = json.dumps(CHAPTERS[4], ensure_ascii=False)

        self.assertIn("```sh\\nnmap -sV www.mikuriya-suisan.local\\n```", chapter_one)
        self.assertIn("```sh\\ndirb http://www.mikuriya-suisan.local/", chapter_one)
        self.assertIn(
            "```sh\\nsmbclient -L //www.mikuriya-suisan.local -U kanzaki\\n```",
            chapter_two,
        )
        self.assertIn("```text\\n' OR 1=1 -- \\n```", chapter_three)
        self.assertIn(
            "```sh\\nsmbclient -L //kaiiki-hozen.local -N\\n```",
            chapter_four,
        )

    def test_public_site_domain_is_used_for_service_scan(self):
        opening = CHAPTERS[1]["blocks"][0]
        dialogue = "".join(message["text"] for message in opening["messages"])
        self.assertIn("http://www.mikuriya-suisan.local/", dialogue)
        self.assertIn("nmap -sV www.mikuriya-suisan.local", dialogue)
        self.assertNotIn("172.30.0.10", dialogue)

    def test_chapter_one_dialogue_links_to_investigation_terminal(self):
        opening = CHAPTERS[1]["blocks"][0]
        terminal_message = next(
            message for message in opening["messages"] if "link" in message
        )
        self.assertEqual(terminal_message["link"]["label"], "調査端末を開く")
        self.assertEqual(
            terminal_message["link"]["href"],
            "http://127.0.0.1:6901/vnc.html?autoconnect=true&reconnect=true&reconnect_delay=5000",
        )

        app_dir = CHAPTERS_MANIFEST_PATH.parent.parent.parent
        script = (app_dir / "static" / "notebook.js").read_text(encoding="utf-8")
        self.assertIn('link.rel = "noopener noreferrer"', script)

    def test_chapter_one_explains_first_tools_for_beginners(self):
        chapter = CHAPTERS[1]
        opening_dialogue = "".join(
            message["text"] for message in chapter["blocks"][0]["messages"]
        )
        for expected in (
            "接続用パスワードは 99",
            "nmap -sV www.mikuriya-suisan.local",
            "PORT",
            "STATE",
            "SERVICE",
        ):
            self.assertIn(expected, opening_dialogue)

        questions = questions_in(chapter)
        for question in questions[:2]:
            self.assertEqual(
                [field["label"] for field in question["answer_fields"]],
                ["ポート番号", "サービス名"],
            )
            self.assertNotIn("placeholder", question)
            self.assertNotIn("input_mode", question)

        web_hints = "".join(questions[0]["blocks"][0]["items"])
        samba_hints = "".join(questions[1]["blocks"][0]["items"])
        web_follow_up = "".join(
            message["text"] for message in questions[0]["blocks"][1]["messages"]
        )
        samba_follow_up = "".join(
            message["text"] for message in questions[1]["blocks"][1]["messages"]
        )
        self.assertIn("80/tcp  open  http", web_hints)
        self.assertIn("HTTPは", web_follow_up)
        self.assertIn("Webページ", web_follow_up)
        self.assertIn("445/tcp  open  netbios-ssn", samba_hints)
        self.assertIn("Samba smbd 4", samba_hints)
        self.assertIn("ファイル共有サービス", samba_follow_up)
        self.assertNotIn("microsoft-ds", opening_dialogue + web_hints + samba_hints)

        directory_question = questions[2]
        self.assertEqual(
            [field["label"] for field in directory_question["answer_fields"]],
            ["ディレクトリ 1", "ディレクトリ 2"],
        )
        dirb_hints = "".join(directory_question["blocks"][0]["items"])
        self.assertIn("==> DIRECTORY:", dirb_hints)
        self.assertIn("`+` はファイル", dirb_hints)
        self.assertIn("`assets/`", dirb_hints)
        self.assertIn("公開メニュー", directory_question["prompt"] + dirb_hints)
        self.assertIn("スタッフ向けの管理画面", dirb_hints)

        directory_follow_up = "".join(
            message["text"] for message in directory_question["blocks"][1]["messages"]
        )
        self.assertIn("/admin/", directory_follow_up)
        self.assertIn("/backup/", directory_follow_up)

        terminal_message = next(
            message for message in chapter["blocks"][0]["messages"] if "image" in message
        )
        self.assertEqual(
            terminal_message["image"]["src"],
            "/static/images/tutorial-terminal.png",
        )
        app_dir = CHAPTERS_MANIFEST_PATH.parent.parent.parent
        image_path = app_dir / terminal_message["image"]["src"].removeprefix("/")
        self.assertTrue(image_path.is_file())

        script = (app_dir / "static" / "notebook.js").read_text(encoding="utf-8")
        self.assertIn('image.loading = "lazy"', script)
        self.assertIn("data-answer-part", script)
        self.assertIn('.join("\\t")', script)

    def test_chapter_one_sections_unlock_in_order_and_bridge_is_standalone(self):
        def chapter_one_with(solved_question_ids):
            progress = {
                "solved_question_ids": solved_question_ids,
                "unlocked_chapter_ids": ["prologue", "chapter-1"],
            }
            return public_chapters(progress)[1]

        web_only = chapter_one_with(["ch1_web_port_service"])
        samba_only = chapter_one_with(["ch1_samba_port_service"])
        both_solved = chapter_one_with(
            ["ch1_web_port_service", "ch1_samba_port_service"]
        )
        directory_solved = chapter_one_with(
            [
                "ch1_web_port_service",
                "ch1_samba_port_service",
                "ch1_hidden_directories",
            ]
        )

        self.assertEqual(
            [question["id"] for question in questions_in(web_only)],
            ["ch1_web_port_service", "ch1_samba_port_service"],
        )
        self.assertEqual(
            [question["id"] for question in questions_in(samba_only)],
            ["ch1_web_port_service", "ch1_samba_port_service"],
        )
        self.assertNotIn("after-service-scan", [block["id"] for block in web_only["blocks"]])
        self.assertNotIn("after-service-scan", [block["id"] for block in samba_only["blocks"]])

        self.assertEqual(
            [question["id"] for question in questions_in(both_solved)],
            [
                "ch1_web_port_service",
                "ch1_samba_port_service",
                "ch1_hidden_directories",
            ],
        )
        both_solved_block_ids = [block["id"] for block in both_solved["blocks"]]
        self.assertIn("after-service-scan", both_solved_block_ids)
        self.assertIn("directory-scan", both_solved_block_ids)
        self.assertNotIn("after-hidden-pages", both_solved_block_ids)
        self.assertNotIn("samba-credentials", both_solved_block_ids)

        self.assertEqual(
            [question["id"] for question in questions_in(directory_solved)],
            [
                "ch1_web_port_service",
                "ch1_samba_port_service",
                "ch1_hidden_directories",
                "ch1_samba_credentials",
            ],
        )
        self.assertIn(
            "after-hidden-pages",
            [block["id"] for block in directory_solved["blocks"]],
        )
        self.assertIn(
            "samba-credentials",
            [block["id"] for block in directory_solved["blocks"]],
        )

        transition = next(
            block
            for block in both_solved["blocks"]
            if block["id"] == "after-service-scan"
        )
        self.assertEqual(transition["type"], "dialogue")
        self.assertEqual(transition["heading"]["number"], "04")
        self.assertEqual(
            next(
                block
                for block in both_solved["blocks"]
                if block["id"] == "directory-scan"
            )["heading"]["number"],
            "05",
        )
        self.assertEqual(
            next(
                block
                for block in directory_solved["blocks"]
                if block["id"] == "after-hidden-pages"
            )["heading"]["number"],
            "06",
        )
        self.assertEqual(
            next(
                block
                for block in directory_solved["blocks"]
                if block["id"] == "samba-credentials"
            )["heading"]["number"],
            "07",
        )
        samba_question = next(
            question
            for question in questions_in(both_solved)
            if question["id"] == "ch1_samba_port_service"
        )
        self.assertNotIn(
            "after-service-scan",
            [block["id"] for block in samba_question["blocks"]],
        )
        dialogue = "".join(message["text"] for message in transition["messages"])
        self.assertIn("アカウントIDとパスワード", dialogue)
        self.assertIn("http://www.mikuriya-suisan.local/", dialogue)
        self.assertIn("DIRB", dialogue)
        self.assertIn("-S -r", dialogue)
        self.assertIn("公開メニューから開けるページ", dialogue)
        hidden_transition = next(
            block
            for block in directory_solved["blocks"]
            if block["id"] == "after-hidden-pages"
        )
        hidden_dialogue = "".join(
            message["text"] for message in hidden_transition["messages"]
        )
        self.assertIn("ブラウザで開き", hidden_dialogue)
        self.assertIn("公開ページ", hidden_dialogue)
        self.assertNotIn("Kanzaki", hidden_dialogue)
        self.assertNotIn("2019", hidden_dialogue)
        credential_questions = {
            question["id"]: question for question in questions_in(directory_solved)
        }
        credentials_question = credential_questions["ch1_samba_credentials"]
        credential_hints = "".join(credentials_question["blocks"][0]["items"])
        self.assertEqual(
            credentials_question["prompt"],
            "侵入できそうなアカウントのSamba認証情報を記録してください。",
        )
        self.assertEqual(
            [field["label"] for field in credentials_question["answer_fields"]],
            ["アカウントID", "初期パスワード"],
        )
        self.assertIn("入社年", credential_hints)
        directory_question = next(
            question
            for question in questions_in(directory_solved)
            if question["id"] == "ch1_hidden_directories"
        )
        follow_up = next(
            block for block in directory_question["blocks"] if block["type"] == "dialogue"
        )
        follow_up_dialogue = "".join(
            message["text"] for message in follow_up["messages"]
        )
        self.assertNotIn("ブラウザで開き", follow_up_dialogue)
        self.assertNotIn(
            "Kanzaki",
            follow_up_dialogue,
        )
        self.assertNotIn("Testing", dialogue)
        self.assertNotIn("==> DIRECTORY:", dialogue)

    def test_chapter_two_starts_with_samba_and_unlocks_discoveries_in_order(self):
        def chapter_two_with(solved_question_ids):
            progress = {
                "solved_question_ids": solved_question_ids,
                "unlocked_chapter_ids": ["prologue", "chapter-1", "chapter-2"],
            }
            return public_chapters(progress)[2]

        start = chapter_two_with([])
        share_solved = chapter_two_with(["ch2_samba_share"])
        past_person_solved = chapter_two_with(
            ["ch2_samba_share", "ch2_past_person"]
        )
        external_person_solved = chapter_two_with(
            [
                "ch2_samba_share",
                "ch2_past_person",
                "ch2_external_person",
            ]
        )

        opening_dialogue = "".join(
            message["text"] for message in start["blocks"][0]["messages"]
        )
        self.assertIn(
            "smbclient -L //www.mikuriya-suisan.local -U kanzaki",
            opening_dialogue,
        )
        self.assertIn("Unable to connect with SMB1", opening_dialogue)
        self.assertEqual(
            [question["id"] for question in questions_in(start)],
            ["ch2_samba_share"],
        )

        self.assertEqual(
            [question["id"] for question in questions_in(share_solved)],
            ["ch2_samba_share", "ch2_past_person"],
        )
        share_transition = next(
            block
            for block in share_solved["blocks"]
            if block["id"] == "after-share-discovery"
        )
        share_dialogue = "".join(
            message["text"] for message in share_transition["messages"]
        )
        self.assertIn(
            "smbclient //www.mikuriya-suisan.local/staff -U kanzaki",
            share_dialogue,
        )
        self.assertIn("`ls` で一覧表示", share_dialogue)
        self.assertIn("`cd ディレクトリ名`", share_dialogue)
        self.assertIn("`get ファイル名`", share_dialogue)
        for undiscovered_term in (
            "01_child_records",
            "sasaki_ema.txt",
            "宮田奏太",
            "片柳修治",
            "特別顧客",
            "提供",
            "Webメール",
            "mail.mikuriya-suisan.local",
        ):
            self.assertNotIn(undiscovered_term, share_dialogue)

        self.assertEqual(
            [question["id"] for question in questions_in(past_person_solved)],
            [
                "ch2_samba_share",
                "ch2_past_person",
                "ch2_external_person",
            ],
        )

        self.assertEqual(
            [question["id"] for question in questions_in(external_person_solved)],
            [
                "ch2_samba_share",
                "ch2_past_person",
                "ch2_external_person",
                "ch2_next_access",
            ],
        )

        question_by_id = {
            question["id"]: question for question in questions_in(external_person_solved)
        }
        self.assertEqual(
            [field["label"] for field in question_by_id["ch2_next_access"]["answer_fields"]],
            ["URL", "ログインID"],
        )

        prompts = {
            question_id: question_by_id[question_id]["prompt"]
            for question_id in (
                "ch2_past_person",
                "ch2_external_person",
                "ch2_next_access",
            )
        }
        for term in ("宮田", "笑真", "提供", "特別顧客", "01_child_records", ".txt"):
            self.assertNotIn(term, prompts["ch2_past_person"])
        for term in ("片柳", "政府", "国土保全庁", "顧客台帳"):
            self.assertNotIn(term, prompts["ch2_external_person"])
        for term in ("神崎", "Webメール", "mail.mikuriya-suisan.local", "03_staff_records"):
            self.assertNotIn(term, prompts["ch2_next_access"])

        chapter_intro = start["objective"] + start["lead"] + opening_dialogue
        for term in (
            "01_child_records",
            "宮田奏太",
            "片柳修治",
            "政府関係者",
            "mail.mikuriya-suisan.local",
        ):
            self.assertNotIn(term, chapter_intro)

        self.assertNotIn(
            "after-child-records",
            [block["id"] for block in past_person_solved["blocks"]],
        )
        self.assertNotIn(
            "after-customer-records",
            [block["id"] for block in external_person_solved["blocks"]],
        )

    def test_chapter_three_reveals_domain_in_order_and_chapter_four_keeps_destination_hidden(self):
        def chapter_three_with(solved_question_ids):
            progress = {
                "solved_question_ids": solved_question_ids,
                "unlocked_chapter_ids": [
                    "prologue",
                    "chapter-1",
                    "chapter-2",
                    "chapter-3",
                ],
            }
            return public_chapters(progress)[3]

        start = chapter_three_with([])
        self.assertEqual(
            [question["id"] for question in questions_in(start)],
            ["ch3_contact_email"],
        )
        self.assertTrue(
            validate_answer(
                QUESTIONS_BY_ID["ch3_contact_email"],
                "shuji.katayanagi@kaiiki-hozen.local",
            )
        )
        self.assertTrue(
            validate_answer(
                QUESTIONS_BY_ID["ch3_government_domain"],
                "kaiiki-hozen.local",
            )
        )

        email_solved = chapter_three_with(["ch3_contact_email"])
        self.assertEqual(
            [question["id"] for question in questions_in(email_solved)],
            ["ch3_contact_email", "ch3_government_domain"],
        )
        self.assertIn(
            "after-contact-email",
            [block["id"] for block in email_solved["blocks"]],
        )
        email_dialogue = "".join(
            message["text"]
            for block in email_solved["blocks"]
            if block["type"] == "dialogue"
            for message in block["messages"]
        )
        self.assertNotIn("第2章", email_dialogue)
        self.assertNotIn(
            "kaiiki-hozen.local",
            email_dialogue,
        )

        completed = chapter_three_with(
            ["ch3_contact_email", "ch3_government_domain"]
        )
        domain_question = next(
            question
            for question in questions_in(completed)
            if question["id"] == "ch3_government_domain"
        )
        self.assertIn(
            "kaiiki-hozen.local",
            "".join(
                message["text"]
                for block in domain_question["blocks"]
                if block["type"] == "dialogue"
                for message in block["messages"]
            ),
        )
        self.assertNotIn(
            "御厨水産を見てきます",
            json.dumps(CHAPTERS[3], ensure_ascii=False),
        )

        chapter_four_opening = CHAPTERS[4]["blocks"][0]
        chapter_four_dialogue = "".join(
            message["text"] for message in chapter_four_opening["messages"]
        )
        self.assertNotIn("御厨水産", chapter_four_dialogue)
        self.assertNotIn("昨日", chapter_four_dialogue)
        for instruction in ("nmap", "DIRB", "SQLインジェクション"):
            self.assertNotIn(instruction, chapter_four_dialogue)

        chapter_datetimes = []
        for chapter in CHAPTERS:
            chapter_datetimes.append(
                datetime.strptime(chapter["date"], "%Y年%m月%d日 %H時%M分")
            )
        self.assertEqual(1, len({value.date() for value in chapter_datetimes}))
        self.assertEqual(sorted(chapter_datetimes), chapter_datetimes)

        chapter_text = json.dumps(CHAPTERS[3], ensure_ascii=False)
        for obsolete_term in (
            "portal.kaiiki-hozen.local",
            "mikuriya-partner",
            "%X1AEFmvw",
        ):
            self.assertNotIn(obsolete_term, chapter_text)

    def test_multi_question_visibility_rejects_unknown_question(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_chapters = Path(temp_dir) / "chapters"
            shutil.copytree(CHAPTERS_MANIFEST_PATH.parent, temp_chapters)
            chapter_path = temp_chapters / "chapter-1.json"
            chapter_data = json.loads(chapter_path.read_text(encoding="utf-8"))
            transition = next(
                block
                for block in chapter_data["chapter"]["blocks"]
                if block["id"] == "after-service-scan"
            )
            transition["visible_when"]["question_ids"][1] = "missing_question"
            chapter_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ContentConfigurationError,
                "存在しない設問ID",
            ):
                load_content(temp_chapters / "manifest.json", ANSWERS_PATH)

    def test_multi_field_question_rejects_single_field_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_chapters = Path(temp_dir) / "chapters"
            shutil.copytree(CHAPTERS_MANIFEST_PATH.parent, temp_chapters)
            chapter_path = temp_chapters / "chapter-1.json"
            chapter_data = json.loads(chapter_path.read_text(encoding="utf-8"))
            port_scan = next(
                block
                for block in chapter_data["chapter"]["blocks"]
                if block["id"] == "port-scan"
            )
            port_scan["items"][0]["answer_fields"] = [
                {
                    "id": "port",
                    "label": "ポート番号",
                    "placeholder": "例: 80",
                    "input_mode": "numeric",
                }
            ]
            chapter_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(ContentConfigurationError, "2件以上"):
                load_content(temp_chapters / "manifest.json", ANSWERS_PATH)

    def test_dialogue_link_rejects_non_http_url(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_chapters = Path(temp_dir) / "chapters"
            shutil.copytree(CHAPTERS_MANIFEST_PATH.parent, temp_chapters)
            chapter_path = temp_chapters / "chapter-1.json"
            chapter_data = json.loads(chapter_path.read_text(encoding="utf-8"))
            chapter_data["chapter"]["blocks"][0]["messages"][0]["link"] = {
                "label": "危険なリンク",
                "href": "javascript:alert(1)",
            }
            chapter_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ContentConfigurationError,
                "http または https の完全なURL",
            ):
                load_content(temp_chapters / "manifest.json", ANSWERS_PATH)

    def test_dialogue_image_rejects_external_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_chapters = Path(temp_dir) / "chapters"
            shutil.copytree(CHAPTERS_MANIFEST_PATH.parent, temp_chapters)
            chapter_path = temp_chapters / "chapter-1.json"
            chapter_data = json.loads(chapter_path.read_text(encoding="utf-8"))
            chapter_data["chapter"]["blocks"][0]["messages"][0]["image"] = {
                "src": "https://example.com/tutorial.png",
                "alt": "外部画像",
            }
            chapter_path.write_text(
                json.dumps(chapter_data, ensure_ascii=False), encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ContentConfigurationError,
                "/static/images/ 配下",
            ):
                load_content(temp_chapters / "manifest.json", ANSWERS_PATH)

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

    def test_note_is_shared_across_all_chapters(self):
        save_note("依頼書を確認した。")
        progress = get_progress(CHAPTERS)
        self.assertEqual(progress["note"]["content"], "依頼書を確認した。")
        self.assertIsNotNone(progress["note"]["updated_at"])
        self.assertNotIn("notes", progress)
        self.assertNotIn("acknowledged_note_chapter_ids", progress)

    def test_legacy_chapter_notes_are_merged_into_shared_note(self):
        with connect() as connection:
            connection.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?)",
                ("prologue", "依頼書のメモ", 1, "2026-09-10T01:00:00+00:00"),
            )
            connection.execute(
                "INSERT INTO notes VALUES (?, ?, ?, ?)",
                ("chapter-1", "寿司屋のメモ", 1, "2026-09-10T02:00:00+00:00"),
            )

        progress = get_progress(CHAPTERS)
        self.assertEqual(progress["note"]["content"], "依頼書のメモ\n\n寿司屋のメモ")

    def test_shared_note_api_reads_writes_and_allows_clearing(self):
        from app.main import NoteSubmission, app, get_note, submit_note

        saved = asyncio.run(submit_note(NoteSubmission(content="全章共通のメモ")))
        self.assertTrue(saved["saved"])
        self.assertEqual(saved["note"]["content"], "全章共通のメモ")
        self.assertEqual(get_note()["content"], "全章共通のメモ")

        cleared = asyncio.run(submit_note(NoteSubmission(content="")))
        self.assertEqual(cleared["note"]["content"], "")
        note_methods = {
            method
            for route in app.routes
            if route.path == "/api/note"
            for method in route.methods
        }
        self.assertEqual(note_methods, {"GET", "PUT"})
        event_methods = {
            method
            for route in app.routes
            if route.path == "/api/note/events"
            for method in route.methods
        }
        self.assertEqual(event_methods, {"GET"})

    def test_note_publish_keeps_only_latest_pending_event(self):
        from app.main import NOTE_SUBSCRIBERS, publish_note

        queue = asyncio.Queue(maxsize=1)
        NOTE_SUBSCRIBERS.add(queue)
        try:
            publish_note({"content": "古いメモ"})
            publish_note({"content": "最新のメモ"})
            self.assertEqual(queue.get_nowait(), {"content": "最新のメモ"})
        finally:
            NOTE_SUBSCRIBERS.discard(queue)

    def test_finale_unlocks_after_chapter_four_final_answer(self):
        for chapter in CHAPTERS[:5]:
            for question_id in chapter["_question_ids"]:
                if question_id == "ch4_handoff_schedule":
                    continue
                save_answer(question_id, "preview")

        progress = get_progress(CHAPTERS)
        self.assertNotIn("finale", progress["unlocked_chapter_ids"])
        save_answer("ch4_handoff_schedule", "2026-09-11T01:00\t裏手の荷捌き所")

        progress = get_progress(CHAPTERS)
        self.assertIn("finale", progress["unlocked_chapter_ids"])
        self.assertIn("finale", progress["completed_chapter_ids"])
        self.assertIn("ch4_handoff_schedule", progress["solved_question_ids"])
        self.assertEqual(progress["total_questions"], 18)

    def test_retired_question_answer_is_ignored(self):
        save_answer("retired_question", "old answer")

        progress = get_progress(CHAPTERS)

        self.assertNotIn("retired_question", progress["answers"])
        self.assertNotIn("retired_question", progress["solved_question_ids"])
        self.assertEqual(progress["solved_count"], 0)


if __name__ == "__main__":
    unittest.main()
