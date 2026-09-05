from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class PlaybackRecord:
    source: str
    title: str
    position_ms: int = 0
    duration_ms: int = 0
    updated_at: float = 0.0

    @property
    def progress(self) -> float:
        if self.duration_ms <= 0:
            return 0.0
        return max(0.0, min(1.0, self.position_ms / self.duration_ms))


class PlaybackHistory:
    """Small persistent resume/history store for local and stream media."""

    def __init__(self, storage: Path | None = None) -> None:
        self.storage = storage or (Path.home() / "AppData" / "Local" / "VEYRA" / "history.json")
        self.records: dict[str, PlaybackRecord] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.storage.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for row in data:
            if not isinstance(row, dict) or "source" not in row or "title" not in row:
                continue
            try:
                record = PlaybackRecord(
                    source=str(row["source"]), title=str(row["title"]),
                    position_ms=max(0, int(row.get("position_ms", 0))),
                    duration_ms=max(0, int(row.get("duration_ms", 0))),
                    updated_at=float(row.get("updated_at", 0.0)),
                )
            except (TypeError, ValueError):
                continue
            self.records[record.source] = record

    def save_position(self, source: str, title: str, position_ms: int, duration_ms: int) -> None:
        import time
        self.records[source] = PlaybackRecord(
            source=source, title=title, position_ms=max(0, int(position_ms)),
            duration_ms=max(0, int(duration_ms)), updated_at=time.time()
        )
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self.records.values(), key=lambda item: item.updated_at, reverse=True)[:100]
        self.storage.write_text(json.dumps([asdict(item) for item in ordered], indent=2), encoding="utf-8")

    def get(self, source: str) -> PlaybackRecord | None:
        return self.records.get(source)

    def recent(self, limit: int = 20) -> list[PlaybackRecord]:
        return sorted(self.records.values(), key=lambda item: item.updated_at, reverse=True)[:limit]
