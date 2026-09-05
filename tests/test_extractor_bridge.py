from veyra.extensions.cs3_api import CS3ExtractorInfo
from veyra.extensions.cs3_runtime.extractor_bridge import ExtractorApiBridge, ExtractorRegistry


def test_registry_routes_subdomains_to_registered_extractors() -> None:
    registry = ExtractorRegistry()
    registry.register(CS3ExtractorInfo(name="Demo", domains=("example.test",)))

    matches = registry.for_url("https://cdn.example.test/watch/123")

    assert [item.name for item in matches] == ["Demo"]
    assert registry.get("demo") is not None


def test_extractor_bridge_registers_and_extracts_streams() -> None:
    calls = []

    def request(method, payload):
        calls.append((method, payload))
        return {"streams": [{
            "url": "https://cdn.example.test/video.m3u8",
            "quality": "1080p",
            "type": "m3u8",
            "headers": {"Referer": "https://example.test"},
            "subtitles": ["https://example.test/sub.vtt"],
        }]}

    bridge = ExtractorApiBridge(request)
    info = bridge.register({
        "name": "DemoExtractor",
        "domains": ["example.test"],
        "requiresReferer": True,
    })
    streams = bridge.extract("https://video.example.test/watch/1", referer="https://example.test")

    assert info.requires_referer is True
    assert streams[0].url.endswith("video.m3u8")
    assert streams[0].format == "m3u8"
    assert streams[0].headers["Referer"] == "https://example.test"
    assert streams[0].subtitles == ("https://example.test/sub.vtt",)
    assert calls[0][0] == "extract"
    assert calls[0][1]["extractor"] == "DemoExtractor"


def test_extractor_bridge_requires_registered_domain_when_name_omitted() -> None:
    bridge = ExtractorApiBridge(lambda *_: {"streams": []})
    try:
        bridge.extract("https://unknown.test/video")
    except LookupError as exc:
        assert "No registered extractor" in str(exc)
    else:
        raise AssertionError("expected LookupError")
