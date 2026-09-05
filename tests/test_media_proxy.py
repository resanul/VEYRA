from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from veyra.providers.media_proxy import MediaStreamProxy, _MediaProxyServer
from veyra.providers.models import StreamSource


def test_prepare_keeps_plain_remote_url_without_request_headers() -> None:
    proxy = MediaStreamProxy()
    try:
        source = StreamSource(url="https://cdn.example/video.mp4")
        assert proxy.prepare(source) == source.url
    finally:
        proxy.close()


def test_prepare_wraps_authenticated_remote_source() -> None:
    proxy = MediaStreamProxy()
    try:
        source = StreamSource(
            url="https://cdn.example/video.m3u8",
            headers={"Referer": "https://example.test/", "Authorization": "Bearer token"},
        )
        wrapped = proxy.prepare(source)
        parts = urlsplit(wrapped)
        assert parts.hostname == "127.0.0.1"
        assert parts.path.startswith("/stream/")
        assert parse_qs(parts.query)["url"] == [source.url]
        assert parts.port == proxy.port
    finally:
        proxy.close()


def test_hls_manifest_rewrites_uri_and_segments() -> None:
    server = _MediaProxyServer(("127.0.0.1", 0))
    try:
        token = "test-token"
        body = "#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"keys/key.bin\"\n#EXTINF:5,\nsegments/one.ts\n"
        rewritten = server.rewrite_manifest("https://cdn.example/path/master.m3u8", body.encode(), token).decode()
        key_url = rewritten.split('URI="', 1)[1].split('"', 1)[0]
        segment_url = rewritten.splitlines()[-1]
        key_parts = urlsplit(key_url)
        segment_parts = urlsplit(segment_url)
        assert key_parts.path == f"/stream/{token}"
        assert segment_parts.path == f"/stream/{token}"
        assert "keys/key.bin" in parse_qs(key_parts.query)["url"][0]
        assert "segments/one.ts" in parse_qs(segment_parts.query)["url"][0]
    finally:
        server.server_close()


def test_dash_manifest_rewrites_segment_attributes_and_base_url() -> None:
    server = _MediaProxyServer(("127.0.0.1", 0))
    try:
        token = "test-token"
        body = "<MPD><BaseURL>video/</BaseURL><SegmentTemplate media=\"chunk-$Number$.m4s\" initialization=\"init.mp4\"/></MPD>"
        rewritten = server.rewrite_manifest("https://cdn.example/path/manifest.mpd", body.encode(), token).decode()
        assert "$Number$" in rewritten
        base_url = rewritten.split("<BaseURL>", 1)[1].split("</BaseURL>", 1)[0]
        media_url = rewritten.split('media="', 1)[1].split('"', 1)[0]
        init_url = rewritten.split('initialization="', 1)[1].split('"', 1)[0]
        assert "video/" in parse_qs(urlsplit(base_url).query)["url"][0]
        assert "chunk-$Number$.m4s" in parse_qs(urlsplit(media_url).query)["url"][0]
        assert "init.mp4" in parse_qs(urlsplit(init_url).query)["url"][0]
        assert urlsplit(base_url).path == f"/stream/{token}"
        assert urlsplit(media_url).path == f"/stream/{token}"
        assert urlsplit(init_url).path == f"/stream/{token}"
    finally:
        server.server_close()
