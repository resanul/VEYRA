from __future__ import annotations

from pathlib import Path
from typing import Iterable
from urllib.parse import quote

from .models import SearchResult, StreamSource


VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".flv",
}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".aac", ".wav", ".ogg", ".m4a", ".opus"}


class LocalMediaProvider:
    id = "local"
    name = "Local Media"

    def __init__(self, roots: Iterable[Path] = ()) -> None:
        self.roots = tuple(roots)

    def search(self, query: str) -> list[SearchResult]:
        needle = query.casefold().strip()
        if not needle:
            return []
        results: list[SearchResult] = []
        for root in self.roots:
            if not root.exists():
                continue
            try:
                iterator = root.rglob("*")
                for path in iterator:
                    if not path.is_file() or path.suffix.casefold() not in VIDEO_EXTENSIONS | AUDIO_EXTENSIONS:
                        continue
                    if needle not in path.name.casefold():
                        continue
                    kind = "video" if path.suffix.casefold() in VIDEO_EXTENSIONS else "audio"
                    results.append(SearchResult(
                        id=str(path.resolve()),
                        title=path.stem,
                        url=path.as_uri(),
                        kind=kind,
                    ))
            except OSError:
                continue
        return results

    def streams(self, item: SearchResult) -> list[StreamSource]:
        if item.url.startswith("file://"):
            return [StreamSource(url=item.url, quality="original", format=Path(quote(item.url, safe=":/%')).suffix or None)]
        return []
