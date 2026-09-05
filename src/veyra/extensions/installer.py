from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from .cs3 import CS3Inspector
from .repository import RemoteExtension


class ExtensionInstaller:
    """Download, verify and install VEYRA and CloudStream package types."""

    def __init__(self, root: Path | None = None, timeout: float = 30.0) -> None:
        self.root = root or (Path.home() / "AppData" / "Local" / "VEYRA" / "extensions")
        self.timeout = timeout
        self.state_path = self.root.parent / "installed_extensions.json"

    def target_path(self, extension: RemoteExtension) -> Path:
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

    def _download(self, extension: RemoteExtension, suffix: str) -> Path:
        temp = Path(tempfile.mkdtemp(prefix="veyra-ext-"))
        archive = temp / f"package{suffix}"
        request = urllib.request.Request(extension.url, headers={"User-Agent": "VEYRA/0.4"})
        with urllib.request.urlopen(request, timeout=self.timeout) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
        if not self._hash_matches(self._sha256(archive), extension.sha256):
            shutil.rmtree(temp, ignore_errors=True)
            raise ValueError(f"SHA-256 mismatch for {extension.name}")
        return archive

    def install(self, extension: RemoteExtension) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        package_type = extension.package_type.lower()
        install_dir = self.root / extension.id
        if package_type == "cs3" or extension.url.lower().split("?", 1)[0].endswith(".cs3"):
            archive = self._download(extension, ".cs3")
            try:
                CS3Inspector.inspect(archive)
                if install_dir.exists():
                    shutil.rmtree(install_dir)
                install_dir.mkdir(parents=True)
                shutil.copy2(archive, install_dir / f"{extension.id}.cs3")
                metadata = {
                    "id": extension.id,
                    "name": extension.name,
                    "version": extension.version,
                    "package_type": "cs3",
                    "enabled": True,
                }
                self._write_metadata(install_dir, metadata)
                self._set_state(extension.id, extension.name, extension.version, True, "cs3")
                return install_dir
            finally:
                shutil.rmtree(archive.parent, ignore_errors=True)

        archive = self._download(extension, ".zip")
        try:
            if not zipfile.is_zipfile(archive):
                raise ValueError("Unsupported extension package: VEYRA extensions must be ZIP packages")
            staging = Path(tempfile.mkdtemp(prefix="veyra-stage-"))
            try:
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
                self._set_state(extension.id, str(raw["name"]), str(raw["version"]), True, "veyra")
                return install_dir
            finally:
                shutil.rmtree(staging, ignore_errors=True)
        finally:
            shutil.rmtree(archive.parent, ignore_errors=True)

    def _write_metadata(self, install_dir: Path, metadata: dict) -> None:
        (install_dir / "veyra-package.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    def _set_state(self, extension_id: str, name: str, version: str, enabled: bool, package_type: str) -> None:
        state = self._read_state()
        state[extension_id] = {"id": extension_id, "name": name, "version": version, "enabled": enabled, "package_type": package_type}
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")

    def _read_state(self) -> dict[str, dict]:
        try:
            rows = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}

    def is_installed(self, extension: RemoteExtension) -> bool:
        install_dir = self.target_path(extension).parent
        if extension.package_type.lower() == "cs3":
            return any(install_dir.glob("*.cs3"))
        return (install_dir / "manifest.json").is_file()

    def set_enabled(self, extension_id: str, enabled: bool) -> None:
        state = self._read_state()
        if extension_id not in state:
            raise KeyError(extension_id)
        state[extension_id]["enabled"] = enabled
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")

    def enabled(self) -> list[str]:
        return [key for key, value in self._read_state().items() if value.get("enabled", True)]

    def package_type(self, extension_id: str) -> str:
        return str(self._read_state().get(extension_id, {}).get("package_type", "veyra"))

    def uninstall(self, extension_id: str) -> None:
        shutil.rmtree(self.root / extension_id, ignore_errors=True)
        state = self._read_state()
        state.pop(extension_id, None)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(list(state.values()), indent=2), encoding="utf-8")
