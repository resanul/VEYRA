from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from veyra.providers.models import SearchResult, StreamSource
from veyra.providers.registry import ProviderRegistry


_RUNNER = r'''
import importlib.util, json, sys
path, method = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("veyra_extension_provider", path)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load provider")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
factory = getattr(module, "create_provider", None)
provider = factory() if callable(factory) else getattr(module, "Provider")()
request = json.loads(sys.stdin.read() or "{}")
argument = request.get("query") if method == "search" else request.get("item")
if method == "home":
    result = provider.home()
else:
    result = getattr(provider, method)(argument)
def encode(value):
    if hasattr(value, "__dataclass_fields__"):
        return {k: encode(getattr(value, k)) for k in value.__dataclass_fields__}
    if isinstance(value, (list, tuple)):
        return [encode(v) for v in value]
    if isinstance(value, dict):
        return {k: encode(v) for k, v in value.items()}
    return value
print(json.dumps(encode(list(result))))
'''


class IsolatedProvider:
    """Provider proxy executed in a separate Python process."""

    def __init__(self, extension_id: str, name: str, provider_file: Path, timeout: float = 45.0) -> None:
        self.id = extension_id
        self.name = name
        self.provider_file = provider_file
        self.timeout = timeout

    def _call(self, method: str, payload: object) -> list[dict]:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", _RUNNER, str(self.provider_file), method],
            input=json.dumps(payload), text=True, capture_output=True,
            timeout=self.timeout, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "extension provider failed")
        value = json.loads(completed.stdout)
        return value if isinstance(value, list) else []

    def home(self):
        return [SearchResult(**row) for row in self._call("home", {})]

    def search(self, query: str):
        return [SearchResult(**row) for row in self._call("search", {"query": query})]

    def streams(self, item: SearchResult):
        return [StreamSource(**row) for row in self._call("streams", {"item": asdict(item)})]


def load_enabled_providers(root: Path | None = None) -> ProviderRegistry:
    """Build a registry from installed and enabled native extensions."""
    root = root or (Path.home() / "AppData" / "Local" / "VEYRA" / "extensions")
    state_path = root.parent / "installed_extensions.json"
    try:
        rows = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        rows = []
    enabled = {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id") and row.get("enabled", True)}
    registry = ProviderRegistry()
    for extension_id, state in enabled.items():
        package = root / extension_id
        manifest_path = package / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            entry = package / str(manifest.get("entry_point", "provider.py"))
            if entry.is_file():
                registry.register(IsolatedProvider(extension_id, str(manifest.get("name", state.get("name", extension_id))), entry))
        except (OSError, ValueError, TypeError):
            continue
    return registry
