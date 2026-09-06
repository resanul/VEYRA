from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from veyra.download_manager import DownloadManager, DownloadStatus, DownloadTask


PAYLOAD = b"VEYRA-download-fixture-" * 20000


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


class SlowHandler(BaseHTTPRequestHandler):
    active = 0
    peak = 0
    lock = threading.Lock()
    hold_next_request = False
    first_chunk_sent = threading.Event()
    release_held_request = threading.Event()

    def do_GET(self) -> None:  # noqa: N802
        with SlowHandler.lock:
            SlowHandler.active += 1
            SlowHandler.peak = max(SlowHandler.peak, SlowHandler.active)
            hold_request = SlowHandler.hold_next_request
            SlowHandler.hold_next_request = False
        try:
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            for offset in range(0, len(PAYLOAD), 1024):
                self.wfile.write(PAYLOAD[offset:offset + 1024])
                self.wfile.flush()
                if offset == 0 and hold_request:
                    SlowHandler.first_chunk_sent.set()
                    SlowHandler.release_held_request.wait(timeout=15)
                time.sleep(0.01)
        finally:
            with SlowHandler.lock:
                SlowHandler.active -= 1

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


@pytest.fixture()
def slow_server():
    SlowHandler.active = 0
    SlowHandler.peak = 0
    SlowHandler.hold_next_request = False
    SlowHandler.first_chunk_sent = threading.Event()
    SlowHandler.release_held_request = threading.Event()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/media/slow.bin"
    finally:
        SlowHandler.release_held_request.set()
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


