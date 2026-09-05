from __future__ import annotations

import json
import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


DEFAULT_PLUGIN_URL = (
    "https://raw.githubusercontent.com/doGior/doGiorsHadEnough/builds/YouTube.cs3"
)
ADB = os.environ.get("VEYRA_ADB", "adb")
PACKAGE = "com.veyra.cs3runtime"
ACTIVITY = f"{PACKAGE}/.MainActivity"
PORT = int(os.environ.get("VEYRA_CS3_E2E_PORT", "18787"))


def run_adb(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([ADB, *args], text=True, capture_output=True, check=False)
    if check and result.returncode != 0:
        raise AssertionError(result.stderr.strip() or f"adb failed: {' '.join(args)}")
    return result


def rpc(method: str, payload: dict[str, object]) -> dict[str, object]:
    request = {"protocol": 1, "method": method, "payload": payload}
    deadline = time.time() + 30
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=5) as sock:
                sock.sendall((json.dumps(request) + "\n").encode())
                line = sock.makefile("rb").readline()
            response = json.loads(line.decode())
            if response.get("error"):
                raise AssertionError(str(response["error"]))
            return response
        except (OSError, json.JSONDecodeError) as exc:
            last_error = exc
            time.sleep(1)
    raise AssertionError(f"Android CS3 runtime did not respond: {last_error}")


def main() -> None:
    apk = Path(os.environ["VEYRA_CS3_APK"]).resolve()
    plugin_url = os.environ.get("VEYRA_CS3_E2E_PLUGIN_URL", DEFAULT_PLUGIN_URL)
    plugin = Path("/tmp/veyra-e2e-plugin.cs3")

    run_adb("wait-for-device")
    run_adb("install", "-r", str(apk))
    urllib.request.urlretrieve(plugin_url, plugin)
    if plugin.stat().st_size < 1024:
        raise AssertionError("Downloaded CS3 package is unexpectedly small")

    remote = "/data/local/tmp/veyra-e2e-plugin.cs3"
    run_adb("push", str(plugin), remote)
    run_adb("forward", f"tcp:{PORT}", f"tcp:{PORT}")
    run_adb(
        "shell",
        "am",
        "start",
        "-n",
        ACTIVITY,
        "--es",
        "package_path",
        remote,
        "--ei",
        "port",
        str(PORT),
    )

    health = rpc("health", {})
    assert health.get("dex_execution") is True, health
    assert health.get("android_api_bridge") is True, health
    assert health.get("cloudstream_api_bridge") is True, health

    providers = rpc("providers", {})
    provider_list = providers.get("providers")
    assert isinstance(provider_list, list) and provider_list, providers

    results = rpc("search", {"query": "OpenAI", "page": 1})
    items = results.get("items")
    assert isinstance(items, list) and items, results

    first = items[0]
    assert isinstance(first, dict)
    url = str(first.get("url") or first.get("data") or "")
    assert url, first

    loaded = rpc("load", {"url": url})
    load = loaded.get("load")
    assert isinstance(load, dict), loaded

    print(json.dumps({
        "plugin_url": plugin_url,
        "provider": provider_list[0],
        "search_results": len(items),
        "loaded": load,
    }, indent=2))


if __name__ == "__main__":
    main()
