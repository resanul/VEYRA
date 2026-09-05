from __future__ import annotations

import json
import os
import subprocess
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .cs3_api import CloudStreamApiBridge, CS3ProviderInfo, search_result_from_cloudstream, stream_source_from_cloudstream
from .cs3_runtime.cloudstream_lifecycle import CloudStreamLifecycleAdapter
from .cs3_runtime.discovery import discover_runtime
from .cs3_runtime.executor import CS3ExecutorUnavailable, WindowsCS3Executor
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
    """Raised when no compatible CS3 sidecar/runtime is available."""


class CS3RuntimeError(RuntimeError):
    """Raised when the CS3 sidecar returns a runtime/protocol error."""


class CS3Sidecar:
    PROTOCOL_VERSION = 1

    def __init__(self, executable: Path | None = None, timeout: float = 45.0) -> None:
        self.executable = executable or discover_runtime()
        self.timeout = timeout

    @property
    def available(self) -> bool:
        return bool(self.executable and self.executable.is_file())

    def request(self, method: str, package: Path, payload: dict | None = None) -> dict:
        if not self.available:
            raise CS3RuntimeUnavailable("No VEYRA CS3 sidecar runtime was discovered.")
        request = {"protocol": self.PROTOCOL_VERSION, "method": method, "package": str(package.resolve()), "payload": payload or {}}
        command = [str(self.executable)]
        if self.executable.suffix.lower() == ".py":
            command = [os.fspath(__import__("sys").executable), "-I", str(self.executable)]
        completed = subprocess.run(command, input=json.dumps(request) + "\n", text=True, capture_output=True, timeout=self.timeout, check=False)
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
    def __init__(self, package: Path, runtime=None) -> None:
        inspection = CS3Inspector.inspect(package)
        self.package = inspection.path
        self.id = inspection.manifest.internal_name
        self.name = inspection.manifest.name
        self.runtime = runtime or _default_runtime()
        self.inspection = inspection
        self.info: CS3ProviderInfo | None = None

    def _response(self, method: str, payload: dict) -> dict:
        return self.runtime.request(method, self.package, payload)

    def lifecycle(self) -> CloudStreamLifecycleAdapter:
        """Return the CloudStream MainAPI/ExtractorApi lifecycle adapter."""
        return CloudStreamLifecycleAdapter(self._response)

    def home(self) -> list[SearchResult]:
        response = self.lifecycle().get_main_page()
        return list(response.home_pages[0].items) if response.home_pages else []

    def search(self, query: str) -> list[SearchResult]:
        return list(self.lifecycle().search(query).results)

    def streams(self, item: SearchResult) -> list[StreamSource]:
        return list(self.lifecycle().streams(item).streams)

    def load(self, url: str):
        return self.lifecycle().load(url)

    def load_links(self, url: str, *, referer: str | None = None, data: str | None = None):
        return self.lifecycle().load_links(url, referer=referer, data=data)

    def registration(self) -> CS3ProviderInfo | None:
        response = self.lifecycle().providers()
        for info in response.providers:
            if info.id == self.id or self.info is None:
                self.info = info
        return self.info


def _default_runtime():
    """Select the platform runtime without making Android part of Windows VEYRA."""
    if os.name == "nt":
        return WindowsCS3Executor()
    return CS3Sidecar()


class CS3RuntimeAdapter:
    def __init__(self, inspector: CS3Inspector | None = None, runtime=None) -> None:
        self.inspector = inspector or CS3Inspector()
        self.runtime = runtime or _default_runtime()

    def load(self, path: Path) -> CS3Inspection | CS3Provider:
        inspection = self.inspector.inspect(path)
        if inspection.has_dex:
            if not getattr(self.runtime, "available", False):
                if os.name == "nt":
                    raise CS3RuntimeUnavailable(
                        "Windows CS3 execution backend is not installed. "
                        "Set VEYRA_CS3_EXECUTOR to a trusted DEX-capable Windows worker."
                    )
                raise CS3RuntimeUnavailable(
                    "This CS3 package contains Android DEX/JVM plugin code and no compatible sidecar is installed."
                )
            return CS3Provider(inspection.path, self.runtime)
        return inspection
