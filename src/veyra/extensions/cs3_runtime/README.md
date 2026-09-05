CS3 execution backend boundary.

The real Android/DEX runtime is intentionally external to VEYRA. The backend must advertise protocol 2 and explicit `dex_execution`, `android_api_bridge`, and `cloudstream_api_bridge` capabilities before VEYRA treats it as a real execution runtime.
