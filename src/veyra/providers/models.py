from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class SearchResult:
    id: str
    title: str
    url: str
    kind: str = "unknown"
    year: int | None = None
    poster: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class StreamSource:
    url: str
    quality: str = "auto"
    format: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    subtitles: tuple[str, ...] = field(default_factory=tuple)
