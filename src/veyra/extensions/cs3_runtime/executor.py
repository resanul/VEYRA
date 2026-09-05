from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutorCapabilities:
    """Explicit capabilities advertised by a CS3 execution backend."""

    protocol: int
    runtime: str
    dex_execution: bool = False
    android_api_bridge: bool = False
    cloudstream_api_bridge: bool = False

    @classmethod
    def from_response(cls, response: dict[str, Any]) -> "ExecutorCapabilities":
        if not isinstance(response, dict):
            raise TypeError("executor capability response must be an object")
        return cls(
            protocol=int(response.get("protocol", 0)),
            runtime=str(response.get("runtime", "unknown")),
            dex_execution=bool(response.get("dex_execution", False)),
            android_api_bridge=bool(response.get("android_api_bridge", False)),
            cloudstream_api_bridge=bool(response.get("cloudstream_api_bridge", False)),
        )

    @property
    def real_cs3_execution(self) -> bool:
        """True only when all runtime layers required by CS3 are present."""
        return all((self.dex_execution, self.android_api_bridge, self.cloudstream_api_bridge))


class CS3ExecutorUnavailable(RuntimeError):
    """Raised when no DEX-capable execution backend is configured."""


class CS3ExecutorError(RuntimeError):
    """Raised when the external DEX execution backend fails."""


class ExternalCS3Executor:
    """Bridge VEYRA's sidecar protocol to a real DEX-capable runtime."""

    def __init__(self, executable: Path | None = None, timeout: float = 45.0) -> None:
        self.executable = executable or self.discover()
        self.timeout = timeout

    @staticmethod
    def discover() -> Path | None:
        configured = os.environ.get("VEYRA_CS3_EXECUTOR")
        if configured:
            path = Path(configured).expanduser()
            return path if path.is_file() else None
        names = ("veyra-cs3-executor.exe", "veyra-cs3-executor") if os.name == "nt" else ("veyra-cs3-executor",)
        here = Path(__file__).resolve()
        candidates = [
            here.parent / names[0],
            here.parents[4] / "runtime" / names[0],
            Path(sys.prefix) / "Scripts" / names[0],
        ]
        if os.name != "nt":
            candidates.extend([
                here.parent / names[0],
                here.parents[4] / "runtime" / names[0],
                Path(sys.prefix) / "bin" / names[0],
            ])
        for candidate in dict.fromkeys(candidates):
            if candidate.is_file():
                return candidate
        return None

    @property
    def available(self) -> bool:
        return bool(self.executable and self.executable.is_file())

    def request(self, method: str, package: Path, payload: dict[str, Any]) -> dict[str, Any]:
        """Send one CS3 RPC request to the isolated execution backend."""
        return self.execute(method, package, payload)

    def execute(self, method: str, package: Path, payload: dict[str, Any]) -> dict[str, Any]:
        if not self.available:
            raise CS3ExecutorUnavailable(
                "No DEX execution backend is installed. Configure VEYRA_CS3_EXECUTOR "
                "with a trusted DEX-capable runner."
            )
        request = {
            "protocol": 1,
            "method": method,
            "package": str(package.resolve()),
            "payload": payload,
        }
        command = [str(self.executable)]
        if self.executable.suffix.lower() == ".py":
            command = [sys.executable, "-I", str(self.executable)]
        completed = subprocess.run(
            command,
            input=json.dumps(request, ensure_ascii=False) + "\n",
            text=True,
            capture_output=True,
            timeout=self.timeout,
            check=False,
        )
        if completed.returncode != 0:
            raise CS3ExecutorError(completed.stderr.strip() or "DEX execution backend failed")
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        if not lines:
            raise CS3ExecutorError("DEX execution backend returned no response")
        try:
            response = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise CS3ExecutorError("DEX execution backend returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise CS3ExecutorError("DEX execution backend response must be an object")
        if response.get("error"):
            raise CS3ExecutorError(str(response["error"]))
        return response
