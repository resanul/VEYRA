from __future__ import annotations

import json
import os
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .cs3_api import CloudStreamApiBridge, CS3ProviderInfo, search_result_from_cloudstream, stream_source_from_cloudstream
from veyra.providers.models import SearchResult, StreamSource


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
    """Raised when no compatible CS3 sidecar runtime is available."""


class CS3RuntimeError(RuntimeError):
    """Raised when the CS3 sidecar returns a runtime/protocol error."""


class CS3Sidecar:
    """JSON-lines process boundary for the clean-room CS3 compatibility runtime.

    The sidecar is deliberately separate from the Python GUI. Its executable
    receives one JSON request on stdin and returns one JSON response on stdout.
    Protocol version 1 maps CloudStream MainAPI/ExtractorApi operations to the
    VEYRA catalog contract without loading DEX inside the Python process.
    """

    PROTOCOL_VERSION = 1

    def __init__(self, executable: Path | None = None, timeout: float = 45.0) -> None:
        configured = executable or os.environ.get("VEYRA_CS3_RUNTIME")
        self.executable = Path(configured) if configured else None
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.executable and self.executable.is_file())

    def request(self, method: str, package: Path, payload: dict | None = None) -> dict:
        if not self.available:
            raise CS3RuntimeUnavailable(
                "VEYRA_CS3_RUNTIME is not configured; install the VEYRA CS3 sidecar runtime first."
            )
        request = {
            "protocol": self.PROTOCOL_VERSION,
            "method": method,
            "package": str(package.resolve()),
            "payload": payload or {},
        }
        completed = subprocess.run(
            [str(self.executable)],
            input=json.dumps(request) + "\n",
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise CS3RuntimeError(completed.stderr.strip() or "CS3 sidecar failed")
        try:
            response = json.loads(completed.stdout.strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            raise CS3RuntimeError("CS3 sidecar returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise CS3RuntimeError("CS3 sidecar response must be an object")
        if response.get("error"):
            raise CS3RuntimeError(str(response["error"]))
        return response


class CS3Provider:
    """Adapter exposing a sidecar-backed CS3 plugin as a VEYRA Provider."""

    def __init__(self, package: Path, runtime: CS3Sidecar | None = None) -> None:
        inspection = CS3Inspector.inspect(package)
        self.package = inspection.path
        self.id = inspection.manifest.internal_name
        self.name = inspection.manifest.name
        self.runtime = runtime or CS3Sidecar()
        self.inspection = inspection
        self.info: CS3ProviderInfo | None = None

    def _response(self, method: str, payload: dict) -> dict:
        return self.runtime.request(method, self.package, payload)

    def home(self) -> list[SearchResult]:
        response = self._response("home", {})
        items = response.get("items", [])
        return [search_result_from_cloudstream(item) for item in items if isinstance(item, dict)]

    def search(self, query: str) -> list[SearchResult]:
        response = self._response("search", {"query": query})
        items = response.get("items", [])
        return [search_result_from_cloudstream(item) for item in items if isinstance(item, dict)]

    def streams(self, item: SearchResult) -> list[StreamSource]:
        response = self._response("streams", {"item": {
            "id": item.id, "title": item.title, "url": item.url,
            "kind": item.kind, "year": item.year, "poster": item.poster,
            "metadata": dict(item.metadata),
        }})
        streams = response.get("streams", [])
        return [stream_source_from_cloudstream(stream) for stream in streams if isinstance(stream, dict)]

    def registration(self) -> CS3ProviderInfo | None:
        response = self._response("providers", {})
        bridge = CloudStreamApiBridge()
        for provider in response.get("providers", []):
            if isinstance(provider, dict):
                info = bridge.register_main_api(provider)
                if info.id == self.id or self.info is None:
                    self.info = info
        return self.info


class CS3RuntimeAdapter:
    """High-level CS3 loader with a real sidecar runtime boundary."""

    def __init__(self, inspector: CS3Inspector | None = None, runtime: CS3Sidecar | None = None) -> None:
        self.inspector = inspector or CS3Inspector()
        self.runtime = runtime or CS3Sidecar()

    def load(self, path: Path) -> CS3Inspection | CS3Provider:
        inspection = self.inspector.inspect(path)
        if inspection.has_dex:
            if not self.runtime.available:
                raise CS3RuntimeUnavailable(
                    "This CS3 package contains Android DEX/JVM plugin code and no compatible sidecar is installed."
                )
            # The sidecar owns DEX/JVM execution; Python receives only the
            # translated MainAPI/ExtractorApi wire contract.
            return CS3Provider(inspection.path, self.runtime)
        return inspection
