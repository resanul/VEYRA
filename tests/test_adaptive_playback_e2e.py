from __future__ import annotations

import os
import time

import pytest

from veyra.providers.media_proxy import MediaStreamProxy
from veyra.providers.models import StreamSource


pytestmark = pytest.mark.e2e

HLS_URL = "https://devimages.apple.com/iphone/samples/bipbop/bipbopall.m3u8"
DASH_URL = "https://dash.akamaized.net/envivio/EnvivioDash3/manifest.mpd"


def _play_remote_adaptive_stream(url: str) -> tuple[bool, str | None, int]:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    app = QCoreApplication.instance() or QCoreApplication([])
    proxy = MediaStreamProxy()
    player = QMediaPlayer()
    audio = QAudioOutput()
    audio.setVolume(0.0)
    player.setAudioOutput(audio)
    loop = QEventLoop()
    state = {"ready": False, "playing": False, "error": None}

    def maybe_finish() -> None:
        if player.duration() > 0 and (state["ready"] or state["playing"]):
            loop.quit()

    def on_status(status) -> None:
        if status in {
            QMediaPlayer.MediaStatus.LoadedMedia,
            QMediaPlayer.MediaStatus.BufferedMedia,
        }:
            state["ready"] = True
            maybe_finish()
        elif status == QMediaPlayer.MediaStatus.InvalidMedia:
            loop.quit()

    def on_state(playback_state) -> None:
        if playback_state == QMediaPlayer.PlaybackState.PlayingState:
            state["playing"] = True
            maybe_finish()

    def on_error(_error, message: str) -> None:
        state["error"] = message or player.errorString()
        loop.quit()

    player.mediaStatusChanged.connect(on_status)
    player.playbackStateChanged.connect(on_state)
    player.errorOccurred.connect(on_error)
    timer = QTimer()
    timer.setSingleShot(True)
    timer.timeout.connect(loop.quit)
    timer.start(60_000)

    try:
        source = StreamSource(
            url=url,
            headers={
                "User-Agent": "VEYRA/0.3.2 adaptive-e2e",
                "Referer": "https://provider.example/",
            },
        )
        play_url = proxy.prepare(source)
        assert play_url != url
        player.setSource(QUrl(play_url))
        player.play()
        loop.exec()
        duration = int(player.duration())
        return (
            state["error"] is None and duration > 0 and (state["ready"] or state["playing"]),
            state["error"],
            duration,
        )
    finally:
        player.stop()
        proxy.close()


def test_qmediaplayer_plays_real_hls_through_proxy() -> None:
    ok, error, duration = _play_remote_adaptive_stream(HLS_URL)
    assert ok, f"HLS playback failed: {error or 'unknown error'}; duration={duration}ms"


def test_qmediaplayer_plays_real_dash_through_proxy() -> None:
    ok, error, duration = _play_remote_adaptive_stream(DASH_URL)
    assert ok, f"DASH playback failed: {error or 'unknown error'}; duration={duration}ms"
