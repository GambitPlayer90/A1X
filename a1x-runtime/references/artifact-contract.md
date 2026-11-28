# Runtime artifact and evidence contract

## Immutability and integrity

- `campaign.json` holds identity, budgets, and research counters.
- `events.jsonl` is an append-only, sequence-numbered hash chain in v4. Authoritative JSON writes are write-ahead materialization events; recovery reapplies a valid pending tail before campaign work resumes. Explicit v3 migration anchors the legacy bytes and never rewrites them.
- `evidence/objects/sha256/` holds immutable raw objects; `evidence/bundles/` holds typed claims and provenance.
- `recon/vNNNN/` holds immutable facts and explicit unknowns outside the source tree.
- `v5/ledger.json` is the compact authoritative investigation index. Its TSV and brief views carry the ledger digest and are rebuilt deterministically. Ledger writes use expected record revisions and atomic replacement; large immutable evidence remains external.
- Continuation, trace-fact, surface, composition, actor, oracle, harness, and solver-job records are authoritative hash-chained campaign materializations, not disposable worker notes.
- Plans, receipts, observations, and replay verifications have SHA-256 seals.
- A run plan and its observation are single-use. Change an input, command, property, prediction, or interpretation by creating a new run.
- Declared file and directory hashes exclude common build caches but include harness and configuration inputs.
- Atomic writes use a temporary file, `fsync`, and rename under a campaign lock where allocation or shared counters require serialization.

The runtime does not make the full campaign tamper-evident against a malicious local user. Seals catch accidental or out-of-band mutation; they are not signatures.

A continuation result is not inherited prose. The parent replay and preserved assertions are one evidence relationship; the distinct observed extension run and its clean replay are another. An operational failure may omit the extension pair but cannot count as semantic stagnation or prerequisite closure. A within-transaction waypoint is a trace coordinate inside the enclosing top-level transaction, never a resumable blockchain state.

Built-in subagent text is not runtime execution evidence. Grounded facts must reference immutable artifacts; behavioral claims must bind to sealed runs and replay. A `SYN` record changes the next test but cannot raise an evidence level by itself.

## Typed evidence references

Coverage, frontier, and impact records do not accept persuasive prose as evidence. They resolve typed references when the record is created and re-resolve them during completion assessment:

- `RunReceipt` (`run-receipt`): sealed mechanical receipt and optional sealed observation;
- `Replay` (`replay`): passing replay record linked to its run;
- `ForkSnapshot` (`fork-snapshot`): recorded snapshot in a known fork lifecycle;
- `SourceAnchor` (`source-anchor`): campaign/source-relative file or directory with content digest and optional line range;
- `TraceArtifact`, `StateDiff`, `SolverWitness`: run-relative artifact path and SHA-256 digest;
- `DeploymentObservation` (`deployment-observation`): sealed run observation about deployed state.

If the artifact disappears, its seal breaks, or its content no longer matches, the completion assessment reports an evidence blocker. A high-consequence demonstrated impact requires a downstream property-violating run whose sealed extension contract names the candidate and its original support run, hashes that parent plan and receipt, declares the causal prefix, and preserves chain/block identity. The downstream run must replay successfully. A distinct causal-control run links to that downstream run under the same hypothesis and exact impact property. High-consequence refutation uses the same extension lineage for executed negative evidence or an anchored deployment/solver proof; a lone persuasive source excerpt or unrelated passing test leaves the branch open.

## Process boundary

Commands run without a shell in a new process session. Timeout handling terminates the entire recorded process group, then escalates to `SIGKILL`. Standard output and error are bounded, redacted, hashed, and retained separately.

The default tool environment is minimal and uses a run-local home directory. `FOUNDRY_FFI=false` is injected. Explicit `--pass-env` and `--inherit-env` expand the boundary and must be justified in the plan.

Filesystem and network isolation still depend on the outer Codex sandbox, container, VM, or OS policy. A receipt states that A1X itself did not enforce network isolation. Do not interpret environment scrubbing as a complete sandbox.

Clean replay uses two roots inside the replay destination: `source/` for the target snapshot and `campaign/` for declared campaign-side harness/config inputs. The replay working directory and every input anchor are remapped to these roots. Verification must not read the original campaign harness after preparation.

## Research counters

Track separately:

- hypotheses investigated;
- concrete candidate/control executions;
- compilation and harness repairs;
- fuzzer campaigns, regardless of internal EVM executions;
- solver campaigns;
- validated root causes.

Deletion does not restore budget. Preserve negative results.

## Mechanical evidence ceilings

| Level | Mechanically required |
|---|---|
| E0 | Recorded hypothesis and mechanism |
| E1 | Exact writer/guard/consumer code evidence |
| E2 | Reachable sequence plus actor/prerequisite justification |
| E3 | Concrete execution reaches the predicted suspicious state |
| E4 | Protocol-property violation plus causal negative control |
| E5 | Implementation, configuration, actor, and economic/dependency fidelity declarations |
| E6 | Clean mechanical replay plus a nonce-bound rationale-withheld packet confirmed by a primary-attested visible built-in subagent; an E6 EvidenceBundle links the candidate, replay, task, and bound review records |

Levels are cumulative ceilings. The runtime verifies record relationships and declared fields, not whether the declarations are true. It cannot authenticate Codex UI thread identity; the primary explicitly attests the thread visible through `/subagents`, and the user can inspect it. Codex must still inspect code, traces, state, accounting, and actor capabilities.

## Secret handling

- Store only RPC variable names.
- Store only explorer API variable names. Provider responses may be immutable evidence; credentials and credential-bearing URLs may not.
- Session-owned fork records assert `upstream_secret_exposed=false`, record chain/block/hash, PID, logs, stop command, and RPC accounting, and preserve only loopback/filtered local endpoints.
- Use an exact `@env:NAME` argument token for command-time substitution.
- Redact resolved values from captured output, including values split across stream chunks.
- Never place secrets in prompts, subagent task packets, run plans, ledger records, events, or Git.

The resolved upstream URL is necessarily visible to the local Anvil process while it is running. Protect the host and `/proc` boundary accordingly.
