from pathlib import Path

from veyra.playlist import PlaylistStore


def test_playlist_roundtrip(tmp_path: Path) -> None:
    store = PlaylistStore(tmp_path / "playlists.json")
    store.add("Favorites", "movie.mkv")
    store.add("Favorites", "movie.mkv")
    store.add("Favorites", "https://example.test/video.m3u8")

    loaded = PlaylistStore(tmp_path / "playlists.json")
    assert loaded.playlists["Favorites"].items == [
        "movie.mkv",
        "https://example.test/video.m3u8",
    ]


def test_empty_playlist_name_rejected(tmp_path: Path) -> None:
    store = PlaylistStore(tmp_path / "playlists.json")
    try:
        store.create("   ")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError")
