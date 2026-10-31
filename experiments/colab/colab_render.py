"""Colabのセル出力向けに、章本文と顔つき会話をHTMLへ変換する。"""

from __future__ import annotations

import base64
import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def terminal_link(href: str) -> bool:
    parsed = urlsplit(href)
    return parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port == 6901


def inline_html(value: str) -> str:
    escaped = html.escape(value)
    return re.sub(
        r"`([^`\n]+)`|\*\*([^*\n]+)\*\*",
        lambda match: (
            f"<code>{match[1]}</code>"
            if match[1] is not None
            else f"<strong>{match[2]}</strong>"
        ),
        escaped,
    )


def markdown_html(value: str) -> str:
    output = []
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    code: list[str] | None = None
    language = ""
    continued = False
    for line in lines:
        fence = re.fullmatch(r"```([A-Za-z0-9_+-]*)\s*", line)
        if fence:
            if code is None:
                code = []
                language = fence[1]
                continued = False
            else:
                output.append(
                    '<pre style="overflow:auto;white-space:pre;line-height:1.6">'
                    + "<code>"
                    + html.escape("\n".join(code))
                    + "</code></pre>"
                )
                code = None
            continue
        if code is not None:
            command = line
            if language in {"sh", "bash", "shell"}:
                if (
                    line.strip()
                    and not line.lstrip().startswith(("!", "#"))
                    and not continued
                ):
                    command = "!" + line
                continued = line.rstrip().endswith("\\")
            code.append(command)
        else:
            output.append(inline_html(line) + "<br>")
    if code is not None:
        output.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
    return "".join(output)


def embedded_image(image_root: Path, filename: str, alt: str, style: str = "") -> str:
    encoded = base64.b64encode((image_root / Path(filename).name).read_bytes()).decode(
        "ascii"
    )
    return (
        f'<img src="data:image/png;base64,{encoded}" alt="{html.escape(alt)}" '
        f'style="{style}">'
    )


def dialogue_html(
    messages: list[dict[str, Any]], speakers: dict[str, Any], image_root: Path
) -> str:
    rows = []
    for message in messages:
        text = markdown_html(message["text"])
        if "link" in message:
            link = message["link"]
            if not link["href"].startswith(("https://", "http://")):
                raise ValueError("リンクはhttpまたはhttpsのURLにしてください。")
            if not terminal_link(link["href"]):
                text += (
                    f'<p><a href="{html.escape(link["href"])}" target="_blank" '
                    f'rel="noopener noreferrer">{html.escape(link["label"])}</a></p>'
                )
        if "image" in message:
            image = message["image"]
            text += "<figure>" + embedded_image(
                image_root, image["src"], image["alt"], "max-width:100%;height:auto"
            )
            text += (
                "<figcaption>"
                + html.escape(image.get("caption", ""))
                + "</figcaption></figure>"
            )
        if message["speaker"] == "narrator":
            rows.append(f'<div style="margin:20px 12px;line-height:1.9">{text}</div>')
            continue
        speaker = speakers[message["speaker"]]
        is_player = message["speaker"] == "player"
        direction = "row-reverse" if is_player else "row"
        margin = "16px 0 16px auto" if is_player else "16px auto 16px 0"
        name_alignment = "right" if is_player else "left"
        corners = "12px 0 12px 12px" if is_player else "0 12px 12px 12px"
        name = html.escape(speaker["name"])
        avatars = speaker.get("avatars", {})
        expression = message.get("expression", speaker.get("defaultExpression"))
        image_name = avatars.get(
            expression, avatars.get(speaker.get("defaultExpression"))
        )
        portrait = ""
        if image_name:
            portrait = embedded_image(
                image_root,
                image_name,
                speaker["name"],
                "width:88px;height:104px;object-fit:contain;flex:none;"
                "image-rendering:pixelated;background:#f4eedf;border-radius:8px",
            )
        rows.append(
            '<article style="display:flex;align-items:flex-start;gap:14px;'
            f'flex-direction:{direction};width:92%;margin:{margin}">'
            + portrait
            + '<div style="min-width:0;flex:1">'
            '<div style="font-weight:700;margin-bottom:6px;color:#214d40;'
            f'text-align:{name_alignment}">{name}</div>'
            '<div style="background:#fffdf6;border:1px solid #d9dfd2;'
            f"border-radius:{corners};padding:14px 16px;"
            f'line-height:1.9;overflow-wrap:anywhere">{text}</div></div></article>'
        )
    notice = ""
    if any(
        terminal_link(message.get("link", {}).get("href", "")) for message in messages
    ):
        notice = (
            '<aside style="padding:12px;border:1px solid #b39455;background:#fff9e8">'
            "調査端末の接続案内は、Colabでは「＋コード」からコードセルを追加する操作に読み替えてください。"
            "調査コマンドはセルに入力して実行します。</aside>"
        )
    return notice + (
        (
            '<section aria-label="掛け合い" lang="ja" style="max-width:820px;'
            "padding:8px 16px;color:#162823;background:#f8f6ef;"
            "border-left:4px solid #214d40;border-radius:8px;font-size:15px;"
            'font-family:system-ui,sans-serif">' + "".join(rows) + "</section>"
        )
        if rows
        else ""
    )
