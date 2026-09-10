from __future__ import annotations

import threading

import pytest

from veyra.bandwidth import BandwidthLimiter
from veyra.download_manager import DownloadManager


def test_unlimited_limiter_does_not_sleep(monkeypatch) -> None:
    limiter = BandwidthLimiter()
    slept: list[float] = []
    monkeypatch.setattr("veyra.bandwidth.time.sleep", slept.append)
    assert limiter.wait(1024)
    assert slept == []


def test_limiter_reserves_shared_rate(monkeypatch) -> None:
    slept: list[float] = []
    monkeypatch.setattr("veyra.bandwidth.time.monotonic", lambda: 0.0)
    monkeypatch.setattr("veyra.bandwidth.time.sleep", slept.append)
    limiter = BandwidthLimiter(100.0)
    assert limiter.wait(100)
    assert limiter.wait(100)
    assert sum(slept) == pytest.approx(1.0)
    assert all(delay <= 0.05 for delay in slept)


def test_limiter_stops_while_waiting(monkeypatch) -> None:
    monkeypatch.setattr("veyra.bandwidth.time.monotonic", lambda: 0.0)
    limiter = BandwidthLimiter(100.0)
    limiter.wait(100)
    stop = threading.Event()
    stop.set()
    assert limiter.wait(100, stop_event=stop) is False


def test_bandwidth_limit_can_be_changed_at_runtime(tmp_path) -> None:
    manager = DownloadManager(tmp_path / "downloads.db", tmp_path / "files", bandwidth_limit=64 * 1024)
    assert manager.bandwidth_limit == 64 * 1024
    manager.set_bandwidth_limit(128 * 1024)
    assert manager.bandwidth_limit == 128 * 1024
    manager.set_bandwidth_limit(None)
    assert manager.bandwidth_limit is None
    manager.shutdown()


def test_bandwidth_limit_rejects_non_positive_values() -> None:
    with pytest.raises(ValueError):
        BandwidthLimiter(0)
    with pytest.raises(ValueError):
        BandwidthLimiter(-1)
