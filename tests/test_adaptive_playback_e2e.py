from __future__ import annotations

import shutil
import subprocess

import pytest

from veyra.providers.media_proxy import MediaStreamProxy
from veyra.providers.models import StreamSource


pytestmark = pytest.mark.e2e

# Public clear adaptive streams used for player compatibility/regression
# testing. Both are decoded by the same native FFmpeg path so the E2E test
# validates manifest rewriting, segment delivery and actual media decoding
# without depending on a platform-specific Qt Multimedia backend.
HLS_URL = "https://devstreaming-cdn.apple.com/videos/streaming/examples/img_bipbop_adv_example_ts/master.m3u8"
DASH_URL = "https://storage.googleapis.com/shaka-demo-assets/dig-the-uke-clear/dash.mpd"


def _decode_through_proxy(url: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.fail("ffmpeg is required for adaptive playback E2E")

    proxy = MediaStreamProxy()
    try:
        source = StreamSource(
            url=url,
            headers={
                "User-Agent": "VEYRA/0.3.2 adaptive-e2e",
                "Referer": "https://provider.example/",
            },
        )
        play_url = proxy.prepare(source)
        assert play_url != url

        result = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-loglevel",
                "error",
                "-nostdin",
                "-i",
                play_url,
                "-t",
                "3",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        stderr = (result.stderr or "").strip()
        assert result.returncode == 0, (
            f"FFmpeg playback through proxy failed for {url}: "
            f"{stderr or 'unknown ffmpeg error'}"
        )
    finally:
        proxy.close()


def test_ffmpeg_decodes_real_hls_through_proxy() -> None:
    _decode_through_proxy(HLS_URL)


def test_ffmpeg_decodes_real_dash_through_proxy() -> None:
    _decode_through_proxy(DASH_URL)
