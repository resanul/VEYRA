from __future__ import annotations

from pathlib import Path

from veyra.extensions.cs3_runtime.executor import ExecutorCapabilities


def test_capabilities_require_explicit_backend_flags():
    capabilities = ExecutorCapabilities.from_response({
        "protocol": 2,
        "runtime": "real-test",
        "dex_execution": True,
        "android_api_bridge": True,
        "cloudstream_api_bridge": True,
    })
    assert capabilities.protocol == 2
    assert capabilities.dex_execution
    assert capabilities.android_api_bridge
    assert capabilities.cloudstream_api_bridge
    assert capabilities.runtime == "real-test"
