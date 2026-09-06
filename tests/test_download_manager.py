from __future__ import annotations

import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from veyra.download_manager import DownloadManager, DownloadStatus


PAYLOAD = b"VEYRA-download-fixture-" * 11264


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

    def do_GET(self) -> None:  # noqa: N802
        with SlowHandler.lock:
            SlowHandler.active += 1
            SlowHandler.peak = max(SlowHandler.peak, SlowHandler.active)
        try:
            self.send_response(200)
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            for offset in range(0, len(PAYLOAD), 1024):
                self.wfile.write(PAYLOAD[offset:offset + 1024])
                self.wfile.flush()
                time.sleep(0.01)
        finally:
            with SlowHandler.lock:
                SlowHandler.active -= 1

    def log_message(self, *_args) -> None:
        return


class GateHandler(BaseHTTPRequestHandler):
    started = threading.Event()
    release = threading.Event()

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Length", str(len(PAYLOAD)))
        self.end_headers()
        first_chunk_size = 256 * 1024
        self.wfile.write(PAYLOAD[:first_chunk_size])
        self.wfile.flush()
        GateHandler.started.set()
        GateHandler.release.wait(timeout=10)
        self.wfile.write(PAYLOAD[first_chunk_size:])
        self.wfile.flush()

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
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), SlowHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/media/slow.bin"
    finally:
        httpd.shutdown()
        thread.join(timeout=2)


@pytest.fixture()
def gate_server():
    GateHandler.started = threading.Event()
    GateHandler.release = threading.Event()
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GateHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_port}/media/gated.bin"
    finally:
        GateHandler.release.set()
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


def test_queued_pause_and_resume_preserve_queue_state(gate_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    first = manager.add(gate_server, filename="first.bin")
    second = manager.add(gate_server, filename="second.bin")
    manager.start(first.id)
    assert GateHandler.started.wait(5)
    manager.start(second.id)
    wait_for_status(manager, first.id, DownloadStatus.DOWNLOADING)
    wait_for_status(manager, second.id, DownloadStatus.QUEUED)
    manager.pause(second.id)
    assert manager.get(second.id).status is DownloadStatus.PAUSED
    assert manager.queued_count() == 0
    assert manager.active_count() == 1
    manager.resume(second.id)
    assert manager.get(second.id).status is DownloadStatus.QUEUED
    GateHandler.release.set()
    assert wait_for(manager, first.id, timeout=10).status is DownloadStatus.COMPLETED
    assert wait_for(manager, second.id, timeout=10).status is DownloadStatus.COMPLETED
    manager.shutdown()


def test_pause_active_then_resume_downloads_from_partial(gate_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add(gate_server, filename="pause.bin")
    manager.start(task.id)
    assert GateHandler.started.wait(5)
    wait_for_status(manager, task.id, DownloadStatus.DOWNLOADING)
    manager.pause(task.id)
    GateHandler.release.set()
    paused = wait_for_status(manager, task.id, DownloadStatus.PAUSED)
    assert paused.downloaded_bytes > 0
    manager.resume(task.id)
    result = wait_for(manager, task.id, timeout=10)
    assert result.status is DownloadStatus.COMPLETED
    assert (tmp_path / "files" / "pause.bin").read_bytes() == PAYLOAD
    manager.shutdown()


def test_cancel_queued_task_does_not_consume_worker_slot(gate_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    first = manager.add(gate_server, filename="running.bin")
    cancelled = manager.add(gate_server, filename="cancelled.bin")
    manager.start(first.id)
    assert GateHandler.started.wait(5)
    manager.start(cancelled.id)
    wait_for_status(manager, cancelled.id, DownloadStatus.QUEUED)
    manager.cancel(cancelled.id)
    assert manager.get(cancelled.id).status is DownloadStatus.CANCELLED
    assert manager.active_count() == 1
    assert not (tmp_path / "files" / "cancelled.bin").exists()
    manager.cancel(first.id)
    GateHandler.release.set()
    assert wait_for(manager, first.id).status is DownloadStatus.CANCELLED
    manager.shutdown()


def test_cancel_active_can_delete_partial(gate_server, tmp_path: Path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", max_concurrent=1)
    task = manager.add(gate_server, filename="delete.bin")
    manager.start(task.id)
    assert GateHandler.started.wait(5)
    wait_for_status(manager, task.id, DownloadStatus.DOWNLOADING)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        current = manager.get(task.id)
        if current and current.downloaded_bytes > 0:
            break
        time.sleep(0.01)
    assert manager.get(task.id).downloaded_bytes > 0
    manager.cancel(task.id, delete_partial=True)
    GateHandler.release.set()
    assert wait_for(manager, task.id).status is DownloadStatus.CANCELLED
    assert not (tmp_path / "files" / ".delete.bin.part").exists()
    assert not (tmp_path / "files" / "delete.bin").exists()
    manager.shutdown()
