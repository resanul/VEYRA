from __future__ import annotations

import json
import os
import stat
import zipfile
from pathlib import Path

import pytest

from veyra.extensions.cs3_runtime.executor import ExternalCS3Executor


def test_external_executor_round_trip(tmp_path: Path):
    package = tmp_path / "demo.cs3"
    with zipfile.ZipFile(package, "w") as z:
        z.writestr("manifest.json", json.dumps({"name": "Demo", "internalName": "demo", "version": 1}))

    backend = tmp_path / "backend.py"
    backend.write_text(
        "import json,sys\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line)\n"
        " print(json.dumps({'protocol':2,'runtime':'test-backend','dex_execution':True,'android_api_bridge':True,'cloudstream_api_bridge':True,'method':r['method']}), flush=True)\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        backend.chmod(backend.stat().st_mode | stat.S_IXUSR)
    executable = Path(os.environ.get("PYTHON", "python"))
    # The production client expects an executable. A tiny launcher is used on
    # POSIX; Windows CI uses the Python interpreter path via this test helper.
    launcher = tmp_path / ("backend.cmd" if os.name == "nt" else "backend")
    if os.name == "nt":
        launcher.write_text(f'@"{executable}" "{backend}"\n', encoding="utf-8")
    else:
        launcher.write_text(f'#!{executable}\nexec "{executable}" "{backend}"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    executor = ExternalCS3Executor(launcher, timeout=5)
    response = executor.request("search", package, {"query": "Demo"})
    assert response["protocol"] == 2
    assert response["method"] == "search"
    assert executor.capabilities(package).dex_execution is True
