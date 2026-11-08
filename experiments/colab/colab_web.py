"""Colabのブラウザから、隔離ネットワーク内の標的サイトを開くための中継。

標的のネットワーク内ではUnixソケットからTCPへ素通しし、カーネル側では
Hostを本来のサイト名へ書き換えるHTTP中継を待ち受ける。ColabはURLを
セッションごとに発行するため、本文のリンクは起動時に取得したURLで描画する。
"""

from __future__ import annotations

import contextlib
import http.client
import socket
import threading
from collections.abc import Callable
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

CHUNK_SIZE = 65536
CONNECT_TIMEOUT = 5
REQUEST_TIMEOUT = 30
# 接続ごとの制御用ヘッダーは中継で引き継がない。
HOP_HEADERS = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-connection",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "content-length",
        "host",
    }
)
UNAVAILABLE_MESSAGE = (
    "このサイトに接続できません。調査環境の準備セルを実行し直してください。"
)


@dataclass(frozen=True)
class Site:
    origin: str
    address: str
    port: int
    local_port: int

    def socket_path(self, root: Path) -> Path:
        return root / "run" / f"web-{self.local_port}.sock"


SITES = (
    Site("http://www.mikuriya-suisan.local", "172.30.0.10", 80, 18080),
    Site("http://mail.mikuriya-suisan.local", "172.30.0.10", 80, 18081),
    Site("http://kaiiki-hozen.local", "172.30.0.20", 80, 18082),
    Site("http://kaiiki-hozen.local:8080", "172.30.0.20", 8080, 18083),
)


class Running:
    """起動した待受の後始末をまとめる。"""

    def __init__(self, port: int, close: Callable[[], None]) -> None:
        self.port = port
        self._close = close

    def close(self) -> None:
        self._close()


def _pump(source: socket.socket, destination: socket.socket) -> None:
    try:
        while data := source.recv(CHUNK_SIZE):
            destination.sendall(data)
    except OSError:
        pass
    finally:
        with contextlib.suppress(OSError):
            destination.shutdown(socket.SHUT_WR)


def _bridge(client: socket.socket, address: str, port: int) -> None:
    try:
        upstream = socket.create_connection((address, port), timeout=CONNECT_TIMEOUT)
    except OSError:
        client.close()
        return
    upstream.settimeout(None)
    reverse = threading.Thread(target=_pump, args=(upstream, client), daemon=True)
    reverse.start()
    _pump(client, upstream)
    reverse.join()
    client.close()
    upstream.close()


def start_relay(socket_path: Path, address: str, port: int) -> Running:
    """Unixソケットで受けた接続を、同じネットワーク内のTCP宛先へ素通しする。"""
    socket_path.unlink(missing_ok=True)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(socket_path))
    listener.listen()

    def accept() -> None:
        while True:
            try:
                client, _ = listener.accept()
            except OSError:
                return
            threading.Thread(
                target=_bridge, args=(client, address, port), daemon=True
            ).start()

    threading.Thread(target=accept, daemon=True).start()

    def close() -> None:
        listener.close()
        socket_path.unlink(missing_ok=True)

    return Running(port, close)


class _UnixConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: Path) -> None:
        super().__init__("localhost", timeout=REQUEST_TIMEOUT)
        self._socket_path = socket_path

    def connect(self) -> None:
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(str(self._socket_path))
        except OSError:
            connection.close()
            raise
        self.sock = connection


class _ProxyServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, port: int, origin: str, socket_path: Path) -> None:
        super().__init__(("127.0.0.1", port), _ProxyHandler)
        self.origin = origin.rstrip("/")
        self.host = urlsplit(origin).netloc
        self.socket_path = socket_path


class _ProxyHandler(BaseHTTPRequestHandler):
    server: _ProxyServer

    def _forward(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_HEADERS
        }
        headers["Host"] = self.server.host
        connection = _UnixConnection(self.server.socket_path)
        try:
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            payload = response.read()
        except (OSError, http.client.HTTPException):
            self._unavailable()
            return
        finally:
            connection.close()
        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() in HOP_HEADERS:
                continue
            if key.lower() == "location" and value.startswith(self.server.origin):
                # 本来のサイト名のままでは中継の外へ出るため、パスだけを返す。
                value = value[len(self.server.origin) :] or "/"
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    def _unavailable(self) -> None:
        payload = UNAVAILABLE_MESSAGE.encode()
        self.send_response(502)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(payload)

    do_GET = _forward
    do_POST = _forward
    do_HEAD = _forward

    def log_message(self, *_args) -> None:
        # 要求ごとのログがセル出力へ混ざらないようにする。
        pass


def start_proxy(origin: str, socket_path: Path, port: int) -> Running:
    """Hostを本来のサイト名へ書き換え、Unixソケット経由で標的へ転送する。"""
    server = _ProxyServer(port, origin, socket_path)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def close() -> None:
        server.shutdown()
        server.server_close()

    return Running(server.server_address[1], close)


def colab_url(port: int) -> str:
    """Colabがこのセッション用に発行する、カーネルのポートへのURLを取得する。"""
    from google.colab.output import eval_js

    return eval_js(f"google.colab.kernel.proxyPort({port}, {{'cache': false}})")
