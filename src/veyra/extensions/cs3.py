from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class CS3Manifest:
    name: str
    internal_name: str
    version: int
    plugin_class_name: str | None
    requires_resources: bool = False


@dataclass(frozen=True, slots=True)
class CS3Inspection:
    path: Path
    manifest: CS3Manifest
    has_dex: bool
    has_resources: bool


class CS3Inspector:
    """Inspect a CloudStream .cs3 package without executing its code."""

    @staticmethod
    def inspect(path: Path) -> CS3Inspection:
        if path.suffix.lower() != ".cs3":
            raise ValueError("Not a CloudStream .cs3 package")
        if not path.is_file() or not zipfile.is_zipfile(path):
            raise ValueError("Invalid .cs3 package")

        with zipfile.ZipFile(path) as package:
            names = {name.replace("\\", "/").lstrip("/") for name in package.namelist()}
            manifests = [name for name in names if name.rsplit("/", 1)[-1] == "manifest.json"]
            if len(manifests) != 1:
                raise ValueError("CS3 package must contain exactly one manifest.json")
            try:
                raw = json.loads(package.read(manifests[0]).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid CS3 manifest.json") from exc
            if not isinstance(raw, dict):
                raise ValueError("Invalid CS3 manifest.json")
            required = ("name", "internalName", "version")
            if not all(key in raw for key in required):
                raise ValueError("CS3 manifest is missing required fields")

            manifest = CS3Manifest(
                name=str(raw["name"]),
                internal_name=str(raw["internalName"]),
                version=int(raw["version"]),
                plugin_class_name=(str(raw["pluginClassName"]) if raw.get("pluginClassName") else None),
                requires_resources=bool(raw.get("requiresResources", False)),
            )
            has_dex = any(name.endswith((".dex", ".jar")) for name in names)
            has_resources = any(name.startswith("res/") or "/res/" in name for name in names)
            return CS3Inspection(path, manifest, has_dex, has_resources)


class CS3RuntimeUnavailable(RuntimeError):
    """Raised when an Android/DEX CS3 package has no compatible runtime."""


class CS3RuntimeAdapter:
    """Runtime boundary for future CS3 compatibility.

    VEYRA deliberately does not execute downloaded DEX/Kotlin code in the
    Python process.  The adapter gives the UI a stable capability boundary
    while a dedicated compatibility runtime is developed.
    """

    def __init__(self, inspector: CS3Inspector | None = None) -> None:
        self.inspector = inspector or CS3Inspector()

    def load(self, path: Path) -> CS3Inspection:
        inspection = self.inspector.inspect(path)
        if inspection.has_dex:
            raise CS3RuntimeUnavailable(
                "This CS3 package contains Android DEX/JVM plugin code; "
                "VEYRA's compatible CS3 runtime is not installed yet."
            )
        return inspection
