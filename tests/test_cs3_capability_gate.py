from __future__ import annotations

from veyra.extensions.cs3_runtime.executor import ExecutorCapabilities


def test_metadata_sidecar_is_not_real_dex_runtime():
    capabilities = ExecutorCapabilities.from_response({
        "protocol": 2,
        "runtime": "veyra-cs3-sidecar-v1",
        "dex_execution": False,
        "android_api_bridge": False,
        "cloudstream_api_bridge": False,
    })
    assert not capabilities.dex_execution
    assert not capabilities.android_api_bridge
    assert not capabilities.cloudstream_api_bridge


def test_real_runtime_requires_all_execution_capabilities():
    capabilities = ExecutorCapabilities.from_response({
        "protocol": 2,
        "runtime": "test-real-runtime",
        "dex_execution": True,
        "android_api_bridge": True,
        "cloudstream_api_bridge": True,
    })
    assert all((capabilities.dex_execution, capabilities.android_api_bridge, capabilities.cloudstream_api_bridge))
