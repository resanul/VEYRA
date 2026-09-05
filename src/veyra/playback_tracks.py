from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class TrackKind(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
    SUBTITLE = "subtitle"


@dataclass(frozen=True, slots=True)
class TrackInfo:
    kind: TrackKind
    index: int
    title: str
    language: str | None = None
    codec: str | None = None
    detail: str | None = None


def _clean(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def make_track_info(
    kind: TrackKind,
    index: int,
    *,
    title: object | None = None,
    language: object | None = None,
    codec: object | None = None,
    detail: object | None = None,
) -> TrackInfo:
    """Build a stable UI model from Qt media-track metadata."""
    clean_title = _clean(title)
    clean_language = _clean(language)
    clean_codec = _clean(codec)
    clean_detail = _clean(detail)

    if not clean_title:
        clean_title = clean_language or f"{kind.value.title()} {index + 1}"

    return TrackInfo(
        kind=kind,
        index=index,
        title=clean_title,
        language=clean_language,
        codec=clean_codec,
        detail=clean_detail,
    )


def format_track_label(track: TrackInfo) -> str:
    """Return a concise, human-readable track menu label."""
    parts = [track.title]
    if track.language and track.language.lower() != track.title.lower():
        parts.append(track.language)
    if track.codec and track.codec.lower() not in {p.lower() for p in parts}:
        parts.append(track.codec)
    if track.detail and track.detail.lower() not in {p.lower() for p in parts}:
        parts.append(track.detail)
    return " · ".join(parts)
