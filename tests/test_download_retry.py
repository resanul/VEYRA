from __future__ import annotations

from pathlib import Path
from urllib.error import URLError

from veyra import download_manager as download_module
from veyra.download_manager import DownloadManager, DownloadStatus


PAYLOAD = b"VEYRA-retry-fixture-" * 200


class FakeResponse:
    def __init__(self, body: bytes, *, status: int = 200, fail_after: int | None = None) -> None:
        self.status = status
        self.headers = {"Content-Length": str(len(body))}
        self._body = body
        self._offset = 0
        self._fail_after = fail_after
        self._failed = False

    def read(self, size: int = -1) -> bytes:
        if self._fail_after is not None and not self._failed and self._offset >= self._fail_after:
            self._failed = True
            raise URLError("simulated connection reset")
        if self._offset >= len(self._body):
            return b""
        end = len(self._body) if size < 0 else min(len(self._body), self._offset + size)
        if self._fail_after is not None:
            end = min(end, self._fail_after)
        chunk = self._body[self._offset:end]
        self._offset = end
        return chunk

    def close(self) -> None:
        return

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args) -> None:
        self.close()


def test_midstream_network_failure_resumes_from_partial(monkeypatch, tmp_path: Path) -> None:
    calls: list[str | None] = []
    first_cut = 8192

    def fake_urlopen(request, timeout):
        del timeout
        range_header = request.headers.get("Range")
        calls.append(range_header)
        if len(calls) == 1:
            return FakeResponse(PAYLOAD, fail_after=first_cut)
        assert range_header == f"bytes={first_cut}-"
        return FakeResponse(PAYLOAD[first_cut:], status=206)

    monkeypatch.setattr(download_module, "urlopen", fake_urlopen)
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add("https://example.test/retry.bin")
    manager.start(task.id)
    result = manager.get(task.id)

    assert result is not None
    assert result.status is DownloadStatus.COMPLETED
    assert (tmp_path / "files" / "retry.bin").read_bytes() == PAYLOAD
    assert calls == [None, f"bytes={first_cut}-"]
    assert result.downloaded_bytes == len(PAYLOAD)
    manager.shutdown()


def test_initial_network_failures_are_retried(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        del request, timeout
        calls += 1
        if calls < 3:
            raise URLError("temporary network unavailable")
        return FakeResponse(PAYLOAD)

    monkeypatch.setattr(download_module, "urlopen", fake_urlopen)
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add("https://example.test/retry.bin")
    manager.start(task.id)
    result = manager.get(task.id)

    assert result is not None
    assert result.status is DownloadStatus.COMPLETED
    assert calls == 3
    assert (tmp_path / "files" / "retry.bin").read_bytes() == PAYLOAD
    manager.shutdown()


def test_network_failure_after_retry_budget_marks_task_failed(monkeypatch, tmp_path: Path) -> None:
    calls = 0

    def fake_urlopen(request, timeout):
        nonlocal calls
        del request, timeout
        calls += 1
        raise URLError("network unavailable")

    monkeypatch.setattr(download_module, "urlopen", fake_urlopen)
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add("https://example.test/retry.bin")
    manager.start(task.id)
    result = manager.get(task.id)

    assert result is not None
    assert result.status is DownloadStatus.FAILED
    assert "after 4 attempts" in (result.error or "")
    assert calls == manager.MAX_RETRIES + 1
    manager.shutdown()
