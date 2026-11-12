# /// script
# requires-python = ">=3.12"
# dependencies = ["numpy", "pillow", "imageio-ffmpeg", "budoux"]
# ///
"""PVの試作を書き出す。

    uv run promo/pv/build.py            # 動画を書き出す
    uv run promo/pv/build.py --stills   # 確認用の静止画だけ書き出す
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg
import numpy as np
from PIL import Image

import audio
import scene_hook
import scene_front
import scene_letter
import scene_office
import vhs
from pixel import FPS, OUT_H, OUT_W, upscale

OUT_DIR = Path(__file__).resolve().parent / "build"


@dataclass(frozen=True)
class Scene:
    name: str
    duration: float
    render: Callable[[float], np.ndarray]


SCENES = (
    Scene("hook", scene_hook.DURATION, scene_hook.render),
    Scene("letter", scene_letter.DURATION, scene_letter.render),
    Scene("office", scene_office.DURATION, scene_office.render),
    Scene("front", scene_front.DURATION, scene_front.render),
)


def scene_at(t: float) -> tuple[Scene, float, float]:
    start = 0.0
    for scene in SCENES:
        if t < start + scene.duration:
            return scene, t - start, start
        start += scene.duration
    last = SCENES[-1]
    return last, last.duration - 1e-6, start - last.duration


def total_duration() -> float:
    return sum(s.duration for s in SCENES)


def build_audio(path: Path) -> None:
    rng = np.random.default_rng(1)
    track = audio.silence(total_duration())
    audio.place(track, audio.room_tone(total_duration(), rng), 0.0)
    for start, end in scene_hook.writing_spans():
        audio.place(track, audio.pencil_scratch(end - start, rng), start)
    letter_start = scene_hook.DURATION
    for shot in scene_letter.SHOTS:
        audio.place(track, audio.square_blip((523.3, 392.0), 0.045), letter_start + shot.start)
    office_start = letter_start + scene_letter.DURATION
    # 吹き出しの文字送り音。話者ごとに高さを変える（主人公は高め、所長は低め）
    clips = {
        "pop": audio.square_blip((392.0, 587.3), 0.04, volume=0.10),
        "blip:player": audio.square_blip((880.0,), 0.022, volume=0.05),
        "blip:director": audio.square_blip((587.3,), 0.022, volume=0.05),
    }
    for t, kind in scene_office.audio_events():
        audio.place(track, clips[kind], office_start + t)
    front_start = office_start + scene_office.DURATION
    cues = scene_front.audio_cues()
    audio.place(track, audio.front_theme_tape(rng), front_start + cues["theme"])
    audio.place(track, audio.tape_hiss(total_duration(), rng), 0.0)
    audio.place(track, audio.square_blip((784.0, 1046.5), 0.05, volume=0.09), front_start + cues["sign"])
    audio.write_wav(path, track)


def final_frame(t: float, use_vhs: bool) -> np.ndarray:
    """場面を描いて出力解像度へ拡大し、必要ならVHSの劣化表現をかける。"""
    scene, local, _ = scene_at(t)
    frame = upscale(scene.render(local))
    return vhs.apply(frame, t) if use_vhs else frame


def write_stills(times: tuple[float, ...], use_vhs: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for t in times:
        img = Image.fromarray(final_frame(t, use_vhs))
        img.resize((OUT_W // 2, OUT_H // 2), Image.Resampling.NEAREST).save(
            OUT_DIR / f"still_{t:05.2f}.png"
        )


def write_video(path: Path, use_vhs: bool) -> None:
    OUT_DIR.mkdir(exist_ok=True)
    wav = OUT_DIR / "audio.wav"
    build_audio(wav)
    cmd = [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-",
        "-i", str(wav),
        "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
        str(path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    frames = int(round(total_duration() * FPS))
    for i in range(frames):
        proc.stdin.write(final_frame(i / FPS, use_vhs).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpegでの書き出しに失敗しました")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", action="store_true")
    parser.add_argument("--no-vhs", action="store_true", help="VHSの劣化表現をかけずに書き出す")
    args = parser.parse_args()
    use_vhs = not args.no_vhs
    if args.stills:
        write_stills((2.6, 8.0, 18.9, 21.6, 24.9), use_vhs)
        return
    write_video(OUT_DIR / "pv_intro_draft.mp4", use_vhs)


if __name__ == "__main__":
    main()
