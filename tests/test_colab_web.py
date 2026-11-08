"""Colab版で標的サイトをブラウザから開くための、中継とリンク表示の振る舞いを検証する。"""

import http.client
import shutil
import sys
import tempfile
import threading
import unittest
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "experiments/colab"))


import colab_render as render  # noqa: E402
import colab_web as web  # noqa: E402


class Links(HTMLParser):
    def __init__(self, value: str) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self.feed(value)

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "a":
            self._href = dict(attrs)["href"]
            self.links.append((self._href, ""))

    def handle_data(self, data) -> None:
        if self._href is not None:
            href, text = self.links[-1]
            self.links[-1] = (href, text + data)

    def handle_endtag(self, tag) -> None:
        if tag == "a":
            self._href = None


class SiteLinkTest(unittest.TestCase):
    def setUp(self) -> None:
        render.set_site_links(
            {
                "http://shop.example": "https://proxy-1.example/",
                "http://docs.example": "https://proxy-2.example/",
                "http://docs.example:8080": "https://proxy-3.example/",
            }
        )
        self.addCleanup(render.set_site_links, {})

    def test_本文中のサイトURLを中継URLへのリンクにする(self) -> None:
        html = render.markdown_html("まず `http://shop.example/` を開く。")

        self.assertEqual(
            Links(html).links, [("https://proxy-1.example/", "http://shop.example/")]
        )

    def test_リンク先はURLのパスを保つ(self) -> None:
        html = render.inline_html("http://shop.example/admin/ を見る")

        self.assertEqual(
            Links(html).links,
            [("https://proxy-1.example/admin/", "http://shop.example/admin/")],
        )

    def test_同じホストでもポートが違えば別の中継URLへつなぐ(self) -> None:
        html = render.inline_html("`http://docs.example:8080/` と `http://docs.example/`")

        self.assertEqual(
            [href for href, _ in Links(html).links],
            ["https://proxy-3.example/", "https://proxy-2.example/"],
        )

    def test_コマンド例のURLはリンクにしない(self) -> None:
        html = render.markdown_html("```sh\ndirb http://shop.example/ list.txt\n```")

        self.assertEqual(Links(html).links, [])
        self.assertIn("http://shop.example/", html)

    def test_中継していないサイトのURLはリンクにしない(self) -> None:
        render.set_site_links({})

        html = render.inline_html("`http://shop.example/` を開く")

        self.assertEqual(Links(html).links, [])


class Backend(BaseHTTPRequestHandler):
    """受け取った要求を記録し、クッキーとリダイレクトを返す標的サイトの代役。"""

    received: list[dict[str, str]] = []

    def _respond(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else ""
        Backend.received.append(
            {
                "method": self.command,
                "path": self.path,
                "host": self.headers["Host"],
                "cookie": self.headers.get("Cookie", ""),
                "body": body,
            }
        )
        payload = "ページ本文".encode()
        self.send_response(303 if self.command == "POST" else 200)
        self.send_header("Set-Cookie", "session=abc; Path=/; HttpOnly")
        if self.command == "POST":
            self.send_header("Location", f"http://{self.headers['Host']}/inbox")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = _respond
    do_POST = _respond

    def log_message(self, *_args) -> None:
        pass


class ProxyTest(unittest.TestCase):
    def setUp(self) -> None:
        Backend.received = []
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
        threading.Thread(target=self.backend.serve_forever, daemon=True).start()
        self.addCleanup(self.backend.server_close)
        self.addCleanup(self.backend.shutdown)
        # macOSはUnixソケットのパス長が短いため、短い一時ディレクトリを使う。
        directory = Path(tempfile.mkdtemp(prefix="cw", dir="/tmp"))
        self.addCleanup(shutil.rmtree, directory, True)
        self.socket_path = directory / "site.sock"

    def start(self, origin: str) -> int:
        relay = web.start_relay(self.socket_path, "127.0.0.1", self.backend.server_port)
        self.addCleanup(relay.close)
        proxy = web.start_proxy(origin, self.socket_path, 0)
        self.addCleanup(proxy.close)
        return proxy.port

    def request(self, port: int, method: str, path: str, **options):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.addCleanup(connection.close)
        connection.request(method, path, **options)
        response = connection.getresponse()
        return response, response.read().decode()

    def test_本来のサイト名を名乗って標的へ転送する(self) -> None:
        port = self.start("http://mail.example")

        response, body = self.request(
            port, "GET", "/inbox?page=2", headers={"Cookie": "session=abc"}
        )

        self.assertEqual((response.status, body), (200, "ページ本文"))
        self.assertEqual(
            Backend.received,
            [
                {
                    "method": "GET",
                    "path": "/inbox?page=2",
                    "host": "mail.example",
                    "cookie": "session=abc",
                    "body": "",
                }
            ],
        )
        self.assertEqual(
            response.getheader("Set-Cookie"), "session=abc; Path=/; HttpOnly"
        )

    def test_既定以外のポートはサイト名にポートを含める(self) -> None:
        port = self.start("http://docs.example:8080")

        self.request(port, "GET", "/")

        self.assertEqual(Backend.received[0]["host"], "docs.example:8080")

    def test_フォームの送信内容を転送しリダイレクト先を中継側のパスにする(self) -> None:
        port = self.start("http://mail.example")

        response, _ = self.request(
            port,
            "POST",
            "/login",
            body="q=%27+OR+1%3D1+--+",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        self.assertEqual(Backend.received[0]["body"], "q=%27+OR+1%3D1+--+")
        self.assertEqual(
            (response.status, response.getheader("Location")), (303, "/inbox")
        )

    def test_標的へつながらないときは502で知らせる(self) -> None:
        proxy = web.start_proxy("http://mail.example", self.socket_path, 0)
        self.addCleanup(proxy.close)

        response, body = self.request(proxy.port, "GET", "/")

        self.assertEqual(response.status, 502)
        self.assertTrue(body)


class SiteTableTest(unittest.TestCase):
    def test_中継する各サイトは固有の待受ポートとソケットを持つ(self) -> None:
        root = Path("/runtime")

        self.assertEqual(
            len({site.local_port for site in web.SITES}), len(web.SITES)
        )
        self.assertEqual(
            len({site.socket_path(root) for site in web.SITES}), len(web.SITES)
        )


if __name__ == "__main__":
    unittest.main()
