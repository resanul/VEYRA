from __future__ import annotations

import os
import shutil
from pathlib import Path


def candidate_paths() -> tuple[Path, ...]:
    """Return deterministic locations for the optional Windows sidecar."""
    candidates: list[Path] = []
    configured = os.environ.get("VEYRA_CS3_RUNTIME")
    if configured:
        candidates.append(Path(configured).expanduser())

    exe_name = "veyra-cs3-runtime.exe" if os.name == "nt" else "veyra-cs3-runtime"
    here = Path(__file__).resolve()
    candidates.extend((
        here.parent / exe_name,
        here.parents[4] / "runtime" / exe_name,
        Path(sys_prefix()) / "Scripts" / exe_name,
    ))
    return tuple(dict.fromkeys(candidates))


def sys_prefix() -> str:
    # Kept separate to make discovery deterministic and easy to test.
    import sys
    return sys.prefix


def discover_runtime() -> Path | None:
    for path in candidate_paths():
        if path.is_file():
            return path
    name = "veyra-cs3-runtime.exe" if os.name == "nt" else "veyra-cs3-runtime"
    found = shutil.which(name)
    return Path(found) if found else None
