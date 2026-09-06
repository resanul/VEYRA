from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from veyra.download_manager import DownloadManager, DownloadStatus


PAYLOAD = b"VEYRA-download-fixture-" * 4096


class RangeHandler(BaseHTTPRequestHandler):
    ranges: list[str | None] = []

    def do_GET(self) -> None:  # noqa: N802
        RangeHandler.ranges.append(self.headers.get("Range"))
        start = 0
        header = self.headers.get("Range")
        if header and header.startswith("bytes="):
            start = int(header.removeprefix("bytes=").split("-", 1)[0])
        body = PAYLOAD[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        if start:
            self.send_header("Content-Range", f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


@pytest.fixture()
def server():
    RangeHandler.ranges = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), RangeHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/media/test.bin"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


def wait_for(manager: DownloadManager, task_id: str, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get(task_id)
        if task and task.status in {DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED, DownloadStatus.PAUSED}:
            return task
        time.sleep(0.01)
    pytest.fail("download worker did not finish in time")


def test_filename_from_url_is_safe() -> None:
    assert DownloadManager.filename_from_url("https://example.test/a%20movie") == "a movie"
    # Windows treats a colon after the first path character as a drive designator;
    # Path.name therefore returns the safe basename that VEYRA will persist.
    assert DownloadManager.filename_from_url("https://example.test/a:b.mp4") == "b.mp4"


def test_download_persists_and_completes(server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files")
    task = manager.add(server)
    manager.start(task.id)
    result = wait_for(manager, task.id)

    target = tmp_path / "files" / "test.bin"
    assert result.status is DownloadStatus.COMPLETED
    assert target.read_bytes() == PAYLOAD
    assert result.downloaded_bytes == len(PAYLOAD)
    assert result.total_bytes == len(PAYLOAD)
    assert result.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    assert not (tmp_path / "files" / ".test.bin.part").exists()

    reopened = DownloadManager(tmp_path / "downloads.db", tmp_path / "files")
    restored = reopened.get(task.id)
    assert restored is not None
    assert restored.status is DownloadStatus.COMPLETED


def test_partial_file_resumes_with_range(server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files")
    task = manager.add(server)
    part = tmp_path / "files" / ".test.bin.part"
    part.write_bytes(PAYLOAD[:100])

    manager.start(task.id)
    result = wait_for(manager, task.id)

    assert result.status is DownloadStatus.COMPLETED
    assert (tmp_path / "files" / "test.bin").read_bytes() == PAYLOAD
    assert RangeHandler.ranges[-1] == "bytes=100-"
