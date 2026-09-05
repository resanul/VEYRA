from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .repository import RemoteExtension


class ExtensionInstaller:
    """Download, verify and install native VEYRA extension packages."""

    def __init__(self, root: Path | None = None, timeout: float = 30.0) -> None:
        self.root = root or (Path.home() / "AppData" / "Local" / "VEYRA" / "extensions")
        self.timeout = timeout
        self.state_path = self.root.parent / "installed_extensions.json"

    def target_path(self, extension: RemoteExtension) -> Path:
        """Return the package payload path used by the installer contract.

        The extension is installed as a directory named after its id, while
        ``extension.bin`` remains the stable target path exposed to callers
        and tests.  This keeps the public path contract compatible with the
        original installer API without forcing the provider package itself to
        be a single binary file.
        """
        return self.root / extension.id / "extension.bin"

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()

    @staticmethod
    def _hash_matches(actual: str, expected: str | None) -> bool:
        if not expected:
            return True
        expected = expected.lower().strip().removeprefix("sha256-").removeprefix("sha256:")
        return actual.lower() == expected

    def install(self, extension: RemoteExtension) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        destination = self.target_path(extension)
        install_dir = destination.parent
        with tempfile.TemporaryDirectory(prefix="veyra-ext-") as temp:
            archive = Path(temp) / "extension.zip"
            request = urllib.request.Request(extension.url, headers={"User-Agent": "VEYRA/0.3"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
            if not self._hash_matches(self._sha256(archive), extension.sha256):
                raise ValueError(f"SHA-256 mismatch for {extension.name}")
            if not zipfile.is_zipfile(archive):
                raise ValueError("Unsupported extension package: VEYRA extensions must be ZIP packages")
            staging = Path(temp) / "package"
            staging.mkdir()
            with zipfile.ZipFile(archive) as package:
                root = staging.resolve()
                for member in package.infolist():
                    target = (staging / member.filename).resolve()
                    if root != target and root not in target.parents:
                        raise ValueError("Unsafe extension archive path")
                package.extractall(staging)
            manifests = list(staging.rglob("manifest.json"))
            if len(manifests) != 1:
                raise ValueError("Extension package must contain exactly one manifest.json")
            manifest_path = manifests[0]
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict) or not {"id", "name", "version"}.issubset(raw):
                raise ValueError("Invalid extension manifest")
            if str(raw["id"]) != extension.id:
                raise ValueError("Extension id does not match repository metadata")
            entry = manifest_path.parent / str(raw.get("entry_point", "provider.py"))
            if not entry.is_file():
                raise ValueError("Extension entry point provider.py is missing")
            if install_dir.exists():
                shutil.rmtree(install_dir)
            shutil.copytree(manifest_path.parent, install_dir)
            self._set_state(extension.id, str(raw["name"]), str(raw["version"]), True)
            return install_dir

    def _set_state(self, extension_id: str, name: str, version: str, enabled: bool) -> None:
        state = self._read_state()
        state[extension_id] = {"id": extension_id, "name": name, "version": version, "enabled": enabled}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")

    def _read_state(self) -> dict[str, dict]:
        try:
            rows = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}

    def is_installed(self, extension: RemoteExtension) -> bool:
        return (self.target_path(extension).parent / "manifest.json").is_file()

    def set_enabled(self, extension_id: str, enabled: bool) -> None:
        state = self._read_state()
        if extension_id not in state:
            raise KeyError(extension_id)
        state[extension_id]["enabled"] = enabled
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")

    def enabled(self) -> list[str]:
        return [key for key, value in self._read_state().items() if value.get("enabled", True)]

    def uninstall(self, extension_id: str) -> None:
        shutil.rmtree(self.root / extension_id, ignore_errors=True)
        state = self._read_state()
        state.pop(extension_id, None)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")
