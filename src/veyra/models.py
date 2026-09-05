from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from enum import Enum


class MediaType(str, Enum):
    UNKNOWN = "unknown"
    VIDEO = "video"
    AUDIO = "audio"
    STREAM = "stream"


VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".ts", ".m2ts", ".flv", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".flac", ".aac", ".wav", ".ogg", ".opus", ".m4a", ".wma"}
STREAM_SUFFIXES = {".m3u8", ".mpd"}


@dataclass(frozen=True)
class MediaItem:
    id: str
    title: str
    source: str
    media_type: MediaType

    @staticmethod
    def from_source(source: str) -> "MediaItem":
        path = Path(source)
        suffix = path.suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            media_type = MediaType.VIDEO
        elif suffix in AUDIO_EXTENSIONS:
            media_type = MediaType.AUDIO
        elif suffix in STREAM_SUFFIXES or source.lower().startswith(("http://", "https://")):
            media_type = MediaType.STREAM
        else:
            media_type = MediaType.UNKNOWN
        return MediaItem(id=source, title=path.name or source, source=source, media_type=media_type)
