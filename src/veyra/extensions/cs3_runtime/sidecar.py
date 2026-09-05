from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from ..cs3 import CS3Inspector

PROTOCOL_VERSION = 1
METHODS = ("health", "providers", "home", "search", "load", "loadLinks", "streams")


class RuntimeServer:
    """JSON-lines CS3 compatibility sidecar.

    This process is deliberately a clean-room protocol boundary. It validates
    packages and exposes a stable CloudStream-shaped transport, but it does not
    execute Android DEX bytecode. A future native/JVM adapter can be attached
    behind the same dispatcher without changing VEYRA's provider API.
    """

    def __init__(self, handlers: dict[str, Callable[[Path, dict[str, Any]], dict[str, Any]]] | None = None) -> None:
        self.handlers = handlers or {}

    def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        if request.get("protocol") != PROTOCOL_VERSION:
            return self._error("unsupported protocol version")
        method = request.get("method")
        if method not in METHODS:
            return self._error(f"unsupported method: {method}")
        package_value = request.get("package")
        if not isinstance(package_value, str) or not package_value:
            return self._error("package is required")
        package = Path(package_value).expanduser()
        try:
            inspection = CS3Inspector.inspect(package)
        except (OSError, ValueError, TypeError) as exc:
            return self._error(f"invalid CS3 package: {exc}")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        if method == "health":
            return {"protocol": PROTOCOL_VERSION, "ok": True, "runtime": "veyra-cs3-sidecar-v1", "dex_execution": False}
        handler = self.handlers.get(method)
        if handler is None:
            return self._error(f"method '{method}' requires a compatible CS3 execution adapter", code="runtime_unavailable")
        try:
            response = handler(inspection.path, payload)
        except Exception as exc:  # boundary: never crash the host process
            return self._error(str(exc), code="handler_error")
        if not isinstance(response, dict):
            return self._error("handler returned a non-object response", code="handler_error")
        response.setdefault("protocol", PROTOCOL_VERSION)
        return response

    @staticmethod
    def _error(message: str, code: str = "protocol_error") -> dict[str, Any]:
        return {"protocol": PROTOCOL_VERSION, "error": message, "code": code}

    def serve(self, stdin=None, stdout=None) -> int:
        stdin = stdin or sys.stdin
        stdout = stdout or sys.stdout
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
                if not isinstance(request, dict):
                    raise ValueError("request must be a JSON object")
                response = self.dispatch(request)
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                response = self._error(str(exc))
            stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            stdout.flush()
        return 0


def main() -> int:
    return RuntimeServer().serve()


if __name__ == "__main__":
    raise SystemExit(main())
