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

Never claim cross-engine independence merely because two tools agree: Wake and Foundry can share `revm`. Native corpora are supporting artifacts, not interchangeable state. Translate a useful result into a typed witness and replay it through Foundry. The runtime directly executes bounded Python exact-integer and isolated Python-Z3 jobs. Halmos, Medusa, Echidna, ItyFuzz, and Wake are admitted only after the per-target capability probe and a real sealed run; uninstalled or target-incompatible adapters are not represented by placeholders.

Use the read-only UDS prestate service for immutable recon queries. For iterative exploit construction, start a disclosed session-owned Anvil fork with `fork start` and pass its loopback endpoint only to sealed tool runs. The host supervisor proxies and caches pinned upstream reads without persisting the upstream credential. Record fork ID, block/hash, PID, endpoint, logs, snapshot, and cleanup. Serialize mutations or use separate disclosed forks.

Every sealed run receives a sanitized environment, run-local home, declared inputs, and the campaign capability record. This makes approved executables available without inheriting unrelated RPC/explorer keys or writable global tool configuration. Start Wake or Echidna control interfaces only for a concrete campaign, record the process, preserve the corpus, and export useful sequences as typed evidence.

The `a1x-campaign` stdio MCP may be registered globally because every call names a campaign root and the server owns no campaign state. Its host-side `explorer_retrieve` operation produces an immutable artifact and Recon Pack without returning credentials. Do not register target-scoped analyzers globally from a home directory. MCP is a frontend or campaign-control transport, never the authoritative runtime.
