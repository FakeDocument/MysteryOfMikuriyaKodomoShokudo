"""撮影するKaliのコマンドを、作中の日時（2026年9月10日 午後・日本時間）で動かす。

撮影した日の時計がコマンドの出力（nmapの開始時刻、dirbのSTART_TIMEなど）に出ないよう、
libfaketimeで時計だけを作中の日時に合わせる。出力の文面は書き換えない。
faketimeは撮影のときだけ、起動中のKaliコンテナへ入れる（イメージは変えない）。
"""

from __future__ import annotations

import shlex
import subprocess

KALI = "sushictf-kali"
STORY_TZ = "Asia/Tokyo"
# 物語の起点（序章）は2026年9月10日 13時00分。録画機の日時表示（vhs.OSD_DATE）と揃える
STORY_DAY = "2026-09-10"
LIBFAKETIME_GLOB = "/usr/lib/*/faketime/libfaketime.so.1"


def ensure_faketime() -> None:
    """Kaliコンテナにlibfaketimeがなければ入れる。"""
    script = (
        f"ls {LIBFAKETIME_GLOB} >/dev/null 2>&1 || "
        "(apt-get update -qq && apt-get install -y -qq --no-install-recommends faketime)"
    )
    subprocess.run(["docker", "exec", "--user", "root", KALI, "bash", "-lc", script], check=True)


def exports(clock: str) -> str:
    """作中の時刻 clock（例 '13:00:05'）から時計が進み始める環境変数を設定するシェル文。"""
    fake = shlex.quote(f"@{STORY_DAY} {clock}")
    return (
        f"export TZ={STORY_TZ} FAKETIME={fake} "
        f"LD_PRELOAD=$(ls {LIBFAKETIME_GLOB} | head -n 1);"
    )
