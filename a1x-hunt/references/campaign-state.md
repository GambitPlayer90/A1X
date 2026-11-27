# Durable campaign state

Create `audit-work/<campaign>/` with `$a1x-runtime`. The runtime owns machine records and may coexist with semantic Markdown maps:

```text
campaign.json
events.jsonl
deployment.md
system-map.md
obligations.md
coverage.md
hypotheses/
runs/
candidates/
replays/
reviews/
scale/
```

Keep target builds and generated tool output outside original source paths when practical. Runtime run directories preserve bounded redacted logs, receipts, hashes, and observations. Reference large tool-native corpora by path and hash.

## campaign.json and semantic notes

Initialize the machine record through the runtime. Maintain `deployment.md`, `system-map.md`, `obligations.md`, and `coverage.md` for detailed reasoning that does not fit stable fields. Record:

- exact in-scope repositories/commits and deployed addresses;
- authorized test techniques and explicitly excluded components/actions;
- repository commit and dirty-state note;
- chain, block, and RPC variable name;
- tool versions actually used;
- time, token, and execution budgets;
- current frontier and checkpoint;
- assumptions and unresolved inputs.

Never record secret values.

## Hypothesis record

Create the stable hypothesis through the runtime, then use a linked Markdown note when detailed reasoning is useful:

```markdown
# H-###: concise mechanism
Status: proposed | mapped | reachable | demonstrated | refuted | blocked
Obligation: O-###
Evidence level: E0-E6

## Claim
Specific actor and state transition that may violate the obligation.

## Preconditions
Actor, capital, state, timing, permissions, liquidity, and environment.

## Supporting prediction
Observable result if the mechanism is real.

## Refuting prediction
Observable result that would disprove or materially narrow it.

## Reached state
Replayable prefix and measured state deltas.

## Runs
Command, target identity, harness path/hash, result path/hash, observation.

## Strongest alternative explanation
Intended behavior, fixture artifact, arbitrage, setup privilege, or model mismatch.

## Next action
One discriminating action or explicit closure reason.
```

## Run record

For every evidence-bearing run, let the runtime seal the replay-exact command template, declared input hashes, working directory, fork reference, environment variable **names**, process result, and raw output paths. Use exact `@env:MAINNET_RPC_URL` argument tokens; never persist the resolved value. Add interpretation only after execution. Do not overwrite earlier records; create a new run ID after changing inputs or predictions.

## Stable record schemas

Use runtime IDs for managed records: obligation `OBL-####`, hypothesis `HYP-####`, run `RUN-####`, fork `FORK-####`, candidate `CAND-####`, replay `REPLAY-####`, review `REVIEW-####`, round `ROUND-####`, and round-local lane `LANE-####`. Use `D-###` and `C-###` only for semantic deployment/component maps.

### deployment.md

For every component record address/path, chain/block or commit, runtime/source hash, proxy/module relation, compiler/build identity, effective configuration, correspondence confidence, and unresolved identity gaps.

### system-map.md

For every critical flow record assets, custody, economic owner, liabilities, units, actors, entry/terminal transitions, external boundaries, failure/recovery paths, and critical state fingerprints. Link each security-relevant state item to its writers and consumers.

### obligations.md

For each `O-###` record property text, boundary, quantifier, actors, variables/units, permitted exceptions, writers, guards, consumers, observable violation, impact, evidence, linked hypotheses, and coverage state.

### coverage.md

Use rows keyed by obligation/path with state `unread`, `mapped`, `challenged`, `executed`, `refuted`, `blocked`, or `not-applicable`; include state range, actor/sequence bounds, evidence links, gaps, and reason for `blocked`/`not-applicable`.

### runs/RUN-####/

The runtime stores a sealed plan, receipt, bounded logs, and a sealed reviewed observation. Link any extended narrative rather than duplicating mutable facts.

### candidates/CAND-####.json

Record artifact-bound writer/guard/consumer/state/property anchors, ordered transition fingerprint, exact code evidence, reachability justification, property and control runs, impact accounting, fidelity declarations, replay, and independent review. Coarse identities remain distinct. The runtime gate reports only a mechanical evidence ceiling.

### Lane merge rules

Lanes allocate disjoint IDs or prefix IDs with lane ID until coordinator merge. The coordinator preserves original IDs as aliases, merges only identical causal fingerprints, retains contradictory observations, and never overwrites a stronger evidence artifact with a summary.

## Near-miss retention

Promote a near-miss into the exploration population when it contains reusable evidence such as a replayable state prefix, a crossed guard, a quantitative accounting drift, a newly resolved dependency, or a narrowed constraint. Store the exact blocker. Keep distinct admitted near-misses active or reserved until causal refutation. Compilation-only or prose-only ideas remain outside the population as hypotheses; do not mislabel them refuted.
