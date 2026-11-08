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
        config.read(self.lab.root / "smb.conf")
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
