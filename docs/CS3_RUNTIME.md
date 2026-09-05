# VEYRA CS3 Runtime

VEYRA accepts CloudStream `.cs3` packages as signed/hashed extension artifacts and executes them outside the Python UI process.

## Runtime boundary

```text
VEYRA Python
   |
   | JSON-lines protocol v1
   v
veyra-cs3-runtime
   |
   | isolated JSON-lines executor protocol v1
   v
DEX-capable execution backend
   |
   +-- plugin classes.dex
   +-- CloudStream-compatible API surface
   +-- network/resource sandbox
```

The Python sidecar never imports or evaluates DEX/JVM bytecode. The execution backend is a separate process so a provider crash cannot corrupt the VEYRA process.

## Configuring an executor

Set `VEYRA_CS3_EXECUTOR` to a trusted DEX-capable runner executable (or a standalone `.py` runner during development):

```powershell
$env:VEYRA_CS3_EXECUTOR = 'C:\VEYRA\runtime\veyra-cs3-executor.exe'
```

The runner receives one JSON object on stdin and must return one JSON object on stdout:

```json
{
  "protocol": 1,
  "method": "search",
  "package": "C:\\...\\provider.cs3",
  "payload": {"query": "demo", "page": 1}
}
```

The response uses the CloudStream lifecycle bridge shape. Supported methods are `providers`, `home`, `search`, `load`, `loadLinks`, and `streams`.

## Security requirements

- The package must pass `CS3Inspector` before it reaches the executor.
- Installed packages are hash-verified by the extension installer when repository metadata provides a hash.
- The executor is a separate process with a hard timeout.
- The executor must not inherit credentials or unrestricted application state from VEYRA.
- A production executor must enforce filesystem/network/resource policy appropriate for third-party extensions.

## Important compatibility note

A `.cs3` file contains Android/JVM DEX bytecode. Having a ZIP reader or JSON adapter is not execution. VEYRA therefore reports `dex_execution: true` only when a DEX-capable executor is actually installed. The repository's Python tests use a tiny isolated fake executor to validate the process boundary; that test does **not** claim that arbitrary Android DEX can run on Windows by itself.
