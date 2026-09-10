from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .download_manager import DownloadManager, DownloadTask


@dataclass(frozen=True, slots=True)
class SubtitleDownloadRequest:
    """A provider subtitle URL ready for the persistent download queue."""

    url: str
    title: str = "subtitle"
    language: str | None = None
    filename: str | None = None


class SubtitleDownloadBridge:
    """Queue external subtitle files through the persistent DownloadManager."""

    _MANIFEST_SUFFIXES = (".m3u8", ".mpd")
    _SUBTITLE_SUFFIXES = (".srt", ".vtt", ".ass", ".ssa")

    def __init__(self, manager: DownloadManager | None = None) -> None:
        self.manager = manager or DownloadManager()

    @classmethod
    def _validate_url(cls, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            raise ValueError("subtitle downloads require an HTTP(S) URL")
        path = parsed.path.lower()
        if path.endswith(cls._MANIFEST_SUFFIXES):
            raise ValueError("HLS/DASH manifests cannot be downloaded as subtitles")

    @classmethod
    def filename_for(cls, request: SubtitleDownloadRequest) -> str:
        if request.filename:
            return request.filename
        suffix = Path(urlparse(request.url).path).suffix.lower()
        if suffix not in cls._SUBTITLE_SUFFIXES:
            suffix = ".srt"
        title = request.title.strip() or "subtitle"
        language = (request.language or "").strip()
        if language:
            title = f"{title}.{language}"
        return f"{title}{suffix}"

    def enqueue(self, request: SubtitleDownloadRequest) -> DownloadTask:
        self._validate_url(request.url)
        task = self.manager.add(
            request.url,
            filename=self.filename_for(request),
        )
        self.manager.start(task.id)
        return task

    def enqueue_url(
        self,
        url: str,
        *,
        title: str = "subtitle",
        language: str | None = None,
        filename: str | None = None,
    ) -> DownloadTask:
        return self.enqueue(
            SubtitleDownloadRequest(
                url=url,
                title=title,
                language=language,
                filename=filename,
            )
        )

    def close(self) -> None:
        self.manager.shutdown()


__all__ = ["SubtitleDownloadBridge", "SubtitleDownloadRequest"]
