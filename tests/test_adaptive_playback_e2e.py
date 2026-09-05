from __future__ import annotations

import pytest

from veyra.providers.media_proxy import MediaStreamProxy
from veyra.providers.models import StreamSource


pytestmark = pytest.mark.e2e

# Public, clear test streams used by established player projects for
# compatibility/regression testing. The DASH fixture is a small clear MP4
# asset so the Windows Qt/FFmpeg backend is not exercising DRM or WebM.
HLS_URL = "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_ts/master.m3u8"
DASH_URL = "https://storage.googleapis.com/shaka-demo-assets/dig-the-uke-clear/dash.mpd"


def _play_remote_adaptive_stream(
    url: str,
    *,
    through_proxy: bool = True,
) -> tuple[bool, str | None, int]:
    from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

    QCoreApplication.instance() or QCoreApplication([])
    proxy = MediaStreamProxy() if through_proxy else None
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
        if proxy is not None:
            play_url = proxy.prepare(source)
            assert play_url != url
        else:
            play_url = source.url
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
        if proxy is not None:
            proxy.close()


def test_qmediaplayer_plays_real_hls_through_proxy() -> None:
    ok, error, duration = _play_remote_adaptive_stream(HLS_URL)
    assert ok, f"HLS playback failed: {error or 'unknown error'}; duration={duration}ms"


def test_qmediaplayer_plays_real_dash_direct() -> None:
    ok, error, duration = _play_remote_adaptive_stream(DASH_URL, through_proxy=False)
    assert ok, f"Direct DASH playback failed: {error or 'unknown error'}; duration={duration}ms"


def test_qmediaplayer_plays_real_dash_through_proxy() -> None:
    ok, error, duration = _play_remote_adaptive_stream(DASH_URL)
    assert ok, f"DASH playback through proxy failed: {error or 'unknown error'}; duration={duration}ms"
