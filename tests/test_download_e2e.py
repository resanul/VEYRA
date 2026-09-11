from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from veyra.download_manager import DownloadManager, DownloadStatus


PAYLOAD = b"VEYRA-download-e2e-fixture-" * 8192


class DownloadHandler(BaseHTTPRequestHandler):
    requests = 0
    ranges: list[str | None] = []

    def do_GET(self) -> None:  # noqa: N802
        DownloadHandler.requests += 1
        header = self.headers.get("Range")
        DownloadHandler.ranges.append(header)
        start = 0
        if header and header.startswith("bytes="):
            start = int(header.removeprefix("bytes=").split("-", 1)[0])

        body = PAYLOAD[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        if start:
            self.send_header(
                "Content-Range",
                f"bytes {start}-{len(PAYLOAD) - 1}/{len(PAYLOAD)}",
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args) -> None:
        return


@pytest.fixture()
def download_server():
    DownloadHandler.requests = 0
    DownloadHandler.ranges = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), DownloadHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/media/fixture.bin"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def wait_for_completion(manager: DownloadManager, task_id: str, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get(task_id)
        if task and task.status in {
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELLED,
            DownloadStatus.PAUSED,
        }:
            return task
        time.sleep(0.01)
    task = manager.get(task_id)
    pytest.fail(
        "download E2E timed out: "
        f"status={task.status.value if task else None}, "
        f"error={task.error if task else None}"
    )


@pytest.mark.e2e
def test_download_e2e_completes_persists_and_verifies(download_server, tmp_path: Path) -> None:
    database = tmp_path / "downloads.db"
    destination = tmp_path / "downloads"
    manager = DownloadManager(database, destination)

    try:
        task = manager.add(download_server, filename="fixture.bin")
        manager.start(task.id)
        result = wait_for_completion(manager, task.id)

        assert result.status is DownloadStatus.COMPLETED
        assert result.downloaded_bytes == len(PAYLOAD)
        assert result.total_bytes == len(PAYLOAD)
        assert result.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
        assert (destination / "fixture.bin").read_bytes() == PAYLOAD
        assert not (destination / ".fixture.bin.part").exists()
        assert DownloadHandler.requests >= 1

        reopened = DownloadManager(database, destination)
        try:
            persisted = reopened.get(task.id)
            assert persisted is not None
            assert persisted.status is DownloadStatus.COMPLETED
            assert persisted.sha256 == result.sha256
            assert persisted.downloaded_bytes == len(PAYLOAD)
        finally:
            reopened.shutdown()
    finally:
        manager.shutdown()
