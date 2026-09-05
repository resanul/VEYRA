from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ExtensionManifest:
    """Metadata for a VEYRA provider/extension package."""

    id: str
    name: str
    version: str
    description: str = ""
    author: str = ""
    homepage: str | None = None
    repository: str | None = None
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    permissions: tuple[str, ...] = field(default_factory=tuple)
