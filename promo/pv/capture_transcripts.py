"""PVの端末のカットに使う、コマンドの実際の出力を記録する。

ローカルの調査環境（docker compose）を起動した状態で実行する。

    uv run promo/pv/capture_transcripts.py

Kaliコンテナでコマンドを実行し、出力を promo/pv/assets/terminal/*.json に保存する。
PVの端末は、この記録をそのまま描く（出力の文面は書き換えない）。
時計は作中の日時に合わせて実行する（story_clock.py）。
smbclientは対話の画面を描くため、対話のときに出る行と ls の出力を、実際の表示と同じ順に並べる。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import story_clock

OUT_DIR = Path(__file__).resolve().parent / "assets/terminal"
KALI = story_clock.KALI
TARGET = "www.mikuriya-suisan.local"
KANZAKI_PASSWORD = "Kanzaki2018"  # 第1章で導く神崎の初期パスワード（画面には出ない）


def run(command: str, clock: str = "13:00:00") -> list[str]:
    """作中の時刻 clock から時計が進む状態で、Kaliでコマンドを実行する。"""
    script = f"{story_clock.exports(clock)} cd ~ && {command}"
    result = subprocess.run(
        ["docker", "exec", "--user", "player", KALI, "bash", "-lc", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.rstrip("\n").split("\n")


def save(name: str, host: str, items: list[dict]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.json"
    path.write_text(json.dumps({"host": host, "items": items}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"保存: {path}")


def main() -> None:
    story_clock.ensure_faketime()
    host = run("hostname")[0]

    nmap = f"nmap -sV {TARGET}"
    save("nmap", host, [{"shell": nmap}, {"output": run(nmap, "13:00:05")}])

    dirb = f"dirb http://{TARGET}/ /usr/share/dirb/wordlists/common.txt -S -r"
    save("dirb", host, [{"shell": dirb}, {"output": run(dirb, "13:00:40")}])

    smb = f"smbclient //{TARGET}/staff -U kanzaki"
    listing = run(f"smbclient //{TARGET}/staff -U 'kanzaki%{KANZAKI_PASSWORD}' -c ls", "13:01:30")
    save(
        "smbclient",
        host,
        [
            {"shell": smb},
            # 対話で接続したときに、パスワード入力の前後に出る行
            {"output": ["Password for [WORKGROUP\\kanzaki]:", 'Try "help" to get a list of possible commands.']},
            {"prompt": "smb: \\> ", "input": "ls"},
            {"output": listing},
        ],
    )


if __name__ == "__main__":
    main()
