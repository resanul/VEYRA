from __future__ import annotations

from urllib.parse import urlsplit

from veyra.providers.media_proxy import MediaStreamProxy, _MediaProxyServer, _decode_url, _encode_url
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
        assert "/stream/" in parts.path
        assert _decode_url(parts.path.rsplit("/", 1)[-1]) == source.url
        assert parts.port == proxy.port
    finally:
        proxy.close()


def test_hls_manifest_rewrites_uri_and_segments() -> None:
    server = _MediaProxyServer(("127.0.0.1", 0))
    try:
        token = "test-token"
        body = "#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI=\"keys/key.bin\"\n#EXTINF:5,\nsegments/one.ts\n"
        rewritten = server.rewrite_manifest(None, "https://cdn.example/path/master.m3u8", body.encode(), token).decode()
        assert f"/stream/{token}/" in rewritten
        assert _encode_url("https://cdn.example/path/keys/key.bin") in rewritten
        assert _encode_url("https://cdn.example/path/segments/one.ts") in rewritten
    finally:
        server.server_close()


def test_dash_manifest_rewrites_segment_attributes_and_base_url() -> None:
    server = _MediaProxyServer(("127.0.0.1", 0))
    try:
        token = "test-token"
        body = "<MPD><BaseURL>video/</BaseURL><SegmentTemplate media=\"chunk-$Number$.m4s\" initialization=\"init.mp4\"/></MPD>"
        rewritten = server.rewrite_manifest(None, "https://cdn.example/path/manifest.mpd", body.encode(), token).decode()
        assert _encode_url("https://cdn.example/path/video/") in rewritten
        assert _encode_url("https://cdn.example/path/chunk-$Number$.m4s") in rewritten
        assert _encode_url("https://cdn.example/path/init.mp4") in rewritten
    finally:
        server.server_close()
