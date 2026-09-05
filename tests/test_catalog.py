from veyra.providers.models import SearchResult, StreamSource


def test_catalog_result_contract() -> None:
    result = SearchResult(id="1", title="Demo", url="https://example.test/demo", kind="movie", year=2026)
    source = StreamSource(url="https://example.test/video.m3u8", quality="1080p", format="hls")
    assert result.title == "Demo"
    assert source.quality == "1080p"
