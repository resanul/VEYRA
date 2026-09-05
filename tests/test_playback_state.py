from __future__ import annotations

from PySide6.QtCore import QSettings

from veyra.playback_state import PlaybackState, PlaybackStateStore


def test_preferences_round_trip() -> None:
    settings = QSettings("memory", "veyra-test")
    settings.clear()
    store = PlaybackStateStore(settings)
    state = PlaybackState(playback_rate=1.5, volume=0.65, muted=True)
    store.save_preferences(state)
    loaded = store.load_preferences()
    assert loaded.playback_rate == 1.5
    assert loaded.volume == 0.65
    assert loaded.muted is True


def test_source_track_state_round_trip_and_isolated() -> None:
    settings = QSettings("memory", "veyra-test-source")
    settings.clear()
    store = PlaybackStateStore(settings)
    state = PlaybackState(
        playback_rate=1.25,
        volume=0.8,
        audio_track=2,
        video_track=1,
        subtitle_track=-1,
        external_subtitle="https://example.test/subtitles/en.vtt",
    )
    store.save_source("https://media.test/movie.m3u8", state)

    loaded = store.load_source("https://media.test/movie.m3u8")
    assert loaded.audio_track == 2
    assert loaded.video_track == 1
    assert loaded.subtitle_track == -1
    assert loaded.external_subtitle.endswith("/en.vtt")
    assert loaded.playback_rate == 1.25
    assert store.load_source("https://media.test/other.m3u8").audio_track == -1


def test_proxy_session_tokens_share_source_state() -> None:
    settings = QSettings("memory", "veyra-test-proxy")
    settings.clear()
    store = PlaybackStateStore(settings)
    state = PlaybackState(playback_rate=1.75, audio_track=1)
    first = "http://127.0.0.1:50123/stream/token-a?url=https%3A%2F%2Fmedia.test%2Fmovie.m3u8"
    second = "http://127.0.0.1:50123/stream/token-b?url=https%3A%2F%2Fmedia.test%2Fmovie.m3u8"
    store.save_source(first, state)
    loaded = store.load_source(second)
    assert loaded.playback_rate == 1.75
    assert loaded.audio_track == 1


def test_state_normalizes_player_preferences() -> None:
    state = PlaybackState(playback_rate=99, volume=-2).normalized()
    assert state.playback_rate == 4.0
    assert state.volume == 0.0
