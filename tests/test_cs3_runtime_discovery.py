from __future__ import annotations

from veyra.extensions.cs3_runtime import discovery


def test_env_runtime_is_first_candidate(monkeypatch, tmp_path):
    runtime = tmp_path / "veyra-cs3-runtime.exe"
    runtime.write_text("stub", encoding="utf-8")
    monkeypatch.setenv("VEYRA_CS3_RUNTIME", str(runtime))
    assert discovery.discover_runtime() == runtime


def test_missing_runtime_returns_none(monkeypatch):
    monkeypatch.setenv("VEYRA_CS3_RUNTIME", "")
    monkeypatch.setattr(discovery.shutil, "which", lambda _: None)
    assert discovery.discover_runtime() is None
