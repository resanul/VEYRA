from __future__ import annotations

from abc import ABC, abstractmethod

from .models import MediaItem


class PlaybackEngine(ABC):
    """Playback backend contract; production libmpv/FFmpeg comes next."""

    @abstractmethod
    def open(self, media: MediaItem) -> None: ...

    @abstractmethod
    def play(self) -> None: ...

    @abstractmethod
    def pause(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def seek(self, seconds: float) -> None: ...

    @abstractmethod
    def set_speed(self, speed: float) -> None: ...

    @abstractmethod
    def set_volume(self, volume: float) -> None: ...
