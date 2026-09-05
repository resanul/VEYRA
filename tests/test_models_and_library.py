from pathlib import Path

from veyra.library import MediaLibrary
from veyra.models import MediaItem, MediaType


def test_media_type_detection() -> None:
    assert MediaItem.from_source("movie.mkv").media_type is MediaType.VIDEO
    assert MediaItem.from_source("track.flac").media_type is MediaType.AUDIO
    assert MediaItem.from_source("https://example.com/video").media_type is MediaType.STREAM
    assert MediaItem.from_source("playlist.m3u8").media_type is MediaType.STREAM


def test_library_round_trip(tmp_path: Path) -> None:
    library_path = tmp_path / "library.json"
    item = MediaItem.from_source("movie.mp4")
    library = MediaLibrary(library_path)
    library.add(item)

    reloaded = MediaLibrary(library_path)
    assert reloaded.items == [item]

    reloaded.remove(item.id)
    assert reloaded.items == []
