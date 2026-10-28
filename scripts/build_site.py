"""READMEを正本としてGitHub Pages用の案内を生成する。"""

from pathlib import Path
import shutil
import struct

import markdown

SITE_URL = "https://fakedocument.github.io/MysteryOfMikuriyaKodomoShokudo/"
TITLE = "御厨こども食堂の謎"
DESCRIPTION = "ささきえまちゃんをさがしてください"

root = Path(__file__).resolve().parents[1]
body = markdown.markdown(
    (root / "README.md").read_text(), extensions=["fenced_code", "toc"]
)
css = (root / "site/style.css").read_text()
out = root / "_site"
out.mkdir(exist_ok=True)
shutil.copytree(root / "docs/mac-setup", out / "docs/mac-setup", dirs_exist_ok=True)
(out / "assets").mkdir(exist_ok=True)
image = root / "docker/notebook/app/static/images/Sushi-ctf-所長-普段着-普段.png"
shutil.copyfile(image, out / "assets/director.png")
image_width, image_height = struct.unpack(">II", image.read_bytes()[16:24])
image_url = SITE_URL + "assets/director.png"
(out / "index.html").write_text(
    f"""<!doctype html>
<html lang="ja" prefix="og: https://ogp.me/ns#"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="{DESCRIPTION}">
<link rel="canonical" href="{SITE_URL}">
<meta property="og:type" content="website">
<meta property="og:locale" content="ja_JP">
<meta property="og:site_name" content="{TITLE}">
<meta property="og:title" content="{TITLE}">
<meta property="og:description" content="{DESCRIPTION}">
<meta property="og:url" content="{SITE_URL}">
<meta property="og:image" content="{image_url}">
<meta property="og:image:type" content="image/png">
<meta property="og:image:width" content="{image_width}">
<meta property="og:image:height" content="{image_height}">
<meta name="twitter:card" content="summary">
<meta name="twitter:site" content="@fakedocument800">
<meta name="twitter:title" content="{TITLE}">
<meta name="twitter:description" content="{DESCRIPTION}">
<meta name="twitter:image" content="{image_url}">
<title>{TITLE} | はじめかた</title><style>"""
    + css
    + """</style></head>
<body><a class="skip" href="#guide">本文へ</a><header><p>御厨こども食堂の謎</p>
「えまちゃんを探してください」探偵事務所に舞い込んできた人探しの依頼。<br>怪しいのは彼女の通っていた子ども食堂だ。
<p>ハッキングを駆使し、真相を解き明かせ</p>
<a class="download" href="https://github.com/FakeDocument/MysteryOfMikuriyaKodomoShokudo/releases/latest">起動用ZIPをダウンロード ↗</a>
</header>
<main id="guide">"""
    + body
    + """
    </main>
    <footer>作: 
    <a href="https://x.com/fakedocument800">X (@fakedocument800)</a> ·
    <a href="https://github.com/FakeDocument">GitHub (FakeDocument)</a>
    </footer></body></html>"""
)
(out / ".nojekyll").touch()
