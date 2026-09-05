from veyra.playback_tracks import TrackKind, format_track_label, make_track_info


def test_audio_track_label_contains_language_and_codec() -> None:
    track = make_track_info(
        TrackKind.AUDIO,
        0,
        language="English",
        codec="AAC",
    )
    assert format_track_label(track) == "English · AAC"


def test_subtitle_track_uses_title_when_language_missing() -> None:
    track = make_track_info(
        TrackKind.SUBTITLE,
        1,
        title="English SDH",
    )
    assert track.title == "English SDH"
    assert format_track_label(track) == "English SDH"


def test_video_track_includes_resolution_detail() -> None:
    track = make_track_info(
        TrackKind.VIDEO,
        1,
        title="Main",
        codec="H.264",
        detail="1920x1080",
    )
    assert format_track_label(track) == "Main · H.264 · 1920x1080"


def test_empty_metadata_has_stable_fallback_name() -> None:
    track = make_track_info(TrackKind.AUDIO, 2)
    assert track.title == "Audio 3"
