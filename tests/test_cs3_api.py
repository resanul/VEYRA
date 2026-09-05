from pathlib import Path

from veyra.extensions.cs3 import CS3Sidecar, CS3RuntimeUnavailable
from veyra.extensions.cs3_api import CloudStreamApiBridge, search_result_from_cloudstream, stream_source_from_cloudstream


def test_main_api_and_extractor_registration_contract() -> None:
    bridge = CloudStreamApiBridge()
    provider = bridge.register_main_api({
        "internalName": "demo",
        "name": "Demo Provider",
        "mainUrl": "https://example.test",
        "tvTypes": ["Movie", "TvSeries"],
        "language": "en",
    })
    extractor = bridge.register_extractor_api({
        "name": "DemoExtractor",
        "domains": ["video.example.test"],
        "requiresReferer": True,
    })
    assert provider.id == "demo"
    assert "Movie" in provider.supported_types
    assert extractor.requires_referer is True


def test_cloudstream_item_and_stream_translation() -> None:
    item = search_result_from_cloudstream({
        "id": "movie-1", "title": "Demo Movie", "url": "https://example.test/movie",
        "type": "movie", "year": "2026", "posterUrl": "https://example.test/poster.jpg",
    })
    stream = stream_source_from_cloudstream({
        "url": "https://cdn.example.test/video.m3u8", "quality": "1080p", "format": "hls",
        "headers": {"Referer": "https://example.test"}, "subtitles": ["https://example.test/en.vtt"],
    })
    assert item.id == "movie-1"
    assert item.year == 2026
    assert stream.format == "hls"
    assert stream.headers["Referer"] == "https://example.test"
    assert stream.subtitles == ("https://example.test/en.vtt",)


def test_sidecar_without_runtime_is_explicitly_unavailable() -> None:
    sidecar = CS3Sidecar(executable=Path("does-not-exist.exe"))
    assert sidecar.available is False
    try:
        sidecar.request("home", Path("demo.cs3"))
    except CS3RuntimeUnavailable:
        pass
    else:
        raise AssertionError("missing sidecar must be unavailable")
