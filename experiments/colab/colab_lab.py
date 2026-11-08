"""Colab用の小さな調査環境。説明と回答判定はノートブックから利用する。"""

from __future__ import annotations

import html
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any

from colab_render import dialogue_html, inline_html, markdown_html, set_site_links
from colab_web import SITES, Running, colab_url, start_proxy, start_relay

TARGET_IP = "172.30.0.10"
TARGET_HOST = "www.mikuriya-suisan.local"
TOOLS = (
    "nginx",
    "smbd",
    "smbpasswd",
    "smbclient",
    "nmap",
    "curl",
    "ip",
    "unshare",
    "nsenter",
)


def normalize(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value).casefold()).rstrip(
        "/"
    )


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(path)


class Lesson:
    def __init__(self, data: dict[str, Any], progress_path: Path) -> None:
        self.data = data
        self.questions = {question["id"]: question for question in data["questions"]}
        self.progress_path = progress_path
        self.answers: dict[str, dict[str, str]] = {}
        if progress_path.exists():
            self.restore(json.loads(progress_path.read_text(encoding="utf-8")))

    def _correct(self, question_id: str, values: dict[str, str]) -> bool:
        if question_id not in self.questions:
            raise ValueError("設問IDが見つかりません。")
        question = self.questions[question_id]
        field_ids = [field["id"] for field in answer_fields(question)]
        if not isinstance(values, dict) or set(values) != set(field_ids):
            raise ValueError("すべての回答欄を入力してください。")
        if not all(isinstance(value, str) for value in values.values()):
            raise ValueError("回答は文字列で入力してください。")
        answer = "\t".join(values[field] for field in field_ids)
        validation = question.get("validation", "one_of")
        if validation == "exact":
            return any(
                unicodedata.normalize("NFKC", answer.strip())
                == unicodedata.normalize("NFKC", accepted)
                for accepted in question["accepted"]
            )
        if validation == "contains_all":
            return all(
                normalize(term) in normalize(answer)
                for term in question["required_terms"]
            )
        return any(
            normalize(answer) == normalize(accepted)
            for accepted in question["accepted"]
        )

    def submit(self, question_id: str, values: dict[str, str]) -> bool:
        if not self._correct(question_id, values):
            return False
        updated = {**self.answers, question_id: dict(values)}
        write_json(self.progress_path, {"version": 1, "answers": updated})
        self.answers = updated
        return True

    def is_solved(self, question_id: str) -> bool:
        return question_id in self.answers

    def follow_up(self, question_id: str) -> str:
        if not self.is_solved(question_id):
            return ""
        return "".join(
            self.render_block(block, question_id)
            for block in self.questions[question_id]["blocks"]
            if block["type"] == "dialogue"
        )

    def visible(self, block: dict[str, Any], question_id: str | None = None) -> bool:
        condition = block.get("visible_when")
        if not condition:
            return True
        if condition["event"] == "question_solved":
            return self.is_solved(question_id)
        if condition["event"] == "questions_solved":
            return all(
                self.is_solved(identifier) for identifier in condition["question_ids"]
            )
        raise ValueError("未対応の表示条件です。")

    def chapter_open(self, chapter_id: str) -> bool:
        for chapter in self.data.get("chapters", []):
            if chapter["id"] == chapter_id:
                return True
            if not all(
                self.is_solved(question["id"])
                for block in chapter["blocks"]
                if block["type"] == "questions"
                for question in block["items"]
            ):
                return False
        return False

    def question_open(self, question_id: str) -> bool:
        if "chapters" not in self.data:
            return True
        return any(
            self.chapter_open(chapter["id"]) and self.visible(block)
            for chapter in self.data["chapters"]
            for block in chapter["blocks"]
            if block["type"] == "questions"
            and any(q["id"] == question_id for q in block["items"])
        )

    def render_block(
        self, block: dict[str, Any], question_id: str | None = None
    ) -> str:
        if not self.visible(block, question_id):
            return ""
        heading = block.get("heading", {})
        result = (
            (
                "<header><small>"
                + html.escape(heading.get("kicker", ""))
                + "</small><h3>"
                + html.escape(heading.get("number", ""))
                + " "
                + html.escape(heading["title"])
                + "</h3></header>"
            )
            if heading
            else ""
        )
        kind = block["type"]
        if kind == "dialogue":
            return result + dialogue_html(
                block["messages"],
                self.data["speakers"],
                self.progress_path.parent / "images",
            )
        if kind == "document":
            content = block["content"]
            result += "<article>" + "".join(
                "<p>" + markdown_html(content.get(key, "")) + "</p>"
                for key in ("kicker", "title")
            )
            result += "".join(
                "<p>" + markdown_html(line) + "</p>" for line in content["body"]
            )
            return (
                result
                + "".join(
                    "<p>" + markdown_html(content.get(key, "")) + "</p>"
                    for key in ("received_stamp", "date", "signature")
                )
                + "</article>"
            )
        if kind == "report":
            result += "<h4>" + inline_html(block["subject"]) + "</h4><dl>"
            result += "".join(
                "<dt>"
                + inline_html(item["label"])
                + "</dt><dd>"
                + inline_html(item["value"])
                + "</dd>"
                for item in block["items"]
            )
            return result + "</dl><p>" + inline_html(block["conclusion"]) + "</p>"
        if kind == "hints":
            return (
                "<details><summary>ヒント</summary>"
                + "".join(
                    "<p>" + markdown_html(item) + "</p>" for item in block["items"]
                )
                + "</details>"
            )
        if kind == "questions":
            return result
        raise ValueError(f"未対応のブロック種別です: {kind}")

    def restore(self, progress: dict[str, Any]) -> None:
        if not isinstance(progress, dict) or not isinstance(
            progress.get("answers"), dict
        ):
            raise TypeError("進捗ファイルの形式が不正です。")
        answers = progress["answers"]
        if not all(
            self._correct(question, values) for question, values in answers.items()
        ):
            raise ValueError("進捗ファイルに不正な回答があります。")
        write_json(self.progress_path, {"version": 1, "answers": answers})
        self.answers = {question: dict(values) for question, values in answers.items()}


