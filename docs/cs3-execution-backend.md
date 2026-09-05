# CS3 Execution Backend

## Goal

Step 5.2 adds a real execution-backend contract for Android DEX based CloudStream extensions while keeping execution outside the VEYRA process.

A `.cs3` package is not a Python plugin. It contains JVM/DEX bytecode and normally depends on Android and CloudStream runtime APIs. VEYRA therefore does not translate arbitrary DEX into Python. Instead it launches a dedicated compatibility backend and communicates with it over JSON-lines RPC.

## Backend contract

The backend executable receives one JSON request on stdin and returns one JSON response on stdout:

```json
{"protocol":2,"method":"providers|home|search|load|loadLinks|streams","package":"C:/.../provider.cs3","payload":{}}
```

The backend must:

1. execute the supplied CS3 package in an isolated process;
2. expose the CloudStream MainAPI/Extractor API boundary;
3. return JSON-shaped provider/search/load/extractor results;
4. never write protocol logs to stdout;
5. return structured errors for unsupported APIs or failed plugins;
6. enforce a process timeout from the VEYRA side.

## Capability levels

- `metadata`: inspect a package only.
- `adapter`: run a purpose-built compatibility adapter.
- `dex`: execute DEX bytecode in a compatible Android/JVM runtime.

VEYRA must report the actual capability returned by the backend. An adapter contract is not advertised as arbitrary DEX execution.

## Why a separate backend

CloudStream plugins are Android/JVM artifacts and can execute third-party code. Keeping them in a separate process limits crashes, classpath conflicts and untrusted plugin behavior from the main media-player process.

The backend is intentionally an explicit executable boundary so a supported Android/DEX runtime can be bundled or installed independently without changing the player/provider UI.
