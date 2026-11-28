# Runtime artifact and evidence contract

## Immutability and integrity

- `campaign.json` holds identity, budgets, and research counters.
- `events.jsonl` is an append-only, sequence-numbered hash chain in v4. Authoritative JSON writes are write-ahead materialization events; recovery reapplies a valid pending tail before campaign work resumes. Explicit v3 migration anchors the legacy bytes and never rewrites them.
- `evidence/objects/sha256/` holds immutable raw objects; `evidence/bundles/` holds typed claims and provenance.
- `recon/vNNNN/` holds immutable facts and explicit unknowns outside the source tree.
- Continuation, trace-fact, surface, composition, actor, oracle, harness, and solver-job records are authoritative hash-chained campaign materializations, not disposable worker notes.
- Plans, receipts, observations, and replay verifications have SHA-256 seals.
- A run plan and its observation are single-use. Change an input, command, property, prediction, or interpretation by creating a new run.
- Declared file and directory hashes exclude common build caches but include harness and configuration inputs.
- Atomic writes use a temporary file, `fsync`, and rename under a campaign lock where allocation or shared counters require serialization.

The runtime does not make the full campaign tamper-evident against a malicious local user. Seals catch accidental or out-of-band mutation; they are not signatures.

A continuation result is not inherited prose. The parent replay and preserved assertions are one evidence relationship; the distinct observed extension run and its clean replay are another. An operational failure may omit the extension pair but cannot count as semantic stagnation or prerequisite closure. A within-transaction waypoint is a trace coordinate inside the enclosing top-level transaction, never a resumable blockchain state.

Scale-lane artifacts are not runtime execution records. The host-owned scale binding re-resolves sealed plans, receipts, observations, and replay verifications, then requires the selected lane artifact to equal a named run artifact by SHA-256. E4 also rechecks the runtime's paired-control contract. Unary protected work must bind the exact continuation attempt; K=2 must bind the exact executable composition. Without that binding the handoff remains E1 and cannot affect RSA selection, fitness progress, or closure accounting.

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

Before a real Codex population round, A1X tests the Bubblewrap user/network namespace operation used by the lane sandbox. A failed preflight records the round as `environment-blocked`; it never silently disables the sandbox or mislabels the worker failure as a refutation.

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
| E6 | Clean mechanical replay plus a fresh-process, sealed-packet, mechanically blind confirming review; an E6 EvidenceBundle must link the qualifying candidate, replay, and blind-review records |

Levels are cumulative ceilings. The runtime verifies record relationships and declared fields, not whether the declarations are true. Codex must still inspect code, traces, state, accounting, and actor capabilities.

## Secret handling

- Store only RPC variable names.
- Store only explorer API variable names. Provider responses may be immutable evidence; credentials and credential-bearing URLs may not.
- Per-lane fork records must assert `upstream_secret_exposed=false`, record chain/block/hash and RPC accounting, and preserve only the filtered UDS path plus host-local ports.
- Use an exact `@env:NAME` argument token for command-time substitution.
- Redact resolved values from captured output, including values split across stream chunks.
- Keep API-key environment variables out of Codex population lanes by default.
- Give population lanes only temporary mode-restricted copies of necessary Codex state; never writable links to operator credentials.
- Never place secrets in prompts, run plans, handoffs, events, or Git.

The resolved upstream URL is necessarily visible to the local Anvil process while it is running. Protect the host and `/proc` boundary accordingly.
