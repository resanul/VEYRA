from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from veyra.providers.models import StreamSource
from veyra.providers.network import NetworkClient, NetworkRequestError, RequestOptions


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/manifest":
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
            self.send_header("Set-Cookie", "session=abc123; Path=/")
            self.end_headers()
            self.wfile.write(
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=1280x720\nvideo/720.m3u8\n"
            )
            return
        if self.path == "/echo":
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"referer={self.headers.get('Referer','')} cookie={self.headers.get('Cookie','')}".encode()
            )
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


def _server() -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_headers_referer_and_cookie_are_forwarded() -> None:
    server, _ = _server()
    try:
        url = f"http://127.0.0.1:{server.server_port}/echo"
        response = NetworkClient().get(
            url,
            headers={"X-Test": "ok"},
            referer="https://provider.example/",
            cookies={"session": "xyz"},
        )
        assert response.status == 200
        assert "referer=https://provider.example/" in response.text
        assert "cookie=session=xyz" in response.text
    finally:
        server.shutdown()


def test_fetch_manifest_preserves_request_headers_on_resolved_source() -> None:
    server, _ = _server()
    try:
        url = f"http://127.0.0.1:{server.server_port}/manifest"
        _, manifest = NetworkClient(options=RequestOptions(referer="https://provider.example/")) .fetch_manifest(url)
        assert manifest.format == "hls"
        assert manifest.sources[0].url.endswith("/video/720.m3u8")
        assert manifest.sources[0].headers["Referer"] == "https://provider.example/"
    finally:
        server.shutdown()


def test_source_request_context_uses_embedded_referer() -> None:
    source = StreamSource(
        url="https://cdn.example/video.m3u8",
        format="m3u8",
        headers={"Authorization": "Bearer test", "referer": "https://provider.example"},
    )
    options = NetworkClient.with_request_context(source)
    assert options.referer == "https://provider.example"
    assert options.headers["Authorization"] == "Bearer test"


def test_response_limit_is_enforced() -> None:
    server, _ = _server()
    try:
        url = f"http://127.0.0.1:{server.server_port}/echo"
        try:
            NetworkClient(options=RequestOptions(max_bytes=1)).get(url)
        except NetworkRequestError as exc:
            assert "byte limit" in str(exc)
        else:
            raise AssertionError("expected response size limit failure")
    finally:
        server.shutdown()
