import json
from pathlib import Path

from veyra.extensions.host import load_enabled_providers


def test_cs3_extensions_are_not_loaded_as_native_python(tmp_path: Path) -> None:
    state = tmp_path / "installed_extensions.json"
    root = tmp_path / "extensions"
    root.mkdir()
    (root / "demo").mkdir()
    (root / "demo" / "manifest.json").write_text(json.dumps({
        "id": "demo", "name": "Demo", "version": "1", "package_type": "cs3"
    }), encoding="utf-8")
    state.write_text(json.dumps([{
        "id": "demo", "name": "Demo", "version": "1", "enabled": True, "package_type": "cs3"
    }]), encoding="utf-8")
    registry = load_enabled_providers(root)
    assert registry.all() == []
