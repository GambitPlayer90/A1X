---
name: a1x
description: Run an authorized, single-session Solidity/EVM bug-bounty investigation from program scope and deployed-state recon through pinned-fork adversarial execution, stateful invariant fuzzing, exact numerical search, replay, and impact validation. Use for end-to-end smart-contract vulnerability hunts, especially difficult cross-contract, sequencing, accounting, and composability failures. Exclude target selection, live-chain exploitation, submission, and generic checklist-only review.
---

# A1X single-session vulnerability hunt

Operate as one persistent primary investigator in the current Codex CLI chat. Use installed tools as evidence producers and visible built-in subagents only for bounded independent questions. The durable campaign ledger is the shared memory.

Never launch `codex exec`, `codex fork`, `codex resume`, another model CLI, or a hidden model process. Never create populations, lanes, fixed generations, or mandatory worker counts. Scripts prepare deterministic state, task packets, executions, evidence, and queries; the primary agent invokes built-in subagents through the current session so their work is visible through `/subagents`.

All adversarial transactions must execute only in local tests or a pinned local fork. Never transact against live assets.

## Start or resume

1. Confirm the supplied target is authorized. Record the exact bug-bounty program, repository and deployed-contract boundary, chain, excluded components, testing restrictions, unprivileged attacker model, and the program's exact eligible impacts. Do not let a generic scanner category substitute for an eligible impact.
2. Locate `$a1x-runtime` by skill name and use its `scripts/a1x` helper. Create or resume `audit-work/<campaign>/`; initialization must create no worker or fork process. Run `ledger brief` before new work and `ledger verify` after material updates.
3. Record scope as an active `SCOPE` ledger item whose `data.impacts` is a non-empty list of exact program strings. A preliminary lead may remain open when it has a plausible path to one of those impacts; candidate creation and promotion require the exact `(scope ID, impact string)` pair.
4. Run the tool doctor and target probe without printing secret values. Record tool versions and target-specific failures. Treat missing optional backends as routing constraints, not as a reason to stop unrelated work.
5. For a new full hunt, read [workflow.md](references/workflow.md). Read [tool-routing.md](references/tool-routing.md) before choosing static analysis, execution, fuzzing, or solving. Read [hard-bug-search.md](references/hard-bug-search.md) when the target has nontrivial accounting, callbacks, lifecycle, cross-contract, cross-chain, or numerical behavior. Read [subagents-and-ledger.md](references/subagents-and-ledger.md) before delegating or synthesizing.

## Core investigation loop

Drive the hunt from program impacts and valuable consumers backward to attacker-controlled writers:

1. **Reconstruct.** Establish repository-to-bytecode identity, proxy/module/library resolution, on-chain configuration, assets, liabilities, internal claims, authority, external dependencies, and lifecycle. Use compiler AST, Slither CFG/call graphs, and related analyzers for inventory and navigation only; verify security claims in source, deployed state, and execution.
2. **Cover.** Resolve this skill's directory from the loaded `SKILL.md`. Always run bundled `scripts/entry_points.py` over the complete in-scope Solidity manifest. When Graphify succeeds, reduce its graph with `scripts/graph_summary.py`; never load the whole graph into context. Build `coverage-map.json`, then require `scripts/coverage_gate.py` to reconcile every file, entry point, and graph category before closure. If the separate `x-ray` skill is installed, reuse its richer enumeration, git-history, and report pipeline rather than duplicating it, but the bundled hard gate remains authoritative. Chain these machine-readable outputs into obligations and investigations. Record inspected, challenged, unknown, and not-applicable states with evidence. Graph coverage is not semantic coverage.
3. **Derive obligations.** State independent properties for conservation, backing, solvency, authorization, provenance, settlement, ordering, replay, lifecycle, liveness, and numerical behavior. Include units, rounding tolerance, actors, boundary, exceptions, support prediction, and refuting prediction.
4. **Form one falsifiable mechanism.** Identify a writer/guard/representation/consumer mismatch or lifecycle contradiction. Preserve secondary grounded leads as separate `INV` records rather than compressing them into one handoff.
5. **Compose reachability.** Build the shortest attacker-valid history across EOAs, helper contracts, attacker-created tokens/pools, callbacks, honest interleavings, transactions, blocks, epochs, and domains. Track capital, approvals, identities observed downstream, prerequisites, state deltas, and the realization/settlement step.
6. **Discriminate.** Choose the cheapest faithful test that separates the mechanism from its strongest alternative explanation. New grounded information may be source/configuration evidence, a reachable writer, exact numerical bound, executed trace, or scoped refutation. Behavioral and impact claims require EVM execution.
7. **Execute and observe.** Create one canonical `EXP` parented by the active `INV`, then pass it to the typed run plan. Use a source-faithful Forge test or a disclosed pinned Anvil fork. Record run plans, receipts, traces, observations, exact commands, artifacts, and state fingerprints. Candidate creation must reject support/control runs lacking the `INV ↔ EXP ↔ RUN` cross-link. Compilation repair is not hypothesis progress.
8. **Deepen selectively.** Route sequence-heavy questions to stateful invariant fuzzing, arithmetic blockers to exact models or bounded solving, and deployed-state composition to adversarial fork sequences. Do not run every backend. Preserve useful failures, constraints, revert regions, partial witnesses, and exact blockers.
9. **Validate.** Require deployment fidelity, attacker-valid reachability, an independently justified property, causal controls, clean replay, and net impact accounting. Trace acquired authority or internal credit into every material consumer before claiming the maximum consequence.
10. **Update the ledger.** Keep the same `INV` identity as it moves from lead to hypothesis to candidate to validated/refuted. Pass canonical ledger IDs to typed obligation/hypothesis commands so runs, candidates, and impact branches are cross-linked through `data.runtime_refs`. Every open record must name a next discriminating action or an explicit blocker.

