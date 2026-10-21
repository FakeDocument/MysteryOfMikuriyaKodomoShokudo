"""READMEを正本としてGitHub Pages用の案内を生成する。"""

from pathlib import Path
import markdown

root = Path(__file__).resolve().parents[1]
body = markdown.markdown(
    (root / "README.md").read_text(), extensions=["fenced_code", "toc"]
)
css = (root / "site/style.css").read_text()
out = root / "_site"
out.mkdir(exist_ok=True)
(out / "index.html").write_text(
    """<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="『御厨こども食堂の謎』のダウンロードと初心者向けセットアップ手順。必要環境と起動手順を案内します。">
<title>御厨こども食堂の謎 | はじめかた</title><style>"""
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