def answer_fields(question: dict[str, Any]) -> list[dict[str, Any]]:
    return question.get(
        "answer_fields",
        [
            {
                "id": "answer",
                "label": "回答",
                "input_mode": question.get("input_mode", "text"),
            }
        ],
    )


def process_identity(pid: int) -> str:
    # PIDの再利用で別のプロセスを停止しないよう、起動時刻も照合する。
    stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return stat[19]


def active_worker(root: Path) -> int:
    record = json.loads((root / "process.json").read_text())
    pid = record["pid"]
    if process_identity(pid) != record["started"]:
        raise ProcessLookupError("調査環境のプロセスが終了しています。")
    command = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
    if str(root).encode() not in command or os.getpgid(pid) != pid:
        raise ProcessLookupError("調査環境のプロセスを確認できません。")
    return pid


def namespace_command(root: Path, tool: str, arguments: list[str]) -> list[str]:
    executable = shutil.which(tool, path="/usr/sbin:/usr/bin:/sbin:/bin")
    if executable is None:
        raise RuntimeError(f"必要なコマンドがありません: {tool}")
    prefix = [
        "/usr/bin/nsenter",
        "--user",
        "--net",
        "--target",
        str(active_worker(root)),
        "--",
    ]
    extra = ["--unprivileged"] if tool == "nmap" else []
    return [*prefix, executable, *extra, *arguments]


def exec_tool(root: Path, tool: str, arguments: list[str]) -> None:
    command = namespace_command(root, tool, arguments)
    os.execv(command[0], command)


