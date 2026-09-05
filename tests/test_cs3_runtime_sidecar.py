from __future__ import annotations

import io
import json
import zipfile

from veyra.extensions.cs3_runtime.sidecar import RuntimeServer


def make_cs3(tmp_path):
    path = tmp_path / "demo.cs3"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"name": "Demo", "internalName": "demo", "version": 1}))
        archive.writestr("classes.dex", b"dex")
    return path


def test_health_and_protocol_errors(tmp_path):
    package = make_cs3(tmp_path)
    server = RuntimeServer()
    health = server.dispatch({"protocol": 1, "method": "health", "package": str(package), "payload": {}})
    assert health["ok"] is True
    assert health["dex_execution"] is False
    bad = server.dispatch({"protocol": 99, "method": "health", "package": str(package)})
    assert bad["code"] == "protocol_error"


def test_unsupported_execution_is_explicit(tmp_path):
    package = make_cs3(tmp_path)
    response = RuntimeServer().dispatch({"protocol": 1, "method": "search", "package": str(package), "payload": {"query": "demo"}})
    assert response["code"] == "runtime_unavailable"


def test_handler_dispatch_and_json_lines(tmp_path):
    package = make_cs3(tmp_path)

    def search(path, payload):
        return {"items": [{"id": "1", "title": payload["query"], "url": "https://example.test/1"}]}

    server = RuntimeServer({"search": search})
    response = server.dispatch({"protocol": 1, "method": "search", "package": str(package), "payload": {"query": "Demo"}})
    assert response["protocol"] == 1
    assert response["items"][0]["title"] == "Demo"

    inp = io.StringIO(json.dumps({"protocol": 1, "method": "search", "package": str(package), "payload": {"query": "CLI"}}) + "\n")
    out = io.StringIO()
    assert server.serve(inp, out) == 0
    assert json.loads(out.getvalue())["items"][0]["title"] == "CLI"
