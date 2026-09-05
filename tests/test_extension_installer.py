from pathlib import Path
from urllib.request import urlopen
import hashlib
import io
import json
import zipfile

from veyra.extensions.installer import ExtensionInstaller
from veyra.extensions.repository import RemoteExtension


def test_install_verified_package(tmp_path: Path, monkeypatch) -> None:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as package:
        package.writestr("manifest.json", json.dumps({"id": "demo", "name": "Demo", "version": "1", "entry_point": "provider.py"}))
        package.writestr("provider.py", "class Provider: pass\n")
    payload = stream.getvalue()

    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *args): self.close()

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response(payload))
    ext = RemoteExtension("demo", "Demo", "1", "https://example.test/demo.zip", sha256=hashlib.sha256(payload).hexdigest())
    installer = ExtensionInstaller(tmp_path / "extensions")
    path = installer.install(ext)
    assert (path / "manifest.json").is_file()
    assert (path / "provider.py").is_file()
    assert installer.is_installed(ext)
    assert "demo" in installer.enabled()
