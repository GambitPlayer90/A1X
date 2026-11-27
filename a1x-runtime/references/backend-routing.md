# Capability-aware backend routing

Run `doctor` for machine inventory and `capability probe` for the current target. Mixed compilers, Vyper, via-IR, remappings, and backend limitations can make an installed tool unusable for one target.

| Blocker | Preferred backend |
|---|---|
| Deterministic replay and final evidence | Foundry |
| Independent economic model or semantic action generator | Wake 5 |
| Interactive coverage/corpus steering | Echidna 2.4 |
| Large multiworker mutation campaign | Medusa |
| Narrow arithmetic/path constraint | Halmos/Z3 or Echidna symbolic mode |
| Deployed-state/snapshot exploration | ItyFuzz, when compatible |

Never claim cross-engine independence merely because two tools agree: Wake and Foundry can share `revm`. Native corpora are supporting artifacts, not interchangeable state. Translate a useful result into a typed witness and replay it through Foundry.

Use the read-only UDS prestate service for immutable recon queries. For iterative exploit construction, use the lane's independent writable fork through `a1x-lane-fork exec -- ... @fork`. The wrapper starts a short-lived HTTP bridge in the same network namespace as the child command, so Forge, Cast, Wake, Echidna, or Medusa can use ordinary HTTP without receiving an upstream credential. The host supervisor proxies and caches pinned upstream reads, and the UDS relay allows local EVM mutation while rejecting fork reset, upstream retargeting, and node-metadata methods.

Every lane receives the sanitized host PATH, a campaign-scoped toolchain home, and `.a1x/capabilities.json`. This makes approved executables available without inheriting RPC/explorer keys or writable global tool configuration. Wake's stdio MCP is injected only when its target probe passed. Echidna's HTTP campaign MCP must be started only for a concrete campaign in the lane namespace; preserve its corpus and export useful sequences as typed evidence.

The `a1x-campaign` stdio MCP may be registered globally because every call names a campaign root and the server owns no campaign state. Its host-side `explorer_retrieve` operation produces an immutable artifact and Recon Pack without returning credentials. Do not register Wake globally from a home directory. Start Echidna 2.4 with `--server PORT` inside the lane namespace only while that campaign is active, then connect to its loopback `/mcp` endpoint. MCP is a frontend or campaign-control transport, never the authoritative runtime.
