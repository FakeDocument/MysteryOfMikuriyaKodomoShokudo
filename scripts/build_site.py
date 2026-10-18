"""READMEを正本としてGitHub Pages用の案内を生成する。"""
from pathlib import Path
import markdown

root = Path(__file__).resolve().parents[1]
body = markdown.markdown((root / 'README.md').read_text(), extensions=['fenced_code', 'toc'])
css = (root / 'site/style.css').read_text()
out = root / '_site'
out.mkdir(exist_ok=True)
(out / 'index.html').write_text('''<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="SushiCTFのダウンロードと初心者向けセットアップ手順。WindowsとMacに対応。">
<title>SushiCTF | はじめかた</title><style>''' + css + '''</style></head>
<body><a class="skip" href="#guide">本文へ</a><header><span>SUSHICTF / GET STARTED</span><p>一冊のノートから、調査をはじめよう。</p>
<a class="download" href="https://github.com/FakeDocument/MysteryOfMikuriyaKodomoShokudo/releases/latest">起動用ZIPをダウンロード ↗</a>
<small>Windows 11 x64 / Apple Silicon Mac ・ Docker Desktopが必要です</small></header>
<main id="guide">''' + body + '</main><footer>SushiCTF · ローカルで遊ぶ、日本語の調査CTF</footer></body></html>')
(out / '.nojekyll').touch()
