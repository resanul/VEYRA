import json
from pathlib import Path

from veyra.extensions.cs3 import CS3Provider, CS3RuntimeAdapter
from veyra.extensions.host import load_enabled_providers


class FakeRuntime:
    available = True

    def load(self, path: Path):
        return CS3Provider(path, runtime=self)

    def request(self, method: str, package: Path, payload=None):
        if method == "home":
            return {"items": [{"id": "m1", "title": "Demo Movie", "url": "https://example.test/movie", "type": "movie", "year": 2026}]}
        return {"items": []}


def make_cs3(path: Path) -> None:
    import zipfile
    with zipfile.ZipFile(path, "w") as package:
        package.writestr("manifest.json", json.dumps({
            "name": "Demo Provider", "internalName": "demo", "version": 1,
        }))
        package.writestr("classes.dex", b"dex")


def test_cs3_extensions_are_not_loaded_as_native_python(tmp_path: Path) -> None:
    state = tmp_path / "installed_extensions.json"
    root = tmp_path / "extensions"
    root.mkdir()
    (root / "demo").mkdir()
    (root / "demo" / "demo.cs3").write_bytes(b"not-a-cs3")
    state.write_text(json.dumps([{
        "id": "demo", "name": "Demo", "version": "1", "enabled": True, "package_type": "cs3"
    }]), encoding="utf-8")
    registry = load_enabled_providers(root)
    assert registry.all() == ()


def test_cs3_provider_is_registered_through_runtime_boundary(tmp_path: Path) -> None:
    state = tmp_path / "installed_extensions.json"
    root = tmp_path / "extensions"
    package_dir = root / "demo"
    package_dir.mkdir(parents=True)
    make_cs3(package_dir / "demo.cs3")
    state.write_text(json.dumps([{
        "id": "demo", "name": "Demo", "version": "1", "enabled": True, "package_type": "cs3"
    }]), encoding="utf-8")
    registry = load_enabled_providers(root, FakeRuntime())
    provider = registry.get("demo")
    assert provider is not None
    assert provider.name == "Demo Provider"
    assert provider.home()[0].title == "Demo Movie"
