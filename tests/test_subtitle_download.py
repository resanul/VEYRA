from __future__ import annotations

from dataclasses import dataclass

import pytest

from veyra.download_manager import DownloadStatus, DownloadTask
from veyra.subtitle_download import SubtitleDownloadBridge, SubtitleDownloadRequest


@dataclass
class FakeManager:
    added: list[tuple[str, str]]
    started: list[str]

    def add(self, url: str, *, filename: str | None = None):
        task = DownloadTask(
            id=f"task-{len(self.added) + 1}",
            url=url,
            destination="downloads",
            filename=filename or "download",
            status=DownloadStatus.QUEUED,
        )
        self.added.append((url, task.filename))
        return task

    def start(self, task_id: str) -> None:
        self.started.append(task_id)


def test_filename_uses_title_language_and_known_extension() -> None:
    request = SubtitleDownloadRequest(
        "https://cdn.example.test/subtitles/movie.vtt",
        title="My Movie",
        language="en",
    )
    assert SubtitleDownloadBridge.filename_for(request) == "My Movie.en.vtt"


def test_filename_defaults_to_srt_for_extensionless_url() -> None:
    request = SubtitleDownloadRequest(
        "https://cdn.example.test/subtitles/123",
        title="My Movie",
    )
    assert SubtitleDownloadBridge.filename_for(request) == "My Movie.srt"


def test_enqueue_uses_persistent_download_manager() -> None:
    manager = FakeManager([], [])
    bridge = SubtitleDownloadBridge(manager)
    task = bridge.enqueue_url(
        "https://cdn.example.test/subtitles/movie.srt",
        title="My Movie",
        language="bn",
    )
    assert manager.added == [("https://cdn.example.test/subtitles/movie.srt", "My Movie.bn.srt")]
    assert manager.started == [task.id]


@pytest.mark.parametrize(
    "url",
    [
        "file:///tmp/subtitle.srt",
        "ftp://cdn.example.test/subtitle.srt",
        "https://cdn.example.test/playlist.m3u8",
        "https://cdn.example.test/manifest.mpd",
    ],
)
def test_enqueue_rejects_unsupported_sources(url: str) -> None:
    bridge = SubtitleDownloadBridge(FakeManager([], []))
    with pytest.raises(ValueError):
        bridge.enqueue_url(url)
