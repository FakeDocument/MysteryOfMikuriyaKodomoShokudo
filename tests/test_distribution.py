"""配布形式とランチャーの成功・失敗時の外部動作を検証する。"""
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('package_release', ROOT / 'scripts/package_release.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'distribution', self.root / 'distribution')
        (self.root / 'README.md').write_text('Setup guide')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.trace = self.root / 'trace'
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'], 'TRACE': str(self.trace)}

    def command(self, name, body):
        file = self.bin / name
        file.write_text('#!/bin/bash\n' + body)
        file.chmod(0o755)

    def test_packages_pin_images_and_preserve_isolation(self):
        config = {'name': 'sushictf', 'services': {name: {'image': f'sushictf/{name}:local', 'build': {'context': '/private/source'}, 'ports': ['127.0.0.1:8080:8000']} for name in package.SERVICES}, 'networks': {'target-net': {'internal': True}}, 'volumes': {'notebook-data': {}}}
        self.command('docker', 'if [ "$1" = compose ]; then cat <<\'CONFIG\'\n' + json.dumps(config) + '\nCONFIG\nelif [ "$1" = save ]; then printf "image archive fixture"; fi\n')
        for arch in ('amd64', 'arm64'):
            with self.subTest(arch=arch), patch.dict(os.environ, self.env), patch.object(package, 'ROOT', self.root), patch.object(sys, 'argv', ['package_release.py', '--version', 'v1.2.3', '--arch', arch, '--repository', 'example/ctf']):
                package.main()
                out = self.root / 'dist'
                archive = out / f'SushiCTF-images-{arch}.tar.gz'
                self.assertEqual(gzip.decompress(archive.read_bytes()), b'image archive fixture')
                bundle = out / ('SushiCTF-Windows-x64.zip' if arch == 'amd64' else 'SushiCTF-macOS-arm64.zip')
                with zipfile.ZipFile(bundle) as z:
                    compose = json.loads(z.read('SushiCTF/compose.yaml'))
                    self.assertTrue(compose['networks']['target-net']['internal'])
                    for svc in compose['services'].values():
                        self.assertNotIn('build', svc)
                        self.assertEqual(svc['platform'], f'linux/{arch}')
                        self.assertEqual(svc['pull_policy'], 'never')
                        self.assertTrue(svc['image'].endswith(f':v1.2.3-{arch}'))
                        self.assertEqual(svc['ports'], ['127.0.0.1:8080:8000'])
                    release = z.read('SushiCTF/release.txt').decode().splitlines()
                    self.assertEqual(release[0], hashlib.sha256(archive.read_bytes()).hexdigest())
                    self.assertIn('/releases/download/v1.2.3/', release[1])
                    if arch == 'arm64':
                        for info in z.infolist():
                            if info.filename.endswith('.command'):
                                self.assertTrue((info.external_attr >> 16) & 0o111)
                                subprocess.run(['bash', '-n'], input=z.read(info), check=True)
                    else:
                        self.assertTrue(z.read('SushiCTF/start.ps1').startswith(b'\xef\xbb\xbf'))

    def test_corrupt_download_never_loads_or_starts(self):
        (self.root / 'release.txt').write_text('0' * 64 + '\nhttps://example.invalid/archive\narm64\n')
        (self.root / 'images.txt').write_text('example/image:v1\n')
        shutil.copy(ROOT / 'distribution/start.command', self.root / 'start.command')
        self.command('docker', 'echo "$*" >> "$TRACE"\nif [ "$1" = info ]; then echo aarch64; fi\nif [ "$1 $2" = "image inspect" ]; then exit 1; fi\n')
        self.command('curl', 'echo invalid > images.tar.gz.part\n')
        self.command('open', 'echo browser >> "$TRACE"\n')
        result = subprocess.run(['bash', str(self.root / 'start.command')], env=self.env, input='\n', text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        trace = self.trace.read_text()
        self.assertNotIn('load --input', trace)
        self.assertNotIn('compose up', trace)
        self.assertNotIn('browser', trace)

    def test_offline_restart_and_unhealthy_failure(self):
        (self.root / 'release.txt').write_text('unused\nhttps://example.invalid/archive\narm64\n')
        (self.root / 'images.txt').write_text('example/image:v1\n')
        shutil.copy(ROOT / 'distribution/start.command', self.root / 'start.command')
        self.command('open', 'echo browser >> "$TRACE"\n')
        self.command('curl', 'echo unexpected-download >> "$TRACE"; exit 99\n')
        for status in (0, 1):
            with self.subTest(status=status):
                self.trace.write_text('')
                self.command('docker', 'echo "$*" >> "$TRACE"\nif [ "$1" = info ]; then echo aarch64; fi\nif [ "$1 $2" = "compose up" ]; then exit ' + str(status) + '; fi\n')
                result = subprocess.run(['bash', str(self.root / 'start.command')], env=self.env, input='\n', text=True, capture_output=True)
                trace = self.trace.read_text()
                self.assertEqual(result.returncode, status)
                self.assertNotIn('unexpected-download', trace)
                self.assertIn('up --no-build --pull never --wait', trace)
                self.assertEqual('browser' in trace, status == 0)


if __name__ == '__main__':
    unittest.main()
