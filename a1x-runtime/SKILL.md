---
name: a1x-runtime
description: Operate the deterministic local runtime for an authorized A1X Solidity/EVM investigation. Use to create/query the compact hunt ledger, seal and execute commands, manage a disclosed pinned Anvil fork, preserve evidence, replay runs, and enforce impact/completion gates. Exclude semantic vulnerability judgment, model orchestration, live-chain transactions, target selection, and submission.
---

# A1X deterministic runtime

Use `scripts/a1x` for repeatable mechanics. The primary Codex chat owns reasoning, tool choice, subagents, experiment design, interpretation, and next actions.

The runtime must never invoke `codex`, another model CLI, or a model API. The installed V5 runtime excludes the quarantined V4 scale/RSA/lane implementation. Built-in subagents are invoked by `$a1x` in the current chat, never by this script.

## Locate and inspect

Resolve this skill directory from the skills catalog; do not guess an installation path. Use a task-specific shell variable, then run `scripts/a1x --version` and `scripts/a1x doctor`. Never print environment values while discovering RPC or explorer variable names.

Read [command-guide.md](references/command-guide.md) before first use and [artifact-contract.md](references/artifact-contract.md) before moving or interpreting evidence.

## Campaign and ledger

Create one campaign outside target build paths. Initialization records source identity, authorization, chain/pinned block, budgets, event state, and a V5 ledger; it starts no fork, worker, or model process.

The canonical research memory is `v5/ledger.json`, with deterministic `ledger.tsv` and `brief.md` projections. Use:

- `ledger add` for `SCOPE`, `OBL`, `INV`, `EXP`, `FACT`, `TASK`, and `SYN`;
- `ledger list/show/brief` for context recovery and queries;
- `ledger update --expected-revision` for concurrency-safe transitions;
- `ledger verify --repair-views` to validate/rebuild projections;
- `ledger migrate-v4` for an additive preview, then `--apply` to import legacy provenance without changing old records.

An `INV` keeps its identity as its stage changes. A `TASK` requires one bounded decision question. A `SYN` requires a revised testable attempt and next discriminator. Keep large logs and immutable run/replay/artifact data outside the ledger and reference them by ID/path/hash.

## Runs and evidence

Record canonical `OBL`, `INV`, and one `EXP` per experiment before execution, then cross-link the typed obligation/hypothesis/run through their required `--ledger` arguments. Create a sealed run plan with property, support/refute predictions, exact inputs, command template, timeout, fork ID, and control relationship. Planning binds the run to its `EXP`; observation closes that experiment. Execute once; create a new run after changing plan or inputs. Record observations separately from raw output and interpretation.

Use `@env:NAME` only as a whole argument. The runtime resolves it at launch, redacts captured output, and preserves the template. Do not store secret values.

Ingest immutable evidence objects, analyze deterministic trace facts, and build typed EvidenceBundles. Exit code, scanner output, symbolic witness, fork balance delta, or generated PoC alone is not a security conclusion.

## Session-owned pinned fork

Use `fork start/status/snapshot/revert/stop` for a writable local Anvil fork. `fork start` must pin and verify chain, block, and block hash and return fork ID, loopback endpoint, supervisor PID, logs, and baseline snapshot. Announce these in the current chat. The upstream credential stays outside prompts/artifacts and the local endpoint must never broadcast to live assets.

Serialize mutations on one fork. Revert to the baseline before independent experiments. Concurrent experiments need separate disclosed fork IDs. Stop every running fork before campaign closure; never use broad process kills.

Use `prestate serve` only when a read-only pinned-state facade is needed. It rejects state beyond the campaign pin. Explorer retrieval is host-side and records only the credential variable name.

## Execution specialists

Use capability and target probes before routing. Foundry remains the concrete replay substrate. Use trace/surface/oracle/actor/component/harness/progress/solver commands for deterministic facts and bounded experimental state. Wake, Echidna, Medusa, Halmos/Z3, and ItyFuzz output remains provisional until source-faithful concrete execution and replay establish the claimed behavior.

Stateful harness records must explicitly cover state writers, valuable consumers, callbacks, actor capabilities, lifecycle, and numerical boundaries, including unknown/not-applicable entries. Preserve action/precondition/state telemetry and replay minimized failures.

## Replay, candidates, and closure

Replay support and control runs from clean recorded inputs. Candidate gates provide a mechanical evidence ceiling; they cannot validate the protocol model, attacker capabilities, economics, novelty, or bounty eligibility.

Record downstream impact properties and exact evidence. High-consequence claims require clean replay and an impact-specific causal control. Refutations require execution or a mechanically anchored impossibility proof.

`controller assess` checks research continuity, ledger/scope/impact state, evidence integrity, unresolved bounded work, candidate/impact gates, and process cleanup. V5 has no bootstrap lanes, populations, candidate-expansion lanes, or RSA generations. `controller close` requires a matching clean, open-risk, budget-exhausted, or environment-blocked disposition.

## Recovery

Classify tool, compiler, RPC, permission, sandbox, and backend failures as environment/tooling observations, never semantic refutations. Preserve the exact failed operation and artifact, repair or reroute, and retry the same discriminator when warranted. Verify ledger, event chain, artifact hashes, fork status, and replay state after interruption.

Return record IDs, campaign-relative paths, redacted command templates, evidence ceiling, limitations, and next discriminating action. Never claim semantic proof from a runtime gate.