class Lab:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.lesson = Lesson(
            json.loads((root / "lesson.json").read_text()), root / "progress.json"
        )
        self.process: subprocess.Popen | None = None
        self.web: tuple[Running, ...] = ()

    def install_tools(self) -> None:
        if sys.platform != "linux" or os.geteuid() != 0:
            raise RuntimeError("この試作はColabのLinuxランタイムで実行してください。")
        if all(
            shutil.which(tool, path="/usr/sbin:/usr/bin:/sbin:/bin") for tool in TOOLS
        ):
            return
        policy = Path("/usr/sbin/policy-rc.d")
        created = not policy.exists()
        if created:
            policy.write_text("#!/bin/sh\nexit 101\n")
            policy.chmod(0o755)
        try:
            print("調査ツールを準備しています。初回は数分かかります。")
            with (self.root / "install.log").open("w") as log:
                for arguments in (
                    ["apt-get", "update", "-qq"],
                    [
                        "apt-get",
                        "install",
                        "-y",
                        "-qq",
                        "--no-install-recommends",
                        "nginx",
                        "samba",
                        "smbclient",
                        "nmap",
                        "curl",
                        "iproute2",
                        "util-linux",
                    ],
                ):
                    subprocess.run(
                        arguments,
                        check=True,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        env={**os.environ, "DEBIAN_FRONTEND": "noninteractive"},
                    )
        except subprocess.CalledProcessError as error:
            raise RuntimeError(
                (self.root / "install.log").read_text()[-4000:]
            ) from error
        finally:
            if created:
                policy.unlink()

    def _configure(self) -> None:
        for directory in ("bin", "run", "lock", "state", "cache", "private", "ncalrpc"):
            (self.root / directory).mkdir(exist_ok=True)
        (self.root / "private").chmod(0o700)
        nginx = (
            f"pid {self.root}/run/nginx.pid; error_log {self.root}/nginx.log;\n"
            "events {} http { include /etc/nginx/mime.types; access_log off;\n"
            f"server {{ listen {TARGET_IP}:80 default_server; root {self.root}/site; "
            "index index.html; charset utf-8; location / { try_files $uri $uri/ =404; } }\n"
            # 社内Webメールは未移植のため、寿司屋HPを誤って表示しない。
            f"server {{ listen {TARGET_IP}:80; server_name mail.mikuriya-suisan.local; "
            "return 404; } }\n"
        )
        (self.root / "nginx.conf").write_text(nginx)
        samba = (
            (self.root / "smb.conf.in")
            .read_text()
            .replace("/srv/samba/staff", str(self.root / "share"))
        )
        additions = (
            f"interfaces = {TARGET_IP}/32\nbind interfaces only = yes\n"
            + "\n".join(
                f"{key} = {self.root / directory}"
                for key, directory in (
                    ("lock directory", "lock"),
                    ("state directory", "state"),
                    ("cache directory", "cache"),
                    ("private dir", "private"),
                    ("pid directory", "run"),
                    ("ncalrpc dir", "ncalrpc"),
                )
            )
            + f"\nlog file = {self.root}/samba.log\n"
        )
        (self.root / "smb.conf").write_text(
            samba.replace("[global]", "[global]\n" + additions)
        )
        self._prepare_account()

    def _prepare_account(self) -> None:
        account = json.loads((self.root / "account.json").read_text())
        username = account["username"]
        import pwd

        try:
            pwd.getpwnam(username)
        except KeyError:
            subprocess.run(
                [
                    "useradd",
                    "--system",
                    "--no-create-home",
                    "--shell",
                    "/usr/sbin/nologin",
                    username,
                ],
                check=True,
            )
        subprocess.run(
            ["smbpasswd", "-c", str(self.root / "smb.conf"), "-a", "-s", username],
            input=f"{account['password']}\n{account['password']}\n",
            text=True,
            stdout=subprocess.DEVNULL,
            check=True,
        )

    def start(self) -> None:
        self.stop()
        self._configure()
        ready = self.root / "ready"
        ready.unlink(missing_ok=True)
        # rootが親名前空間でUID/GIDを対応付けてから、子のサービスを起動する。
        script = 'kill -STOP $$; exec "$1" "$2" --worker "$3"'
        with (self.root / "startup.log").open("w") as log:
            self.process = subprocess.Popen(
                [
                    "unshare",
                    "--user",
                    "--net",
                    "sh",
                    "-c",
                    script,
                    "sh",
                    sys.executable,
                    __file__,
                    str(self.root),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        pid = self.process.pid
        write_json(
            self.root / "process.json", {"pid": pid, "started": process_identity(pid)}
        )
        try:
            self._map_user(pid)
            os.kill(pid, signal.SIGCONT)
            for _ in range(200):
                if self.process.poll() is not None:
                    raise RuntimeError((self.root / "startup.log").read_text()[-4000:])
                if ready.exists():
                    self._register_commands()
                    self._open_sites()
                    print("準備ができました。コードセルから調査を始められます。")
                    return
                time.sleep(0.1)
            raise RuntimeError(
                "サービスの起動が完了しませんでした。startup.logを確認してください。"
            )
        except BaseException:
            self.stop()
            raise

    def _open_sites(self) -> None:
        # ブラウザから標的サイトを開けるよう、サイトごとの中継とURLを用意する。
        self.web = tuple(
            start_proxy(site.origin, site.socket_path(self.root), site.local_port)
            for site in SITES
        )
        set_site_links({site.origin: colab_url(site.local_port) for site in SITES})

    def _close_sites(self) -> None:
        set_site_links({})
        for proxy in self.web:
            proxy.close()
        self.web = ()

    def _map_user(self, pid: int) -> None:
        for _ in range(200):
            if self.process.poll() is not None:
                raise RuntimeError((self.root / "startup.log").read_text()[-4000:])
            if (
                Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
                == "T"
            ):
                for kind in ("uid_map", "gid_map"):
                    Path(f"/proc/{pid}/{kind}").write_text("0 0 65536\n")
                return
            time.sleep(0.02)
        raise RuntimeError("ネットワークの準備が完了しませんでした。")

    def _register_commands(self) -> None:
        hosts = Path("/etc/hosts")
        previous = [
            line
            for line in hosts.read_text().splitlines()
            if not line.endswith("# mikuriya-colab")
        ]
        hosts.write_text(
            "\n".join([*previous, f"{TARGET_IP} {TARGET_HOST} # mikuriya-colab", ""])
        )
        for tool in ("nmap", "curl", "smbclient"):
            wrapper = self.root / "bin" / tool
            wrapper.write_text(
                f"#!{sys.executable}\nimport sys\nsys.path.insert(0, {str(self.root)!r})\n"
                "from pathlib import Path\nfrom colab_lab import exec_tool\n"
                f"exec_tool(Path({str(self.root)!r}), {tool!r}, sys.argv[1:])\n"
            )
            wrapper.chmod(0o755)
        path = str(self.root / "bin")
        os.environ["PATH"] = os.pathsep.join(
            [
                path,
                *[
                    part
                    for part in os.environ["PATH"].split(os.pathsep)
                    if part != path
                ],
            ]
        )

    def run(
        self, tool: str, *arguments: str, timeout: float = 90
    ) -> subprocess.CompletedProcess:
        return subprocess.run(
            namespace_command(self.root, tool, list(arguments)),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=True,
        )

    def ask(self, question_id: str, values: dict[str, str]) -> bool:
        """設問を表示し、回答欄が入力されていれば判定する。"""
        from IPython.display import HTML, display

        if not self.lesson.question_open(question_id):
            print("必要な設問に正解してから、このセルを再実行してください。")
            return False
        # 初回は設問を読むために実行されるため、空欄を誤答として扱わない。
        is_blank = not any(value.strip() for value in values.values())
        correct = (
            self.lesson.is_solved(question_id)
            if is_blank
            else self.lesson.submit(question_id, values)
        )
        markup = self._question_html(question_id)
        if correct:
            markup += (
                '<p style="color:#214d40;font-weight:bold">正解です。</p>'
                + self.lesson.follow_up(question_id)
            )
        display(HTML(markup))
        if correct:
            return True
        if is_blank:
            print("上の回答欄に入力し、このセルを再実行してください。")
        else:
            print(
                self.lesson.questions[question_id].get(
                    "incorrect_message",
                    "調査結果と一致しません。証拠をもう一度確認してください。",
                )
            )
        return False

    def show_block(self, chapter_id: str, block_id: str) -> None:
        from IPython.display import HTML, display

        chapter = next(
            chapter
            for chapter in self.lesson.data["chapters"]
            if chapter["id"] == chapter_id
        )
        block = next(block for block in chapter["blocks"] if block["id"] == block_id)
        if not self.lesson.chapter_open(chapter_id) or not self.lesson.visible(block):
            print("必要な設問に正解してから、このセルを再実行してください。")
            return
        display(HTML(self.lesson.render_block(block)))

    def _question_html(self, question_id: str) -> str:
        """ヒントを返す。設問文と入力形式はセルのフォームに、正解後の会話は follow_up が出す。"""
        question = self.lesson.questions[question_id]
        return "".join(
            self.lesson.render_block(block, question_id)
            for block in question["blocks"]
            if block["type"] != "dialogue"
        )

    def stop(self) -> None:
        self._close_sites()
        try:
            pid = active_worker(self.root)
        except (FileNotFoundError, ProcessLookupError):
            return
        os.killpg(pid, signal.SIGTERM)
        os.kill(pid, signal.SIGCONT)
        if self.process is not None and self.process.pid == pid:
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(pid, signal.SIGKILL)
                self.process.wait(timeout=3)
        else:
            for _ in range(30):
                try:
                    active_worker(self.root)
                except (FileNotFoundError, ProcessLookupError):
                    break
                time.sleep(0.1)
            else:
                os.killpg(pid, signal.SIGKILL)
        (self.root / "process.json").unlink(missing_ok=True)
        (self.root / "ready").unlink(missing_ok=True)


def serve(root: Path) -> None:
    subprocess.run(["ip", "link", "set", "lo", "up"], check=True)
    subprocess.run(["ip", "address", "add", f"{TARGET_IP}/32", "dev", "lo"], check=True)
    commands = (
        ["nginx", "-c", str(root / "nginx.conf"), "-g", "daemon off;"],
        [
            "smbd",
            "--foreground",
            "--no-process-group",
            "--debug-stdout",
            "--configfile=" + str(root / "smb.conf"),
        ],
    )
    processes: list[subprocess.Popen] = []
    relays: list[Running] = []

    def shutdown(_signal: int, _frame: Any) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    try:
        # カーネル側の中継が、このネットワーク内の標的サイトへ届くようにする。
        relays.extend(
            start_relay(site.socket_path(root), site.address, site.port)
            for site in SITES
        )
        # smbdは標準入力がEOFになると終了するため、監督プロセスがパイプを保持する。
        for command in commands:
            processes.append(
                subprocess.Popen(command, stdin=subprocess.PIPE, start_new_session=True)
            )
        for _ in range(200):
            if any(process.poll() is not None for process in processes):
                nginx_log = (
                    (root / "nginx.log").read_text()
                    if (root / "nginx.log").exists()
                    else ""
                )
                failed = [
                    (command[0], process.returncode)
                    for command, process in zip(commands, processes)
                    if process.poll() is not None
                ]
                raise RuntimeError(
                    f"標的サービスが停止しました: {failed}\n" + nginx_log[-3000:]
                )
            try:
                for port in (80, 445):
                    with socket.create_connection((TARGET_IP, port), timeout=0.1):
                        pass
            except OSError:
                time.sleep(0.1)
                continue
            (root / "ready").touch()
            break
        else:
            raise RuntimeError("標的サービスの接続確認に失敗しました。")
        while True:
            if any(process.poll() is not None for process in processes):
                raise RuntimeError("標的サービスが停止しました。")
            time.sleep(0.25)
    finally:
        for relay in relays:
            relay.close()
        for process in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
            if process.stdin is not None:
                process.stdin.close()


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        serve(Path(sys.argv[2]))
