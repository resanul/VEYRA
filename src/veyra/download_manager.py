from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


class DownloadStatus(str, Enum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class DownloadTask:
    id: str
    url: str
    destination: str
    filename: str
    status: DownloadStatus
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: str | None = None
    created_at: float = 0.0
    updated_at: float = 0.0
    sha256: str | None = None

    @property
    def progress(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return min(1.0, max(0.0, self.downloaded_bytes / self.total_bytes))


class DownloadManager:
    """Persistent download queue with bounded concurrent workers and lifecycle controls."""

    # Keep socket reads bounded so pause/cancel checks are revisited frequently even
    # when the peer sends data slowly. A blocking read avoids read1() buffering quirks.
    CHUNK_SIZE = 8 * 1024
    DEFAULT_TIMEOUT = 30.0
    DEFAULT_MAX_CONCURRENT = 3

    def __init__(
        self,
        storage: Path | None = None,
        download_dir: Path | None = None,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        root = Path.home() / "AppData" / "Local" / "VEYRA"
        self.storage = storage or root / "downloads.db"
        self.download_dir = download_dir or root / "Downloads"
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = max_concurrent
        self._lock = threading.RLock()
        self._stop_events: dict[str, threading.Event] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._delete_partial_on_cancel: set[str] = set()
        self._futures: dict[str, Future[None]] = {}
        # Track admitted/running tasks explicitly instead of deriving worker state
        # from Future.done(), which has a small completion/cleanup race.
        self._running_tasks: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=max_concurrent, thread_name_prefix="veyra-download")
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.storage, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute(
                """CREATE TABLE IF NOT EXISTS downloads (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    destination TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    status TEXT NOT NULL,
                    downloaded_bytes INTEGER NOT NULL DEFAULT 0,
                    total_bytes INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    sha256 TEXT
                )"""
            )
            db.execute("CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status)")
            db.commit()

    @staticmethod
    def _safe_filename(value: str) -> str:
        value = Path(value).name.strip().replace("\x00", "")
        invalid = '<>:"/\\|?*'
        value = "".join("_" if char in invalid or ord(char) < 32 else char for char in value)
        value = value.rstrip(" .")
        return value[:240] or "download"

    @classmethod
    def filename_from_url(cls, url: str, fallback: str = "download") -> str:
        name = Path(unquote(urlparse(url).path)).name
        return cls._safe_filename(name or fallback)

    def add(self, url: str, *, filename: str | None = None, destination: Path | None = None) -> DownloadTask:
        if not url.lower().startswith(("http://", "https://")):
            raise ValueError("downloads require an HTTP(S) URL")
        name = self._safe_filename(filename or self.filename_from_url(url))
        directory = Path(destination or self.download_dir)
        directory.mkdir(parents=True, exist_ok=True)
        task_id = uuid.uuid4().hex
        now = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT INTO downloads VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (task_id, url, str(directory), name, DownloadStatus.QUEUED.value, 0, 0, None, now, now, None),
            )
            db.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def get(self, task_id: str) -> DownloadTask | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM downloads WHERE id = ?", (task_id,)).fetchone()
        return self._row_to_task(row) if row else None

    def list(self, *, statuses: set[DownloadStatus] | None = None) -> list[DownloadTask]:
        with self._connect() as db:
            if statuses:
                values = tuple(status.value for status in statuses)
                placeholders = ",".join("?" for _ in values)
                rows = db.execute(
                    f"SELECT * FROM downloads WHERE status IN ({placeholders}) ORDER BY created_at DESC", values
                ).fetchall()
            else:
                rows = db.execute("SELECT * FROM downloads ORDER BY created_at DESC").fetchall()
        return [self._row_to_task(row) for row in rows]

    def active_count(self) -> int:
        with self._lock:
            return len(self._running_tasks)

    def queued_count(self) -> int:
        return len(self.list(statuses={DownloadStatus.QUEUED}))

    def start(self, task_id: str) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status == DownloadStatus.COMPLETED:
                return
            if task_id in self._running_tasks:
                return
            future = self._futures.get(task_id)
            if future and not future.done():
                return
            self._delete_partial_on_cancel.discard(task_id)
            self._stop_events[task_id] = threading.Event()
            self._pause_events[task_id] = threading.Event()
            self._update(task_id, status=DownloadStatus.QUEUED, error=None)
            self._pump()

    def start_all(self) -> None:
        for task in self.list(statuses={DownloadStatus.QUEUED, DownloadStatus.FAILED}):
            self.start(task.id)

    def _pump(self) -> None:
        """Start FIFO queued work only while an actual worker slot is available."""
        with self._lock:
            available = max(0, self.max_concurrent - len(self._running_tasks))
            if available == 0:
                return
            queued = self.list(statuses={DownloadStatus.QUEUED})
            for task in queued:
                if available <= 0:
                    break
                if task.id in self._running_tasks:
                    continue
                self._stop_events.setdefault(task.id, threading.Event())
                self._pause_events.setdefault(task.id, threading.Event())
                self._update(task.id, status=DownloadStatus.DOWNLOADING, error=None)
                self._running_tasks.add(task.id)
                try:
                    self._futures[task.id] = self._executor.submit(self._worker, task.id)
                except Exception:
                    self._running_tasks.discard(task.id)
                    self._update(task.id, status=DownloadStatus.QUEUED)
                    raise
                available -= 1

    def pause(self, task_id: str) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status == DownloadStatus.QUEUED:
                self._update(task_id, status=DownloadStatus.PAUSED)
                return
            event = self._pause_events.get(task_id)
            if event is not None and task.status == DownloadStatus.DOWNLOADING:
                event.set()
                self._update(task_id, status=DownloadStatus.PAUSED)

    def resume(self, task_id: str) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status not in {DownloadStatus.PAUSED, DownloadStatus.FAILED, DownloadStatus.QUEUED}:
                return
            event = self._pause_events.get(task_id)
            if event is not None:
                event.clear()
            self._update(task_id, status=DownloadStatus.QUEUED, error=None)
            self._pump()

    def cancel(self, task_id: str, *, delete_partial: bool = False) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status == DownloadStatus.COMPLETED:
                return
            future = self._futures.get(task_id)
            stop = self._stop_events.get(task_id)
            running = task_id in self._running_tasks
            if running:
                if stop:
                    stop.set()
                if delete_partial:
                    self._delete_partial_on_cancel.add(task_id)
            else:
                if future and not future.running():
                    future.cancel()
                if delete_partial:
                    self._part_path(task).unlink(missing_ok=True)
                    (Path(task.destination) / task.filename).unlink(missing_ok=True)
            self._update(task_id, status=DownloadStatus.CANCELLED)
            self._pump()

    def remove(self, task_id: str, *, delete_file: bool = False) -> None:
        task = self.get(task_id)
        if task is None:
            return
        if task.status in {DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED}:
            self.cancel(task_id, delete_partial=delete_file)
        if delete_file:
            Path(task.destination, task.filename).unlink(missing_ok=True)
            self._part_path(task).unlink(missing_ok=True)
        with self._connect() as db:
            db.execute("DELETE FROM downloads WHERE id = ?", (task_id,))
            db.commit()

    def shutdown(self, wait: bool = True) -> None:
        with self._lock:
            for event in self._stop_events.values():
                event.set()
            self._executor.shutdown(wait=wait, cancel_futures=True)

    def _worker(self, task_id: str) -> None:
        try:
            self._download(task_id)
        except Exception as exc:  # noqa: BLE001 - worker boundary
            task = self.get(task_id)
            if task and task.status not in {DownloadStatus.CANCELLED, DownloadStatus.PAUSED}:
                self._update(task_id, status=DownloadStatus.FAILED, error=str(exc))
        finally:
            with self._lock:
                task = self.get(task_id)
                delete_partial = task_id in self._delete_partial_on_cancel
                self._running_tasks.discard(task_id)
                self._futures.pop(task_id, None)
                self._stop_events.pop(task_id, None)
                self._pause_events.pop(task_id, None)
                self._delete_partial_on_cancel.discard(task_id)
                if delete_partial and task is not None and task.status == DownloadStatus.CANCELLED:
                    self._part_path(task).unlink(missing_ok=True)
                    (Path(task.destination) / task.filename).unlink(missing_ok=True)
            self._pump()

    def _download(self, task_id: str) -> None:
        task = self.get(task_id)
        if task is None:
            return
        target = Path(task.destination) / task.filename
        part = self._part_path(task)
        existing = part.stat().st_size if part.exists() else 0
        request = Request(task.url, headers={"User-Agent": "VEYRA/0.3.2", "Accept": "*/*"}, method="GET")
        if existing:
            request.add_header("Range", f"bytes={existing}-")
        try:
            response = urlopen(request, timeout=self.DEFAULT_TIMEOUT)
        except HTTPError as exc:
            if existing and exc.code == 416:
                if target.exists() and target.stat().st_size == existing:
                    self._complete(task_id, target, existing)
                    return
                part.unlink(missing_ok=True)
                existing = 0
                response = urlopen(Request(task.url, headers={"User-Agent": "VEYRA/0.3.2", "Accept": "*/*"}, method="GET"), timeout=self.DEFAULT_TIMEOUT)
            else:
                raise
        except (URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"download request failed: {exc}") from exc

        with response:
            status = int(getattr(response, "status", 200))
            resumed = existing > 0 and status == 206
            if existing and not resumed:
                existing = 0
                part.unlink(missing_ok=True)
            content_length = response.headers.get("Content-Length")
            total = existing + int(content_length) if content_length and content_length.isdigit() else 0
            self._update(task_id, status=DownloadStatus.DOWNLOADING, downloaded_bytes=existing, total_bytes=total, error=None)
            hasher = hashlib.sha256()
            if existing:
                with part.open("rb") as previous:
                    for chunk in iter(lambda: previous.read(self.CHUNK_SIZE), b""):
                        hasher.update(chunk)
            downloaded = existing
            with part.open("ab" if resumed else "wb") as output:
                while True:
                    stop = self._stop_events.get(task_id)
                    pause = self._pause_events.get(task_id)
                    if stop and stop.is_set():
                        return
                    if pause and pause.is_set():
                        self._update(task_id, status=DownloadStatus.PAUSED, downloaded_bytes=downloaded, total_bytes=total)
                        return
                    chunk = response.read(self.CHUNK_SIZE)
                    if not chunk:
                        break
                    output.write(chunk)
                    output.flush()
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    self._update(task_id, downloaded_bytes=downloaded, total_bytes=total)

        with self._lock:
            stop = self._stop_events.get(task_id)
            pause = self._pause_events.get(task_id)
            current = self.get(task_id)
            if stop and stop.is_set():
                return
            if pause and pause.is_set():
                self._update(task_id, status=DownloadStatus.PAUSED, downloaded_bytes=downloaded, total_bytes=total)
                return
            if current is None or current.status == DownloadStatus.CANCELLED:
                return
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(part, target)
            self._complete(task_id, target, downloaded, hasher.hexdigest())

    def _complete(self, task_id: str, target: Path, size: int, digest: str | None = None) -> None:
        if digest is None:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
        self._update(task_id, status=DownloadStatus.COMPLETED, downloaded_bytes=size, total_bytes=size, error=None, sha256=digest)

    def _part_path(self, task: DownloadTask) -> Path:
        return Path(task.destination) / f".{task.filename}.part"

    def _update(self, task_id: str, **values: object) -> None:
        if not values:
            return
        values["updated_at"] = time.time()
        assignments = ", ".join(f"{key} = ?" for key in values)
        params = [getattr(value, "value", value) for value in values.values()]
        params.append(task_id)
        with self._connect() as db:
            db.execute(f"UPDATE downloads SET {assignments} WHERE id = ?", params)
            db.commit()

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> DownloadTask:
        return DownloadTask(
            id=str(row["id"]), url=str(row["url"]), destination=str(row["destination"]), filename=str(row["filename"]),
            status=DownloadStatus(str(row["status"])), downloaded_bytes=int(row["downloaded_bytes"]), total_bytes=int(row["total_bytes"]),
            error=row["error"], created_at=float(row["created_at"]), updated_at=float(row["updated_at"]), sha256=row["sha256"],
        )