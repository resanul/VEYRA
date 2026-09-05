from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

from .manager import ExtensionManager
from .repository import RemoteExtension


class ExtensionInstaller:
    """Downloads and verifies declarative VEYRA extensions."""

    def __init__(self, root: Path | None = None, timeout: float = 30.0) -> None:
        self.root = root or (Path.home() / "AppData" / "Local" / "VEYRA" / "extensions")
        self.timeout = timeout

    def target_path(self, extension: RemoteExtension) -> Path:
        return self.root / extension.id / "extension.bin"

    def install(self, extension: RemoteExtension) -> Path:
        target = self.target_path(extension)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_dir = target.parent
        with tempfile.NamedTemporaryFile(dir=temp_dir, delete=False) as tmp:
            temporary = Path(tmp.name)
        try:
            request = Request(extension.url, headers={"User-Agent": "VEYRA/0.3"})
            with urlopen(request, timeout=self.timeout) as response:
                with temporary.open("wb") as output:
                    while True:
                        block = response.read(1024 * 1024)
                        if not block:
                            break
                        output.write(block)
            if extension.sha256:
                digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
                expected = extension.sha256.removeprefix("sha256-").lower()
                if digest.lower() != expected:
                    raise ValueError(
                        f"SHA-256 mismatch for {extension.name}: expected {expected}, got {digest}"
                    )
            temporary.replace(target)
            return target
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def uninstall(self, extension_id: str) -> None:
        path = self.root / extension_id
        if path.exists():
            for child in sorted(path.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
                elif child.is_dir():
                    child.rmdir()
            path.rmdir()

    def is_installed(self, extension: RemoteExtension) -> bool:
        return self.target_path(extension).is_file()
