# Trace diagnosis

Classify failure before changing the candidate:

| Class | Meaning | Next action |
| --- | --- | --- |
| Build/interface | Wrong compiler, import, ABI, selector, type, or harness | Repair mechanics; do not update hypothesis confidence |
| Identity/config | Wrong implementation, address, role, asset, router, pool, or block | Return to recon and correct the model |
| Reachability | Guard, actor, capital, time, or ordering prerequisite not established | Revise transition ledger or refute path |
| Semantic | The targeted state changed differently than predicted | Re-evaluate mechanism and obligation |
| Search | Mechanism appears valid but parameters/sequence remain unresolved | Route to solve or fuzz |
| Oracle | Path executes but property/impact measurement is invalid | Redesign the security oracle |
| Environment | RPC, archive data, fork, external dependency, or tool failure | Fix environment; do not treat as safety evidence |

## Read the trace causally

Identify the first divergence from the predicted transition ledger, not merely the final revert. Record caller, callee, selector, parameters, value, relevant storage/balance deltas, external returns, and revert data. Trace across proxies and callbacks.

Generic AMM or arithmetic reverts often indicate an earlier accounting or ordering mistake. Repeating nearby amounts without understanding that divergence is not progress.
