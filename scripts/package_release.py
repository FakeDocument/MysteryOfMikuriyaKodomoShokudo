"""CIでビルドしたイメージを、固定版ComposeとOS別ランチャーへ梱包する。"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ('notebook', 'sushi', 'portal', 'kali')
BUNDLE_NAME = 'MysteryOfMikuriyaKodomoShokudo'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', required=True)
    parser.add_argument('--arch', choices=['amd64', 'arm64'], required=True)
    parser.add_argument('--repository', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'v[0-9][A-Za-z0-9_.-]*', args.version):
        parser.error('version must be a v-prefixed release tag')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', args.repository):
        parser.error('invalid repository')
    config = json.loads(run('docker', 'compose', 'config', '--format', 'json', capture_output=True, text=True).stdout)
    images = []
    for name in SERVICES:
        svc = config['services'][name]
        source = svc['image']
        image = f'sushictf/{name}:{args.version}-{args.arch}'
        run('docker', 'tag', source, image)
        svc.pop('build', None)
        svc['image'] = image
        svc['platform'] = f'linux/{args.arch}'
        svc['pull_policy'] = 'never'
        images.append(image)
    out = ROOT / 'dist'
    out.mkdir(exist_ok=True)
    archive = out / f'{BUNDLE_NAME}-images-{args.arch}.tar.gz'
    # Stream to disk rather than buffering a multi-GB image archive in RAM.
    with gzip.open(archive, 'wb', compresslevel=6) as target:
        proc = subprocess.Popen(['docker', 'save', *images], stdout=subprocess.PIPE)
        try:
            while chunk := proc.stdout.read(1024 * 1024):
                target.write(chunk)
        finally:
            proc.stdout.close()
        if proc.wait() != 0:
            raise RuntimeError('docker save failed')
    if archive.stat().st_size >= 2_000_000_000:
        raise RuntimeError('Image archive exceeds GitHub Releases asset size limit; reduce image size.')
    with archive.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    url = f'https://github.com/{args.repository}/releases/download/{args.version}/{archive.name}'
    os_name = 'Windows-x64' if args.arch == 'amd64' else 'macOS-arm64'
    bundle = out / f'{BUNDLE_NAME}-{os_name}.zip'
    with zipfile.ZipFile(bundle, 'w', zipfile.ZIP_DEFLATED) as z:
        def add(name, content, executable=False):
            entry = zipfile.ZipInfo(f'{BUNDLE_NAME}/{name}')
            entry.create_system = 3
            entry.external_attr = (0o100755 if executable else 0o100644) << 16
            z.writestr(entry, content)
        add('compose.yaml', json.dumps(config, ensure_ascii=False, indent=2))
        add('release.txt', f'{sha}\n{url}\n{args.arch}\n')
        add('images.txt', '\n'.join(images) + '\n')
        add('README.md', (ROOT / 'README.md').read_bytes())
        for screenshot in sorted((ROOT / 'docs/mac-setup').glob('*.png')):
            add(screenshot.relative_to(ROOT).as_posix(), screenshot.read_bytes())
        if args.arch == 'amd64':
            add('start.ps1', b'\xef\xbb\xbf' + (ROOT / 'distribution/start.ps1').read_bytes())
            add('start.bat', '@echo off\r\ncd /d "%~dp0"\r\npowershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"\r\n')
            for action in ('stop', 'reset'):
                # ASCII wrappers are readable by cmd.exe regardless of codepage.
                confirm = 'set /p "answer=Delete ALL progress? Type y to continue: "\r\nif /i not "%answer%"=="y" exit /b\r\n' if action == 'reset' else ''
                cmd = 'down --volumes' if action == 'reset' else 'stop'
                add(action + '.bat', '@echo off\r\ncd /d "%~dp0"\r\n' + confirm + f'docker compose {cmd}\r\nif errorlevel 1 (echo Failed. Check Docker Desktop.) else (echo Done.)\r\npause\r\n')
        else:
            add('start.command', (ROOT / 'distribution/start.command').read_bytes(), True)
            for action in ('stop', 'reset'):
                confirm = 'read -r -p "進捗をすべて削除します。続ける場合は y: " answer\n[ "$answer" = y ] || exit 0\n' if action == 'reset' else ''
                cmd = 'down --volumes' if action == 'reset' else 'stop'
                add(action + '.command', '#!/bin/bash\ncd "$(dirname "$0")"\n' + confirm + f'if docker compose {cmd}; then echo "完了しました。"; else echo "失敗しました。Docker Desktopを確認してください。"; fi\nread -r -p "Enterキーで閉じます..." _\n', True)
    for path in (archive, bundle):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        (out / (path.name + '.sha256')).write_text(f'{digest}  {path.name}\n')


if __name__ == '__main__':
    main()
