from __future__ import annotations

from dataclasses import dataclass, field

from .models import SearchResult, StreamSource


@dataclass(frozen=True, slots=True)
class PlayRequest:
    """Resolved playback request passed from a catalog to the media engine."""

    source: StreamSource
    item: SearchResult | None = None
    title: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    subtitles: tuple[str, ...] = ()

    @classmethod
    def from_source(cls, source: StreamSource, item: SearchResult | None = None) -> "PlayRequest":
        return cls(
            source=source,
            item=item,
            title=item.title if item else None,
            headers=dict(source.headers),
            subtitles=tuple(source.subtitles),
        )
