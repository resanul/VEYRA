# Real CS3 Runtime Roadmap

Step 5.2 is split into explicit gates:

1. executor process/RPC boundary;
2. capability negotiation;
3. Android API compatibility surface;
4. DEX execution engine;
5. CloudStream MainAPI/Extractor API bindings;
6. real public `.cs3` provider smoke test through search/load/loadLinks;
7. VEYRA player handoff.

Only gates 1-2 are complete in the current source tree. Gates 3-7 require an actual DEX-capable runtime and are not satisfied by the Python sidecar.
