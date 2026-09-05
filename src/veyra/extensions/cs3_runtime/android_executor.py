from __future__ import annotations

import json
import os
import socket
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .executor import CS3ExecutorError, CS3ExecutorUnavailable, ExecutorCapabilities


class AndroidCS3Executor:
    """Execute a CS3 package through an isolated Android ART/Dalvik host.

    VEYRA stays on the Windows/Python side. The Android companion performs the
    actual DEX class loading and CloudStream API calls. Communication is JSONL
    over an adb port-forwarded loopback socket.
    """

    DEFAULT_PORT = 18787
    AGENT_PACKAGE = "com.veyra.cs3runtime"
    AGENT_ACTIVITY = f"{AGENT_PACKAGE}/.MainActivity"

    def __init__(self, adb: str | None = None, timeout: float = 45.0, port: int = DEFAULT_PORT) -> None:
        self.adb = adb or os.environ.get("VEYRA_ADB", "adb")
        self.timeout = timeout
        self.port = port
        self._forwarded = False

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(
                [self.adb, *args],
                text=True,
                capture_output=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise CS3ExecutorUnavailable(f"ADB is unavailable: {exc}") from exc
        if check and result.returncode != 0:
            raise CS3ExecutorError(result.stderr.strip() or f"adb command failed: {' '.join(args)}")
        return result

    def available(self) -> bool:
        result = self._run("get-state", check=False)
        return result.returncode == 0 and result.stdout.strip() == "device"

    def _start_agent(self, package: Path) -> None:
        remote = f"/data/local/tmp/veyra-cs3/{package.stem}.cs3"
        self._run("shell", "mkdir", "-p", "/data/local/tmp/veyra-cs3")
        self._run("push", str(package.resolve()), remote)
        self._run(
            "shell",
            "am",
            "start",
            "-n",
            self.AGENT_ACTIVITY,
            "--es",
            "package_path",
            remote,
            "--ei",
            "port",
            str(self.port),
        )
        self._run("forward", f"tcp:{self.port}", f"tcp:{self.port}")
        self._forwarded = True

    def _rpc(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._forwarded:
            raise CS3ExecutorUnavailable("Android CS3 agent is not connected")
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=self.timeout) as sock:
                sock.settimeout(self.timeout)
                sock.sendall((json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8"))
                data = b""
                while not data.endswith(b"\n"):
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    data += chunk
        except OSError as exc:
            raise CS3ExecutorError(f"Android CS3 agent connection failed: {exc}") from exc
        if not data:
            raise CS3ExecutorError("Android CS3 agent returned no response")
        try:
            response = json.loads(data.decode("utf-8").splitlines()[-1])
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CS3ExecutorError("Android CS3 agent returned invalid JSON") from exc
        if not isinstance(response, dict):
            raise CS3ExecutorError("Android CS3 agent response must be an object")
        if response.get("error"):
            raise CS3ExecutorError(str(response["error"]))
        return response

    def request(self, method: str, package: Path, payload: dict[str, Any]) -> dict[str, Any]:
        if not package.is_file():
            raise CS3ExecutorError(f"CS3 package not found: {package}")
        if not self.available():
            raise CS3ExecutorUnavailable("No Android device/emulator is available through adb")
        self._start_agent(package)
        return self._rpc({"protocol": 1, "method": method, "payload": payload})

    def capabilities(self, package: Path) -> ExecutorCapabilities:
        return ExecutorCapabilities.from_response(self.request("health", package, {}))

    def execute(self, method: str, package: Path, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request(method, package, payload)

    def close(self) -> None:
        if self._forwarded:
            self._run("forward", "--remove", f"tcp:{self.port}", check=False)
            self._forwarded = False