Re-enter reconstruction whenever execution reveals an unknown writer, consumer, identity, configuration, callback, or dependency.

## Pinned Anvil and adversarial sequencing

For deployed targets, run a session-owned Anvil fork pinned to an exact block and block hash. Announce and record the fork ID, chain, block/hash, endpoint, PID, log paths, baseline snapshot, and stop command. Keep no provider credential in prompts or artifacts.

Revert to a clean baseline before independent experiments. Preserve state deliberately across transactions within one attack history. Serialize mutations to one fork; concurrent experiments require separate disclosed fork instances. Cheatcodes may establish ordinary environment setup, but must not manufacture the exploit prerequisite, protocol identity, capital claim, or attacker capability being asserted.

Adversarial programs must support multiple actors, callbacks, reentrancy boundaries, multi-transaction ordering, time/epoch movement, attacker-deployed components, flash liquidity, lifecycle changes, settlement, withdrawal, and residual obligations. For historical reproduction, fork before the earliest attacker-controlled prerequisite rather than inheriting corrupted state.

## Stateful invariant fuzzing

Treat stateful fuzzing as a first-class search mode for critical sequence-dependent state machines unless a concrete reason makes it inapplicable. Build handlers from real writers and consumers, with realistic actors, callbacks, lifecycle transitions, numerical boundaries, and honest interleavings. Use independent security oracles; do not restate the implementation formula as the invariant.

Record action counts, rejected preconditions, reached semantic states, seeds, corpus, shrink results, and replay commands. A minimized counterexample becomes a deterministic Forge/Anvil regression with neighboring positive and negative controls before promotion.

## Selective subagents and aggregation

Spawn visible built-in subagents only when independent work can change a decision: deployment/config verification, an unbiased alternative mechanism, one blocker-specific numerical search, alternate-consumer tracing, harness/accounting challenge, or independent replay/refutation. Announce each spawn. Give one bounded question, immutable artifacts, scope/attacker constraints, output requirements, and a stop condition. Withhold the preferred explanation when independence matters. Do not allow concurrent writes to the same harness or fork.

Invoke them automatically from the primary chat at these evidence checkpoints, without asking the user to operate another process:

- one deployment/configuration verifier when unresolved identity materially changes scope or execution fidelity;
- one or two independent workers when a grounded investigation survives its first faithful discriminator and has separable preparation, numerical, composition, or alternative-explanation questions;
- one rationale-withheld independent challenger for every candidate before E6 promotion.

Do not spawn merely because a phase began, and do not replace a blocked or unavailable built-in subagent with a shell/model command. Scripts create the ledger `TASK` and sealed packet; this skill—not a script—invokes the built-in collaboration tool because only the active Codex chat can create visible subagent threads.

Re-aggregate only when new grounded information materially changes the unresolved question. Preserve both:

- **Attack composition:** connect compatible executable state transitions.
- **Investigation synthesis:** combine complementary facts, constraints, and refutations from attempts at the same blocker.

Record synthesis as `SYN`. It must produce a revised testable attempt and next discriminator; a summary or vote is not progress. Bound concurrent workers, synthesis inputs, and repeated attempts without information gain.

## Promotion and closure

A candidate is promotable only when the exact deployment and state are established, the full attacker-reachable sequence executes, the independent obligation is violated, a causal control isolates the mechanism, clean replay passes, net impact and harmed party are measured, and an exact eligible program impact is named. State limitations explicitly.

Close a branch only as causally refuted, mechanically unreachable under the attacker model, environment-blocked, budget-limited with a preserved next experiment, outside scope, or validated. Never discard negative evidence that applies only to one configuration or sequence.

Before campaign closure:

- reconcile deterministic recon and entry-point coverage;
- challenge every high-value in-scope impact sink and critical lifecycle or justify it as not applicable;
- resolve or disclose every high-priority bounded ledger action;
- validate, refute, or bound every candidate and material acquired capability;
- stop every session-owned Anvil/fuzzer process;
- verify the ledger, event chain, evidence seals, and replay commands.

Return validated candidates, open investigations with exact blockers and next tests, scoped refutations, coverage limitations, deployment gaps, and reproducible commands. A clean hunt is a bounded coverage statement, never proof of safety or guaranteed vulnerability discovery.
