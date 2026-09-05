from __future__ import annotations

import io
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from veyra.history import PlaybackHistory
from veyra.playback_state import PlaybackState, PlaybackStateStore
from veyra.providers.media_proxy import MediaStreamProxy
from veyra.providers.models import StreamSource


pytestmark = pytest.mark.e2e


def _wav_bytes(duration_seconds: float = 6.0) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8000)
        output.writeframes(b"\x00\x00" * int(8000 * duration_seconds))
    return buffer.getvalue()


class _MediaServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], body: bytes) -> None:
        self.body = body
        self.requests = 0
        self.lock = threading.Lock()
        super().__init__(address, _MediaHandler)


class _MediaHandler(BaseHTTPRequestHandler):
    server: _MediaServer

    def log_message(self, *_args: object) -> None:
        return

    def do_GET(self) -> None:
        with self.server.lock:
            self.server.requests += 1
        body = self.server.body
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _wait_for_loaded(player, timeout_ms: int = 30_000) -> None:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtMultimedia import QMediaPlayer

    loop = QEventLoop()
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(timeout_ms)
    loaded = {"value": False, "error": None}

    def status_changed(status) -> None:
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            loaded["value"] = True
            loop.quit()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            loop.quit()

    def error_changed(_error, message: str) -> None:
        loaded["error"] = message or player.errorString()
        loop.quit()

    player.mediaStatusChanged.connect(status_changed)
    player.errorOccurred.connect(error_changed)
    if player.duration() > 0:
        loaded["value"] = True
    else:
        loop.exec()
    if loaded["error"]:
        raise AssertionError(loaded["error"])
    assert loaded["value"], "QMediaPlayer did not load the E2E media"
    assert player.duration() > 0


def test_qmediaplayer_restores_advanced_state_across_new_session(tmp_path) -> None:
    from PySide6.QtCore import QCoreApplication, QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    _app = QCoreApplication.instance() or QCoreApplication([])
    server = _MediaServer(("127.0.0.1", 0), _wav_bytes())
    server_thread = threading.Thread(target=server.serve_forever, name="veyra-player-e2e", daemon=True)
    server_thread.start()
    proxy = MediaStreamProxy()

    settings_path = tmp_path / "player.ini"
    from PySide6.QtCore import QSettings
    settings = QSettings(str(settings_path), QSettings.Format.IniFormat)
    settings.clear()
    state_store = PlaybackStateStore(settings)
    history = PlaybackHistory(tmp_path / "history.json")

    upstream = f"http://127.0.0.1:{server.server_port}/media.wav"
    source = StreamSource(url=upstream, headers={"User-Agent": "VEYRA/0.3.2 player-e2e"})
    first_url = proxy.prepare(source)
    player = QMediaPlayer()
    audio = QAudioOutput()
    player.setAudioOutput(audio)

    try:
        player.setSource(QUrl(first_url))
        player.play()
        _wait_for_loaded(player)

        target_position = min(1800, max(500, player.duration() // 3))
        player.setPosition(target_position)
        player.setPlaybackRate(1.5)
        audio.setVolume(0.35)
        audio.setMuted(True)

        state_store.save_source(
            first_url,
            PlaybackState(
                playback_rate=player.playbackRate(),
                volume=audio.volume(),
                muted=audio.isMuted(),
                audio_track=1,
                video_track=0,
                subtitle_track=-1,
                external_subtitle="https://example.test/subtitles/en.vtt",
            ),
        )
        history.save_position(upstream, "E2E Media", target_position, player.duration())
        player.stop()
        player.deleteLater()
        player = None

        second_url = proxy.prepare(source)
        restored_player = QMediaPlayer()
        restored_audio = QAudioOutput()
        restored_player.setAudioOutput(restored_audio)
        restored_player.setSource(QUrl(second_url))
        _wait_for_loaded(restored_player)

        restored_state = state_store.load_source(second_url)
        restored_record = history.get(upstream)
        assert restored_record is not None
        assert restored_state.audio_track == 1
        assert restored_state.video_track == 0
        assert restored_state.external_subtitle.endswith("/en.vtt")

        restored_player.setPlaybackRate(restored_state.playback_rate)
        restored_audio.setVolume(restored_state.volume)
        restored_audio.setMuted(restored_state.muted)
        restored_player.setPosition(restored_record.position_ms)

        assert restored_player.playbackRate() == pytest.approx(1.5)
        assert restored_audio.volume() == pytest.approx(0.35, abs=0.01)
        assert restored_audio.isMuted() is True
        assert restored_player.position() == pytest.approx(target_position, abs=150)
        assert server.requests > 0
    finally:
        try:
            if player is not None:
                player.stop()
        except Exception:
            pass
        try:
            restored_player.stop()
        except (NameError, UnboundLocalError):
            pass
        proxy.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=2.0)
