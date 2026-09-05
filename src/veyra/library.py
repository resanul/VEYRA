from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .models import MediaItem


class MediaLibrary:
    """Persistent local library foundation for VEYRA."""

    def __init__(self, storage: Path | None = None) -> None:
        self.storage = storage or (Path.home() / "AppData" / "Local" / "VEYRA" / "library.json")
        self.items: list[MediaItem] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.storage.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if isinstance(data, list):
            for row in data:
                if isinstance(row, dict) and {"id", "title", "source", "media_type"} <= row.keys():
                    self.items.append(
                        MediaItem(
                            id=str(row["id"]),
                            title=str(row["title"]),
                            source=str(row["source"]),
                            media_type=row["media_type"],
                        )
                    )

    def add(self, item: MediaItem) -> None:
        if not any(existing.id == item.id for existing in self.items):
            self.items.append(item)
            self.save()

    def add_many(self, items: Iterable[MediaItem]) -> None:
        for item in items:
            if not any(existing.id == item.id for existing in self.items):
                self.items.append(item)
        self.save()

    def remove(self, item_id: str) -> None:
        self.items = [item for item in self.items if item.id != item_id]
        self.save()

    def save(self) -> None:
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.storage.write_text(json.dumps([asdict(item) for item in self.items], indent=2), encoding="utf-8")
