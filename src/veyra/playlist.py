from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Playlist:
    name: str
    items: list[str]


class PlaylistStore:
    """Persistent named playlists for local media and stream URLs."""

    def __init__(self, storage: Path | None = None) -> None:
        self.storage = storage or (Path.home() / "AppData" / "Local" / "VEYRA" / "playlists.json")
        self.playlists: dict[str, Playlist] = {}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.storage.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return
        if not isinstance(data, list):
            return
        for row in data:
            if not isinstance(row, dict) or not row.get("name"):
                continue
            items = row.get("items", [])
            if isinstance(items, list):
                self.playlists[str(row["name"])] = Playlist(str(row["name"]), [str(x) for x in items])

    def save(self) -> None:
        self.storage.parent.mkdir(parents=True, exist_ok=True)
        self.storage.write_text(
            json.dumps([asdict(p) for p in self.playlists.values()], indent=2),
            encoding="utf-8",
        )

    def create(self, name: str) -> Playlist:
        name = name.strip()
        if not name:
            raise ValueError("Playlist name cannot be empty")
        playlist = self.playlists.setdefault(name, Playlist(name, []))
        self.save()
        return playlist

    def add(self, name: str, source: str) -> Playlist:
        playlist = self.create(name)
        if source not in playlist.items:
            playlist.items.append(source)
            self.save()
        return playlist

    def remove(self, name: str, source: str) -> None:
        playlist = self.playlists.get(name)
        if not playlist:
            return
        playlist.items = [item for item in playlist.items if item != source]
        self.save()

    def delete(self, name: str) -> None:
        self.playlists.pop(name, None)
        self.save()
