from __future__ import annotations

import threading
import time


class BandwidthLimiter:
    """Thread-safe aggregate byte-rate limiter for concurrent download workers."""

    def __init__(self, limit_bytes_per_second: float | None = None) -> None:
        self._lock = threading.Lock()
        self._limit = self._validate(limit_bytes_per_second)
        self._next_available = time.monotonic()

    @staticmethod
    def _validate(value: float | None) -> float | None:
        if value is None:
            return None
        value = float(value)
        if value <= 0:
            raise ValueError("bandwidth limit must be greater than zero")
        return value

    @property
    def limit_bytes_per_second(self) -> float | None:
        with self._lock:
            return self._limit

    def set_limit(self, value: float | None) -> None:
        with self._lock:
            self._limit = self._validate(value)
            self._next_available = time.monotonic()

    def wait(self, amount: int, *, stop_event: threading.Event | None = None, pause_event: threading.Event | None = None) -> bool:
        """Reserve time for ``amount`` bytes and remain responsive to pause/cancel."""
        if amount <= 0:
            return True
        with self._lock:
            limit = self._limit
            if limit is None:
                return True
            now = time.monotonic()
            start = max(now, self._next_available)
            self._next_available = start + (amount / limit)
            remaining = start - now

        while remaining > 0:
            if stop_event is not None and stop_event.is_set():
                return False
            if pause_event is not None and pause_event.is_set():
                return False
            delay = min(0.05, remaining)
            time.sleep(delay)
            remaining -= delay
        return True


__all__ = ["BandwidthLimiter"]
