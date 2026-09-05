from veyra.providers.stream_resolver import StreamResolver


HLS = '''#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360
low/index.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1920x1080
https://cdn.example.test/high/index.m3u8
'''

DASH = '''<?xml version="1.0"?>
<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">
  <Period>
    <AdaptationSet mimeType="video/mp4">
      <Representation id="360" bandwidth="800000" width="640" height="360">
        <BaseURL>video/360.mp4</BaseURL>
      </Representation>
      <Representation id="1080" bandwidth="5000000" width="1920" height="1080">
        <BaseURL>video/1080.mp4</BaseURL>
      </Representation>
    </AdaptationSet>
  </Period>
</MPD>'''


def test_detects_manifest_formats() -> None:
    assert StreamResolver.detect_format("https://example.test/master.m3u8") == "hls"
    assert StreamResolver.detect_format("https://example.test/manifest", HLS) == "hls"
    assert StreamResolver.detect_format("https://example.test/stream.mpd") == "dash"
    assert StreamResolver.detect_format("https://example.test/manifest", DASH) == "dash"
    assert StreamResolver.detect_format("https://example.test/video.mp4") == "direct"


def test_parses_hls_variants_and_resolves_urls() -> None:
    result = StreamResolver.parse_manifest(
        "https://media.example.test/master.m3u8",
        HLS,
        headers={"Authorization": "Bearer test"},
        referer="https://example.test/watch",
    )
    assert result.format == "hls"
    assert [source.quality for source in result.sources] == ["360p", "1080p"]
    assert result.sources[0].url == "https://media.example.test/low/index.m3u8"
    assert result.sources[1].url == "https://cdn.example.test/high/index.m3u8"
    assert result.sources[0].headers["Referer"] == "https://example.test/watch"


def test_parses_dash_base_urls_and_quality() -> None:
    result = StreamResolver.parse_manifest("https://media.example.test/manifest.mpd", DASH)
    assert result.format == "dash"
    assert [source.quality for source in result.sources] == ["360p", "1080p"]
    assert result.sources[0].url == "https://media.example.test/video/360.mp4"
    assert result.sources[1].url == "https://media.example.test/video/1080.mp4"


def test_direct_url_is_preserved() -> None:
    result = StreamResolver.parse_manifest(
        "https://cdn.example.test/video.mp4",
        "",
        headers={"User-Agent": "VEYRA"},
    )
    assert result.sources[0].url.endswith("video.mp4")
    assert result.sources[0].headers["User-Agent"] == "VEYRA"