def wait_for_status(manager: DownloadManager, task_id: str, status: DownloadStatus, timeout: float = 5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get(task_id)
        if task and task.status is status:
            return task
        time.sleep(0.01)
    pytest.fail(f"download did not reach {status.value}")


def wait_for_partial(manager: DownloadManager, task_id: str, timeout: float = 5.0) -> DownloadTask:
    """Wait for persisted worker progress, independent of socket timing."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = manager.get(task_id)
        if task and task.downloaded_bytes > 0:
            return task
        time.sleep(0.01)
    pytest.fail("download did not persist partial progress in time")


def wait_for_no_active(manager: DownloadManager, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if manager.active_count() == 0:
            return
        time.sleep(0.01)
    pytest.fail("download worker did not release its worker slot in time")


def test_filename_from_url_is_safe() -> None:
    assert DownloadManager.filename_from_url("https://example.test/a%20movie") == "a movie"
    assert DownloadManager.filename_from_url("https://example.test/a:b.mp4") == "b.mp4"


def test_download_persists_and_completes(server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files")
    task = manager.add(server)
    manager.start(task.id)
    result = wait_for(manager, task.id)
    assert result.status is DownloadStatus.COMPLETED
    assert (tmp_path / "files" / "test.bin").read_bytes() == PAYLOAD
    assert result.sha256 == hashlib.sha256(PAYLOAD).hexdigest()
    reopened = DownloadManager(tmp_path / "downloads.db", tmp_path / "files")
    assert reopened.get(task.id).status is DownloadStatus.COMPLETED
    manager.shutdown()
    reopened.shutdown()


def test_partial_file_resumes_with_range(server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files")
    task = manager.add(server)
    (tmp_path / "files" / ".test.bin.part").write_bytes(PAYLOAD[:100])
    manager.start(task.id)
    result = wait_for(manager, task.id)
    assert result.status is DownloadStatus.COMPLETED
    assert (tmp_path / "files" / "test.bin").read_bytes() == PAYLOAD
    assert RangeHandler.ranges[-1] == "bytes=100-"
    manager.shutdown()


def test_queue_respects_max_concurrency(slow_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=2)
    tasks = [manager.add(slow_server, filename=f"file-{index}.bin") for index in range(4)]
    for task in tasks:
        manager.start(task.id)
    results = [wait_for(manager, task.id, timeout=10) for task in tasks]
    assert all(task.status is DownloadStatus.COMPLETED for task in results)
    assert SlowHandler.peak == 2
    manager.shutdown()


def test_start_all_only_uses_bounded_workers(slow_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=2)
    tasks = [manager.add(slow_server, filename=f"batch-{index}.bin") for index in range(3)]
    manager.start_all()
    results = [wait_for(manager, task.id, timeout=10) for task in tasks]
    assert all(task.status is DownloadStatus.COMPLETED for task in results)
    assert SlowHandler.peak == 2
    manager.shutdown()


def test_queued_pause_and_resume_preserve_queue_state(slow_server, tmp_path: Path) -> None:
    SlowHandler.hold_next_request = True
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    first = manager.add(slow_server, filename="first.bin")
    second = manager.add(slow_server, filename="second.bin")
    manager.start(first.id)
    assert SlowHandler.first_chunk_sent.wait(timeout=2)
    manager.start(second.id)
    wait_for_status(manager, first.id, DownloadStatus.DOWNLOADING)
    wait_for_status(manager, second.id, DownloadStatus.QUEUED)
    manager.pause(second.id)
    assert manager.get(second.id).status is DownloadStatus.PAUSED
    assert manager.queued_count() == 0
    assert manager.active_count() == 1
    manager.resume(second.id)
    assert manager.get(second.id).status is DownloadStatus.QUEUED
    SlowHandler.release_held_request.set()
    assert wait_for(manager, first.id, timeout=10).status is DownloadStatus.COMPLETED
    assert wait_for(manager, second.id, timeout=10).status is DownloadStatus.COMPLETED
    manager.shutdown()


def test_pause_active_then_resume_downloads_from_partial(slow_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add(slow_server, filename="pause.bin")
    manager.start(task.id)
    wait_for_partial(manager, task.id)
    wait_for_status(manager, task.id, DownloadStatus.DOWNLOADING)
    manager.pause(task.id)
    paused = wait_for_status(manager, task.id, DownloadStatus.PAUSED)
    assert paused.downloaded_bytes > 0
    manager.resume(task.id)
    result = wait_for(manager, task.id, timeout=10)
    assert result.status is DownloadStatus.COMPLETED
    assert (tmp_path / "files" / "pause.bin").read_bytes() == PAYLOAD
    manager.shutdown()


def test_cancel_queued_task_does_not_consume_worker_slot(slow_server, tmp_path: Path) -> None:
    SlowHandler.hold_next_request = True
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    first = manager.add(slow_server, filename="running.bin")
    cancelled = manager.add(slow_server, filename="cancelled.bin")
    manager.start(first.id)
    assert SlowHandler.first_chunk_sent.wait(timeout=2)
    manager.start(cancelled.id)
    wait_for_status(manager, first.id, DownloadStatus.DOWNLOADING)
    wait_for_status(manager, cancelled.id, DownloadStatus.QUEUED)
    manager.cancel(cancelled.id)
    assert manager.get(cancelled.id).status is DownloadStatus.CANCELLED
    assert manager.active_count() == 1
    assert not (tmp_path / "files" / "cancelled.bin").exists()
    manager.cancel(first.id)
    assert wait_for(manager, first.id).status is DownloadStatus.CANCELLED
    SlowHandler.release_held_request.set()
    wait_for_no_active(manager)
    manager.shutdown()


def test_cancel_active_can_delete_partial(slow_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add(slow_server, filename="delete.bin")
    manager.start(task.id)
    wait_for_partial(manager, task.id)
    wait_for_status(manager, task.id, DownloadStatus.DOWNLOADING)
    manager.cancel(task.id, delete_partial=True)
    assert wait_for(manager, task.id).status is DownloadStatus.CANCELLED
    wait_for_no_active(manager)
    assert not (tmp_path / "files" / ".delete.bin.part").exists()
    assert not (tmp_path / "files" / "delete.bin").exists()
    manager.shutdown()
