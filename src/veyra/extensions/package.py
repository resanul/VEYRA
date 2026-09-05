from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .cs3 import CS3Inspection, CS3Inspector
from .repository import RemoteExtension


@dataclass(frozen=True, slots=True)
class PackageInspection:
    extension: RemoteExtension
    package_type: str
    cs3: CS3Inspection | None = None


def inspect_package(path: Path, extension: RemoteExtension) -> PackageInspection:
    """Inspect a downloaded package without executing extension code."""
    package_type = extension.package_type.lower()
    if package_type == "cs3" or path.suffix.lower() == ".cs3":
        inspection = CS3Inspector.inspect(path)
        return PackageInspection(extension, "cs3", inspection)
    if package_type in {"veyra", "zip"}:
        return PackageInspection(extension, "veyra")
    raise ValueError(f"Unsupported extension package type: {package_type}")
