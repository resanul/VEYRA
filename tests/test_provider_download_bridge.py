from __future__ import annotations

from types import SimpleNamespace

import pytest

from veyra.providers.download_bridge import ProviderDownloadBridge, ProviderDownloadRequest
from veyra.providers.models import SearchResult, StreamSource


class FakeManager:
    def __init__(self) -> None:
        self.added = []
        self.started = []

    def add(self, url: str, *, filename: str | None = None, destination=None):
        self.added.append((url, filename, destination))
        return SimpleNamespace(id="task-1", filename=filename or "download")

    def start(self, task_id: str) -> None:
        self.started.append(task_id)


def test_enqueue_provider_direct_stream() -> None:
    manager = FakeManager()
    bridge = ProviderDownloadBridge(manager)  # type: ignore[arg-type]
    item = SearchResult(id="movie-1", title="VEYRA Movie", url="https://example.test/title")
    source = StreamSource(url="https://cdn.example.test/video.mp4", quality="1080p", format="mp4")

    task = bridge.enqueue(ProviderDownloadRequest(source=source, item=item))

    assert task.id == "task-1"
    assert manager.added[0][0] == source.url
    assert manager.added[0][1] == "VEYRA Movie.mp4"
    assert manager.started == ["task-1"]


def test_enqueue_rejects_manifest_downloads() -> None:
    bridge = ProviderDownloadBridge(FakeManager())  # type: ignore[arg-type]
    source = StreamSource(url="https://example.test/master.m3u8", format="m3u8")

    with pytest.raises(ValueError, match="manifest downloads are not supported"):
        bridge.enqueue(ProviderDownloadRequest(source=source))


def test_enqueue_rejects_non_http_provider_source() -> None:
    bridge = ProviderDownloadBridge(FakeManager())  # type: ignore[arg-type]
    source = StreamSource(url="file:///tmp/movie.mp4", format="mp4")

    with pytest.raises(ValueError, match="HTTP\(S\)"):
        bridge.enqueue(ProviderDownloadRequest(source=source))
