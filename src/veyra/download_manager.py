from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import time
import uuid
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
    """Persistent, resumable download queue for VEYRA."""

    CHUNK_SIZE = 256 * 1024
    DEFAULT_TIMEOUT = 30.0

    def __init__(self, storage: Path | None = None, download_dir: Path | None = None) -> None:
        root = Path.home() / "AppData" / "Local" / "VEYRA"
        self.storage = storage or root / "downloads.db"
        self.download_dir = download_dir or root / "Downloads"
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._stop_events: dict[str, threading.Event] = {}
        self._pause_events: dict[str, threading.Event] = {}
        self._threads: dict[str, threading.Thread] = {}
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

    def add(
        self,
        url: str,
        *,
        filename: str | None = None,
        destination: Path | None = None,
    ) -> DownloadTask:
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

    def start(self, task_id: str) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status == DownloadStatus.COMPLETED:
                return
            thread = self._threads.get(task_id)
            if thread and thread.is_alive():
                return
            self._stop_events[task_id] = threading.Event()
            self._pause_events[task_id] = threading.Event()
            self._update(task_id, status=DownloadStatus.DOWNLOADING, error=None)
            thread = threading.Thread(target=self._worker, args=(task_id,), name=f"veyra-download-{task_id[:8]}", daemon=True)
            self._threads[task_id] = thread
            thread.start()

    def pause(self, task_id: str) -> None:
        with self._lock:
            event = self._pause_events.get(task_id)
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if event is not None and task.status == DownloadStatus.DOWNLOADING:
                event.set()
                self._update(task_id, status=DownloadStatus.PAUSED)

    def resume(self, task_id: str) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if task.status in {DownloadStatus.PAUSED, DownloadStatus.FAILED, DownloadStatus.QUEUED}:
                self.start(task_id)

    def cancel(self, task_id: str, *, delete_partial: bool = False) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                raise KeyError(task_id)
            event = self._stop_events.get(task_id)
            if event is not None:
                event.set()
            self._update(task_id, status=DownloadStatus.CANCELLED)
            if delete_partial:
                self._part_path(task).unlink(missing_ok=True)

    def remove(self, task_id: str, *, delete_file: bool = False) -> None:
        task = self.get(task_id)
        if task is None:
            return
        if task.status == DownloadStatus.DOWNLOADING:
            self.cancel(task_id, delete_partial=delete_file)
        if delete_file:
            Path(task.destination, task.filename).unlink(missing_ok=True)
            self._part_path(task).unlink(missing_ok=True)
        with self._connect() as db:
            db.execute("DELETE FROM downloads WHERE id = ?", (task_id,))
            db.commit()

    def shutdown(self) -> None:
        with self._lock:
            for event in self._stop_events.values():
                event.set()

    def _worker(self, task_id: str) -> None:
        try:
            self._download(task_id)
        except Exception as exc:  # noqa: BLE001 - worker boundary
            task = self.get(task_id)
            if task and task.status not in {DownloadStatus.CANCELLED, DownloadStatus.PAUSED}:
                self._update(task_id, status=DownloadStatus.FAILED, error=str(exc))
        finally:
            with self._lock:
                self._threads.pop(task_id, None)
                self._stop_events.pop(task_id, None)
                self._pause_events.pop(task_id, None)

    def _download(self, task_id: str) -> None:
        task = self.get(task_id)
        if task is None:
            return
        target = Path(task.destination) / task.filename
        part = self._part_path(task)
        existing = part.stat().st_size if part.exists() else 0
        headers = {"User-Agent": "VEYRA/0.3.2", "Accept": "*/*"}
        request = Request(task.url, headers=headers, method="GET")
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
                request = Request(task.url, headers=headers, method="GET")
                response = urlopen(request, timeout=self.DEFAULT_TIMEOUT)
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
            mode = "ab" if resumed else "wb"
            downloaded = existing
            with part.open(mode) as output:
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
                    hasher.update(chunk)
                    downloaded += len(chunk)
                    self._update(task_id, downloaded_bytes=downloaded, total_bytes=total)

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
