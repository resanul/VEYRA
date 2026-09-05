from __future__ import annotations

import io
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from veyra.providers.media_proxy import MediaStreamProxy
from veyra.providers.models import StreamSource


pytestmark = pytest.mark.e2e


def _wav_bytes(duration_seconds: float = 5.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * int(8000 * duration_seconds))
    return buffer.getvalue()


class _AuthenticatedMediaServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], body: bytes) -> None:
        self.body = body
        self.requests: list[tuple[str | None, str | None, str | None]] = []
        self.lock = threading.Lock()
        super().__init__(address, _AuthenticatedMediaHandler)


class _AuthenticatedMediaHandler(BaseHTTPRequestHandler):
    server: _AuthenticatedMediaServer

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        authorization = self.headers.get("Authorization")
        referer = self.headers.get("Referer")
        range_header = self.headers.get("Range")
        with self.server.lock:
            self.server.requests.append((authorization, referer, range_header))

        if authorization != "Bearer e2e-token" or referer != "https://provider.example/":
            self.send_error(403, "missing provider request context")
            return

        body = self.server.body
        start, end = 0, len(body) - 1
        status = 200
        if range_header and range_header.startswith("bytes="):
            raw_start, _, raw_end = range_header[6:].partition("-")
            if raw_start.isdigit():
                start = int(raw_start)
                if raw_end.isdigit():
                    end = min(int(raw_end), len(body) - 1)
                if start >= len(body) or start > end:
                    self.send_error(416, "range not satisfiable")
                    return
                status = 206
        payload = body[start : end + 1]
        self.send_response(status)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(payload)))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{len(body)}")
        self.end_headers()
        self.wfile.write(payload)


def test_qmediaplayer_plays_authenticated_remote_media_through_proxy() -> None:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    body = _wav_bytes()
    server = _AuthenticatedMediaServer(("127.0.0.1", 0), body)
    thread = threading.Thread(target=server.serve_forever, name="veyra-e2e-media", daemon=True)
    thread.start()
    proxy = MediaStreamProxy()
    app = QCoreApplication.instance() or QCoreApplication([])
    player = QMediaPlayer()
    audio = QAudioOutput()
    audio.setVolume(0.0)
    player.setAudioOutput(audio)
    loop = QEventLoop()
    deadline = time.monotonic() + 30.0
    state = {"error": None, "loaded": False, "playing": False}

    def on_status(status) -> None:
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            state["loaded"] = True
            if player.duration() > 0:
                loop.quit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            loop.quit()

    def on_state(playback_state) -> None:
        if playback_state == QMediaPlayer.PlaybackState.PlayingState:
            state["playing"] = True
            if player.duration() > 0:
                loop.quit()

    def on_error(_error, message: str) -> None:
        state["error"] = message or player.errorString()
        loop.quit()

    player.mediaStatusChanged.connect(on_status)
    player.playbackStateChanged.connect(on_state)
    player.errorOccurred.connect(on_error)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(30_000)

    try:
        upstream = f"http://127.0.0.1:{server.server_port}/audio.wav"
        source = StreamSource(
            url=upstream,
            headers={
                "Authorization": "Bearer e2e-token",
                "Referer": "https://provider.example/",
            },
        )
        play_url = proxy.prepare(source)
        assert play_url != upstream
        player.setSource(QUrl(play_url))
        player.play()
        loop.exec()

        assert state["error"] is None, state["error"]
        assert state["loaded"] or state["playing"], "QMediaPlayer did not load remote media"
        assert player.duration() > 0
        assert time.monotonic() < deadline or state["loaded"] or state["playing"]

        with server.lock:
            requests = list(server.requests)
        assert requests, "proxy did not reach the authenticated upstream server"
        assert any(auth == "Bearer e2e-token" and ref == "https://provider.example/" for auth, ref, _ in requests)
    finally:
        player.stop()
        proxy.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2.0)
