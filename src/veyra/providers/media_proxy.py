from __future__ import annotations

import base64
import re
import secrets
import threading
from dataclasses import dataclass
from http.cookiejar import CookieJar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urljoin, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener

from .models import StreamSource
from .network import DEFAULT_HEADERS


_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


@dataclass(frozen=True, slots=True)
class ProxySource:
    url: str
    headers: dict[str, str]


def _encode_url(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")


def _decode_url(value: str) -> str:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding).decode("utf-8")


def _is_manifest(url: str, content_type: str = "") -> bool:
    path = urlsplit(url).path.lower()
    content = content_type.lower()
    return (
        path.endswith((".m3u8", ".m3u"))
        or path.endswith(".mpd")
        or "mpegurl" in content
        or "dash+xml" in content
    )


class _ProxyHandler(BaseHTTPRequestHandler):
    server: "_MediaProxyServer"

    def log_message(self, *_args: object) -> None:
        return

    def do_HEAD(self) -> None:
        self._handle(head_only=True)

    def do_GET(self) -> None:
        self._handle(head_only=False)

    def _handle(self, *, head_only: bool) -> None:
        parts = self.path.split("/", 2)
        if len(parts) != 3 or parts[1] != "stream":
            self.send_error(404, "Unknown media proxy route")
            return
        token = parts[2].split("/", 1)[0]
        encoded = parts[2][len(token) + 1 :]
        try:
            session = self.server.sessions[token]
            upstream_url = _decode_url(encoded)
        except (KeyError, ValueError, UnicodeError):
            self.send_error(404, "Unknown media source")
            return

        headers = dict(session.headers)
        range_header = self.headers.get("Range")
        if range_header:
            headers["Range"] = range_header
        request = Request(upstream_url, headers=headers, method="GET")
        try:
            with session.opener.open(request, timeout=session.timeout) as response:
                status = int(response.status)
                response_headers = {str(k): str(v) for k, v in response.headers.items()}
                content_type = response_headers.get("Content-Type", "")
                body = response.read(8 * 1024 * 1024 + 1) if _is_manifest(upstream_url, content_type) else None

                self.send_response(status)
                for key, value in response_headers.items():
                    if key.lower() in _HOP_BY_HOP or key.lower() == "content-length":
                        continue
                    self.send_header(key, value)
                if body is not None:
                    if len(body) > 8 * 1024 * 1024:
                        self.send_error(502, "Manifest exceeds proxy limit")
                        return
                    rewritten = self.server.rewrite_manifest(session, upstream_url, body, token)
                    self.send_header("Content-Length", str(len(rewritten)))
                elif "Content-Length" in response_headers:
                    self.send_header("Content-Length", response_headers["Content-Length"])
                self.end_headers()
                if head_only:
                    return
                if body is not None:
                    self.wfile.write(rewritten)
                    return
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
        except Exception as exc:  # pragma: no cover - exercised by real playback
            if not self.wfile.closed:
                self.send_error(502, f"Upstream media request failed: {exc}")


@dataclass(slots=True)
class _Session:
    headers: dict[str, str]
    timeout: float
    opener: object


class _MediaProxyServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _ProxyHandler)
        self.sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def add_source(self, source: StreamSource) -> str:
        token = secrets.token_urlsafe(18)
        headers = dict(DEFAULT_HEADERS)
        headers.update(source.headers)
        jar = CookieJar()
        opener = build_opener(HTTPCookieProcessor(jar))
        with self._lock:
            self.sessions[token] = _Session(headers=headers, timeout=30.0, opener=opener)
        return token

    def remove_source(self, token: str) -> None:
        with self._lock:
            self.sessions.pop(token, None)

    def rewrite_url(self, token: str, absolute_url: str) -> str:
        return f"http://127.0.0.1:{self.server_port}/stream/{token}/{_encode_url(absolute_url)}"

    def rewrite_manifest(self, session: _Session, base_url: str, body: bytes, token: str) -> bytes:
        text = body.decode("utf-8", errors="replace")
        if ".mpd" in urlsplit(base_url).path.lower() or "<MPD" in text[:512] or "<mpd" in text[:512]:
            return self._rewrite_dash(base_url, text, token).encode("utf-8")
        return self._rewrite_hls(base_url, text, token).encode("utf-8")

    def _rewrite_hls(self, base_url: str, text: str, token: str) -> str:
        def uri_replace(match: re.Match[str]) -> str:
            value = match.group(1)
            return f'URI="{self.rewrite_url(token, urljoin(base_url, value))}"'

        text = re.sub(r'URI="([^"]+)"', uri_replace, text)
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                line = line.replace(stripped, self.rewrite_url(token, urljoin(base_url, stripped)))
            lines.append(line)
        return "\n".join(lines) + ("\n" if text.endswith("\n") else "")

    def _rewrite_dash(self, base_url: str, text: str, token: str) -> str:
        def attr_replace(match: re.Match[str]) -> str:
            name, value = match.group(1), match.group(2)
            if value.startswith(("http://127.0.0.1:", "https://127.0.0.1:")):
                return match.group(0)
            return f'{name}="{self.rewrite_url(token, urljoin(base_url, value))}"'

        text = re.sub(r'\b(media|initialization|sourceURL|href)="([^"]+)"', attr_replace, text)

        def base_replace(match: re.Match[str]) -> str:
            value = match.group(1).strip()
            return f"<BaseURL>{self.rewrite_url(token, urljoin(base_url, value))}</BaseURL>"

        return re.sub(r"<BaseURL>([^<]+)</BaseURL>", base_replace, text)


class MediaStreamProxy:
    """Localhost HTTP bridge for QMediaPlayer network streams.

    Qt Multimedia's high-level QMediaPlayer source API accepts a URL but does
    not expose per-source HTTP headers on that API. The localhost bridge keeps
    extractor headers/cookies on the Python side and forwards every manifest
    and segment request with the same authenticated request context.
    """

    def __init__(self) -> None:
        self._server = _MediaProxyServer(("127.0.0.1", 0))
        self._thread = threading.Thread(target=self._server.serve_forever, name="veyra-media-proxy", daemon=True)
        self._thread.start()

    @property
    def port(self) -> int:
        return int(self._server.server_port)

    def prepare(self, source: StreamSource) -> str:
        parts = urlsplit(source.url)
        if parts.scheme not in {"http", "https"} or not source.headers:
            return source.url
        token = self._server.add_source(source)
        return self._server.rewrite_url(token, source.url)

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2.0)
