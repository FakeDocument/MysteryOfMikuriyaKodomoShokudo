"""Colab版の標的サービスを、Docker版の設定から起動用に変換する振る舞いを検証する。"""

import configparser
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "colab"))

import colab_targets as targets

SAMBA_TEMPLATE = """[global]
    workgroup = WORKGROUP
    map to guest = Bad User
    log file = /var/log/samba/log.%m
    smb ports = 445

[open]
    path = /srv/samba/open
    guest ok = yes

[locked]
    path = /srv/samba/locked
    guest ok = no
    valid users = someone
"""


def parse(text: str) -> configparser.ConfigParser:
    # 同じキーが二重に書かれていれば、ここで例外になる。
    config = configparser.ConfigParser(interpolation=None, strict=True)
    config.read_string(text)
    return config


class SambaConfigTests(unittest.TestCase):
    def convert(self, work: Path) -> configparser.ConfigParser:
        return parse(
            targets.samba_config(
                SAMBA_TEMPLATE,
                address="172.30.0.99",
                workdir=work,
                shares={"open": Path("/lab/open"), "locked": Path("/lab/locked")},
            )
        )

    def test_標的のアドレスだけで待ち受け実行時の置き場を作業フォルダへ移す(
        self,
    ) -> None:
        config = self.convert(Path("/lab/samba-a"))
        glob = config["global"]
        self.assertEqual(glob["interfaces"], "172.30.0.99/32")
        self.assertEqual(glob["bind interfaces only"], "yes")
        for key in ("lock directory", "state directory", "private dir", "log file"):
            self.assertTrue(glob[key].startswith("/lab/samba-a/"), key)

    def test_共有の公開範囲を保ったまま共有の中身を作業フォルダから配る(
        self,
    ) -> None:
        config = self.convert(Path("/lab/samba-a"))
        self.assertEqual(config["open"]["path"], "/lab/open")
        self.assertEqual(config["locked"]["path"], "/lab/locked")
        self.assertEqual(config["open"]["guest ok"], "yes")
        self.assertEqual(config["locked"]["valid users"], "someone")
        self.assertEqual(config["global"]["map to guest"], "Bad User")

    def test_作業フォルダが違えば実行時の置き場も重ならない(self) -> None:
        first = self.convert(Path("/lab/samba-a"))["global"]
        second = self.convert(Path("/lab/samba-b"))["global"]
        for key in (
            "lock directory",
            "state directory",
            "private dir",
            "pid directory",
        ):
            self.assertNotEqual(first[key], second[key], key)

    def test_置き場の指定がない共有は変換時に拒否する(self) -> None:
        with self.assertRaises(ValueError):
            targets.samba_config(
                SAMBA_TEMPLATE,
                address="172.30.0.99",
                workdir=Path("/lab/samba-a"),
                shares={"open": Path("/lab/open")},
            )


class NginxConfigTests(unittest.TestCase):
    def test_Docker版の各サイトを標的のアドレスとColabの中継先で待ち受ける(
        self,
    ) -> None:
        root = Path("/lab")
        config = targets.nginx_config(
            root,
            sushi=(ROOT / "docker/sushi/nginx.conf").read_text(),
            portal=(ROOT / "docker/portal/nginx.conf").read_text(),
        )
        listens = re.findall(r"listen\s+([^;\s]+)", config)
        self.assertEqual(
            set(listens),
            {
                f"{targets.SUSHI_ADDRESS}:80",
                f"{targets.PORTAL_ADDRESS}:80",
                f"{targets.PORTAL_ADDRESS}:8080",
            },
        )
        self.assertIn(f"root {root / 'site'};", config)
        self.assertIn(f"proxy_pass http://127.0.0.1:{targets.WEBMAIL_PORT};", config)
        self.assertIn(f"proxy_pass http://127.0.0.1:{targets.PORTAL_PORT};", config)
        # ポートでサービスを選ぶ振り分けは、Docker版と同じものを使う。
        self.assertIn("X-Kaiiki-Service catalog", config)
        self.assertIn("X-Kaiiki-Service public", config)

    def test_待受ポートを書き換えられない設定は拒否する(self) -> None:
        with self.assertRaises(ValueError):
            targets.nginx_config(
                Path("/lab"),
                sushi="server { listen unix:/tmp/x.sock; }",
                portal=(ROOT / "docker/portal/nginx.conf").read_text(),
            )


class TargetLayoutTests(unittest.TestCase):
    def test_各サイト名は起動する標的のアドレスへ解決される(self) -> None:
        import colab_web

        for site in colab_web.SITES:
            host = site.origin.split("://", 1)[1].split(":")[0]
            self.assertEqual(targets.HOSTS[host], site.address, host)
            self.assertIn(site.port, targets.OPEN_PORTS[site.address], host)


if __name__ == "__main__":
    unittest.main()
