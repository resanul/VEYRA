from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .manifest import ExtensionManifest


class ExtensionManager:
    """Discovers trusted, declarative VEYRA extension packages.

    Extensions are metadata plus an explicitly declared entry point. Execution
    remains opt-in so the application can later add stronger sandboxing/signing.
    """

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path.home() / "AppData" / "Local" / "VEYRA" / "extensions")
        self.manifests: dict[str, ExtensionManifest] = {}

    def discover(self) -> list[ExtensionManifest]:
        self.manifests.clear()
        if not self.root.exists():
            return []
        for manifest_path in sorted(self.root.glob("*/manifest.json")):
            try:
                manifest = self._read_manifest(manifest_path)
            except (OSError, ValueError, KeyError, TypeError):
                continue
            self.manifests[manifest.id] = manifest
        return list(self.manifests.values())

    @staticmethod
    def verify_sha256(path: Path, expected: str) -> bool:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest().lower() == expected.lower()

    def _read_manifest(self, path: Path) -> ExtensionManifest:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("manifest must be an object")
        required = {"id", "name", "version"}
        if not required.issubset(raw):
            raise KeyError("missing required manifest fields")
        return ExtensionManifest(
            id=str(raw["id"]),
            name=str(raw["name"]),
            version=str(raw["version"]),
            description=str(raw.get("description", "")),
            author=str(raw.get("author", "")),
            homepage=raw.get("homepage"),
            repository=raw.get("repository"),
            capabilities=tuple(map(str, raw.get("capabilities", []))),
            permissions=tuple(map(str, raw.get("permissions", []))),
        )
