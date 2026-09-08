from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..download_manager import DownloadManager, DownloadTask
from .models import SearchResult, StreamSource


@dataclass(frozen=True, slots=True)
class ProviderDownloadRequest:
    """A resolved provider source ready for the persistent download queue."""

    source: StreamSource
    item: SearchResult | None = None
    filename: str | None = None


class ProviderDownloadBridge:
    """Translate provider stream sources into DownloadManager tasks.

    The current downloader handles byte-addressable HTTP(S) resources. HLS/DASH
    manifests remain playback-only until a segment-aware download pipeline is
    introduced; silently downloading a manifest would produce an unusable file.
    """

    _MANIFEST_FORMATS = {"m3u8", "hls", "mpd", "dash"}

    def __init__(self, manager: DownloadManager | None = None) -> None:
        self.manager = manager or DownloadManager()

    @classmethod
    def _is_manifest(cls, source: StreamSource) -> bool:
        if (source.format or "").lower() in cls._MANIFEST_FORMATS:
            return True
        lowered = source.url.split("?", 1)[0].lower()
        return lowered.endswith((".m3u8", ".mpd"))

    def enqueue(self, request: ProviderDownloadRequest) -> DownloadTask:
        source = request.source
        if not source.url.lower().startswith(("http://", "https://")):
            raise ValueError("provider downloads require an HTTP(S) source")
        if self._is_manifest(source):
            raise ValueError("HLS/DASH manifest downloads are not supported yet; choose a direct file source")

        filename = request.filename
        if not filename and request.item is not None:
            filename = request.item.title
            suffix = Path(source.url.split("?", 1)[0]).suffix
            if suffix and "." not in Path(filename).name:
                filename = f"{filename}{suffix}"
        task = self.manager.add(source.url, filename=filename)
        self.manager.start(task.id)
        return task

    def close(self) -> None:
        self.manager.shutdown()
