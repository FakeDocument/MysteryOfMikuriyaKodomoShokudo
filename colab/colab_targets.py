"""Colab版の標的サービスの配置と、Docker版の設定をColab用に変換する処理。

寿司屋サーバー（公開サイト・社内Webメール・Samba）と政府サーバー（公開サイト・
文書目録・Samba）を、隔離したネットワーク内の別アドレスで起動する。
nginxとSambaの設定はDocker版を正本とし、待受先と実行時の置き場だけを書き換える。
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

SUSHI_ADDRESS = "172.30.0.10"
PORTAL_ADDRESS = "172.30.0.20"
HOSTS: Mapping[str, str] = MappingProxyType(
    {
        "www.mikuriya-suisan.local": SUSHI_ADDRESS,
        "mail.mikuriya-suisan.local": SUSHI_ADDRESS,
        "kaiiki-hozen.local": PORTAL_ADDRESS,
    }
)
# 起動の完了を確かめる待受ポート。
OPEN_PORTS: Mapping[str, tuple[int, ...]] = MappingProxyType(
    {SUSHI_ADDRESS: (80, 445), PORTAL_ADDRESS: (80, 445, 8080)}
)
# Webアプリはネットワーク内のループバックだけで待ち受け、nginxが中継する。
WEBMAIL_PORT = 8000
PORTAL_PORT = 8001
# 保護共有の専用アカウント。正本は docker/portal/Dockerfile。
PORTAL_ACCOUNT = ("hozen_sync", "TideLog_2024")

# 実行時の置き場。Sambaを複数起動しても互いの状態が混ざらないよう、作業フォルダごとに分ける。
_SAMBA_DIRECTORIES = (
    ("lock directory", "lock"),
    ("state directory", "state"),
    ("cache directory", "cache"),
    ("private dir", "private"),
    ("pid directory", "run"),
    ("ncalrpc dir", "ncalrpc"),
)
_SECTION = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_SETTING = re.compile(r"^\s*([^=#;]+?)\s*=")


@dataclass(frozen=True)
class SambaServer:
    """1つのアドレスで待ち受けるSambaの設定と共有の置き場。"""

    name: str
    address: str
    template: str
    shares: Mapping[str, str]

    def workdir(self, root: Path) -> Path:
        return root / f"samba-{self.name}"

    def config_path(self, root: Path) -> Path:
        return root / f"smb-{self.name}.conf"


SAMBA_SERVERS = (
    SambaServer("sushi", SUSHI_ADDRESS, "smb.conf.in", {"staff": "share"}),
    SambaServer(
        "portal",
        PORTAL_ADDRESS,
        "smb-portal.conf.in",
        {"handover": "portal-handover", "handoff": "portal-handoff"},
    ),
)


def samba_directories(workdir: Path) -> list[Path]:
    return [workdir / directory for _, directory in _SAMBA_DIRECTORIES]


def samba_config(
    template: str, *, address: str, workdir: Path, shares: Mapping[str, Path]
) -> str:
    """Docker版のSamba設定を、指定アドレスと作業フォルダで動くように書き換える。"""
    overrides = {
        "interfaces": f"{address}/32",
        "bind interfaces only": "yes",
        **{key: str(workdir / directory) for key, directory in _SAMBA_DIRECTORIES},
        "log file": str(workdir / "samba.log"),
    }
    output: list[str] = []
    section: str | None = None
    for line in template.splitlines():
        heading = _SECTION.match(line)
        if heading:
            if section == "global":
                output.extend(
                    f"    {key} = {value}" for key, value in overrides.items()
                )
            section = heading[1].strip()
            output.append(line)
            continue
        setting = _SETTING.match(line)
        key = setting[1].strip().lower() if setting else None
        if section == "global" and key in overrides:
            continue
        if section not in (None, "global") and key == "path":
            if section not in shares:
                raise ValueError(f"共有の置き場が指定されていません: {section}")
            line = f"    path = {shares[section]}"
        output.append(line)
    if section == "global":
        output.extend(f"    {key} = {value}" for key, value in overrides.items())
    return "\n".join(output) + "\n"


def _bind(server_config: str, address: str, upstream: tuple[int, int]) -> str:
    """待受をアドレス付きにし、IPv6の待受を除き、Webアプリの中継先を差し替える。"""
    lines = [
        line
        for line in server_config.splitlines()
        if not re.match(r"\s*listen\s+\[", line)
    ]
    text = "\n".join(lines)
    bound, count = re.subn(r"(\blisten\s+)(\d+)\b", rf"\g<1>{address}:\g<2>", text)
    if count != len(re.findall(r"\blisten\s", text)):
        raise ValueError("nginxの待受ポートを標的のアドレスへ書き換えられません。")
    before, after = upstream
    return bound.replace(f"127.0.0.1:{before};", f"127.0.0.1:{after};")


def nginx_config(root: Path, *, sushi: str, portal: str) -> str:
    """Docker版の2つのnginx設定を、1つのnginxで両標的を担う設定にまとめる。"""
    sushi_servers = _bind(sushi, SUSHI_ADDRESS, (8000, WEBMAIL_PORT)).replace(
        "root /usr/share/nginx/html;", f"root {root / 'site'};"
    )
    portal_servers = _bind(portal, PORTAL_ADDRESS, (8000, PORTAL_PORT))
    return (
        f"pid {root / 'run/nginx.pid'};\nerror_log {root / 'nginx.log'};\n"
        "events {}\nhttp {\ninclude /etc/nginx/mime.types;\naccess_log off;\n"
        f"{sushi_servers}\n{portal_servers}\n}}\n"
    )


@dataclass(frozen=True)
class Service:
    name: str
    command: tuple[str, ...]
    cwd: Path | None = None
    env: Mapping[str, str] = MappingProxyType({})


def services(root: Path, python: str) -> tuple[Service, ...]:
    """隔離ネットワーク内で起動するプロセス。"""
    return (
        Service(
            "nginx", ("nginx", "-c", str(root / "nginx.conf"), "-g", "daemon off;")
        ),
        *(
            Service(
                f"smbd-{server.name}",
                (
                    "smbd",
                    "--foreground",
                    "--no-process-group",
                    "--debug-stdout",
                    "--configfile=" + str(server.config_path(root)),
                ),
            )
            for server in SAMBA_SERVERS
        ),
        Service(
            "webmail",
            (python, str(root / "webmail/app.py")),
            env=MappingProxyType({"WEBMAIL_DB_PATH": str(root / "webmail.db")}),
        ),
        Service(
            "portal",
            (
                python,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORTAL_PORT),
                "--log-level",
                "warning",
            ),
            cwd=root / "portal",
        ),
    )


def ready_endpoints() -> list[tuple[str, int]]:
    """すべてのサービスが応答できるかを確かめる接続先。"""
    return [
        *((address, port) for address, ports in OPEN_PORTS.items() for port in ports),
        ("127.0.0.1", WEBMAIL_PORT),
        ("127.0.0.1", PORTAL_PORT),
    ]
