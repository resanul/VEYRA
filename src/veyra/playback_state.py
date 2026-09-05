from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
from urllib.parse import parse_qs, urlparse

from PySide6.QtCore import QSettings


@dataclass(frozen=True, slots=True)
class PlaybackState:
    """Persistent player preferences and per-source track selections."""

    playback_rate: float = 1.0
    volume: float = 1.0
    muted: bool = False
    audio_track: int = -1
    video_track: int = -1
    subtitle_track: int = -1
    external_subtitle: str | None = None

    def normalized(self) -> "PlaybackState":
        rate = min(4.0, max(0.25, float(self.playback_rate)))
        volume = min(1.0, max(0.0, float(self.volume)))
        return replace(
            self,
            playback_rate=rate,
            volume=volume,
            muted=bool(self.muted),
            audio_track=int(self.audio_track),
            video_track=int(self.video_track),
            subtitle_track=int(self.subtitle_track),
            external_subtitle=self.external_subtitle or None,
        )


class PlaybackStateStore:
    """QSettings-backed global preferences plus source-specific track state."""

    def __init__(self, settings: QSettings | None = None) -> None:
        self.settings = settings or QSettings("VEYRA", "VEYRA")

    def load_preferences(self) -> PlaybackState:
        return PlaybackState(
            playback_rate=self._float("player/playback_rate", 1.0),
            volume=self._float("player/volume", 1.0),
            muted=self._bool("player/muted", False),
        ).normalized()

    def save_preferences(self, state: PlaybackState) -> None:
        state = state.normalized()
        self.settings.setValue("player/playback_rate", state.playback_rate)
        self.settings.setValue("player/volume", state.volume)
        self.settings.setValue("player/muted", state.muted)
        self.settings.sync()

    def load_source(self, source: str) -> PlaybackState:
        key = self._source_key(source)
        preferences = self.load_preferences()
        return PlaybackState(
            playback_rate=preferences.playback_rate,
            volume=preferences.volume,
            muted=preferences.muted,
            audio_track=self._int(f"tracks/{key}/audio", -1),
            video_track=self._int(f"tracks/{key}/video", -1),
            subtitle_track=self._int(f"tracks/{key}/subtitle", -1),
            external_subtitle=self._optional(f"tracks/{key}/external_subtitle"),
        ).normalized()

    def save_source(self, source: str, state: PlaybackState) -> None:
        state = state.normalized()
        key = self._source_key(source)
        self.settings.setValue(f"tracks/{key}/audio", state.audio_track)
        self.settings.setValue(f"tracks/{key}/video", state.video_track)
        self.settings.setValue(f"tracks/{key}/subtitle", state.subtitle_track)
        if state.external_subtitle:
            self.settings.setValue(f"tracks/{key}/external_subtitle", state.external_subtitle)
        else:
            self.settings.remove(f"tracks/{key}/external_subtitle")
        self.save_preferences(state)

    @staticmethod
    def _canonical_source(source: str) -> str:
        """Unwrap VEYRA's localhost media proxy so random proxy tokens do not break persistence."""
        try:
            parsed = urlparse(source)
            if parsed.hostname in {"127.0.0.1", "localhost"}:
                upstream = parse_qs(parsed.query).get("url", [None])[0]
                if upstream:
                    return upstream
        except ValueError:
            pass
        return source

    def _source_key(self, source: str) -> str:
        canonical = self._canonical_source(source)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]

    def _optional(self, key: str) -> str | None:
        value = self.settings.value(key, None)
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _float(self, key: str, default: float) -> float:
        try:
            return float(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _int(self, key: str, default: int) -> int:
        try:
            return int(self.settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _bool(self, key: str, default: bool) -> bool:
        value = self.settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}


__all__ = ["PlaybackState", "PlaybackStateStore"]
