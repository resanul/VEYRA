import json
import zipfile
from pathlib import Path

import pytest

from veyra.extensions.cs3 import CS3Inspector, CS3RuntimeAdapter, CS3RuntimeUnavailable


def make_cs3(path: Path, *, dex: bool = True) -> None:
    manifest = {
        "name": "Demo Provider",
        "internalName": "demo",
        "version": 7,
        "pluginClassName": "com.example.DemoPlugin",
        "requiresResources": False,
    }
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        if dex:
            package.writestr("classes.dex", b"dex\\n035\\x00")


def test_inspect_cs3_manifest_and_dex(tmp_path: Path) -> None:
    path = tmp_path / "demo.cs3"
    make_cs3(path)
    result = CS3Inspector.inspect(path)
    assert result.manifest.name == "Demo Provider"
    assert result.manifest.internal_name == "demo"
    assert result.manifest.version == 7
    assert result.has_dex is True


def test_runtime_rejects_android_dex_until_compatibility_runtime_exists(tmp_path: Path) -> None:
    path = tmp_path / "demo.cs3"
    make_cs3(path)
    with pytest.raises(CS3RuntimeUnavailable):
        CS3RuntimeAdapter().load(path)


def test_non_cs3_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "provider.zip"
    path.write_bytes(b"not a cs3")
    with pytest.raises(ValueError):
        CS3Inspector.inspect(path)
