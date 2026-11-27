---
name: a1x-scale
description: Scale an execution-guided smart contract vulnerability hunt using mandatory independent lanes, evidence-aware candidate populations, semantic frontier search, and recursive self-aggregation. Use for the initial blind population and whenever one grounded frontier has multiple material branches. Exclude redundant same-prompt sampling, prose-only voting, and aggregation of ungrounded narratives.
---

# Scale vulnerability research while preserving diversity

Apply more inference and execution compute to a structured population. Scale mechanisms, attack prefixes, and evidence—not merely answer count.

## Mandatory activation

Run the bootstrap population created by campaign initialization before committing to one mechanism. Afterward, activate a new population when any grounded mechanism has multiple plausible consumers, impact paths, constraints, orderings, or refutations. Candidate creation already opens the required extension round; do not skip it because the current consequence appears reportable.

## Admission gate for later rounds

Scale only candidates containing at least one of:

- a code-grounded writer/consumer contradiction;
- a replayable state prefix;
- a crossed security-relevant guard;
- measured accounting/authorization/lifecycle drift;
- a narrowed numeric or ordering constraint;
- an execution observation that distinguishes the mechanism.

Ungrounded ideas remain hypotheses and should receive a cheap discriminator before population resources.

## Create diverse lanes

Read [population-design.md](references/population-design.md) and [hard-bug-search.md](references/hard-bug-search.md). Assign independent lanes by obligation, mechanism, actor model, consumer, lifecycle interruption, perspective flip, amplifier, or tool/search strategy. Different temperatures alone are insufficient diversity. Require at least one lane to challenge the assumed ownership/trust model and one to seek a multi-contract or multi-lifecycle composition when the target exposes either surface.

Each lane receives exact target identity, one bounded question, budget, allowed tools, campaign output path, evidence contract, and stop/pivot rule. Use `$a1x-runtime` to create isolated worktrees, launch structured `codex exec` lanes, preserve process output, and enforce lane/time/parallel budgets. Blind lanes should not receive other lanes' conclusions until synthesis.

## Select with external evidence

Use `scale auto-select` to allocate active slots across source-faithful execution, witness phase, phase-local property signal, stable prerequisite closure, evidence level, reachability, consequence, novelty, and next-test cost. It reserves one elite per anchored mechanism family before Pareto ranking. Runtime-owned lineages, rather than lane-authored family prose, control progress and closure. Distinct overflow and coarsely identified leads remain in a recombination reserve; only exact artifact-bound, ordered-sequence identities may alias. Selection is compute allocation, not a safety verdict.

Use execution and protocol-specific properties as the primary verifiers. LLM critique may generate tests or identify inconsistencies; it does not decide truth.

## Recombine carefully

Read [recursive-aggregation.md](references/recursive-aggregation.md) before RSA-style recombination. Exchange structured components:

- root-cause mechanism;
- required state and actor capabilities;
- transaction prefix and call ordering;
- solved parameters and constraints;
- observed traces/state deltas;
- unresolved blockers and refuting evidence.

Use `scale evolve` after aggregation when one source-faithful partial witness needs closure, one reproducible conditional mechanism needs reachable setup, or two grounded components can compose. Each generation reserves bounded `K=1W` witness-closure and `K=1R` reachability-closure lanes, stratifies compatible `K=2` parent pairs across sequential, nested callback, and temporal topologies, rotates reserved leads, executes every child, and injects fresh blind work to resist population collapse. K=1R admission requires an evidence-backed unprivileged writer path toward the exact artificial predicate. A closure lane receives its complete immutable parent packet and may not pivot to a different target, root cause, or consumer. It must replay the parent and inherited assertions, then use a distinct observed extension run plus clean replay before claiming progress. Preserve parents and reserves until an exact duplicate is proven or a mechanism-specific refutation closes them.

Allocation is attempt-aware and fair. Waiting is not stagnation, operational failure consumes a separate allowance, and an eligible lineage receives an investigation opportunity before repeatedly attempted siblings monopolize closure slots. Record witness progress separately from information progress. Verified progress may consume the bounded adaptive-depth allowance; prose changes, repeated nearby executions, and unrelated-lane discoveries may not. A failed protected closure lane receives a bounded retry and remains explicitly blocked if it still fails; successful siblings may not silently replace it.

## Tree and frontier search

Read [tree-search.md](references/tree-search.md) when action ordering is the primary uncertainty. Prefer semantic beam/frontier search before MCTS. Use MCTS only when actions, states, transitions, and intermediate values are stable and informative.

## Synthesis

The runtime can rank active work and preserve a reserve. Deduplicate only through the runtime's artifact-bound writer/guard/consumer/state/property, attacker-model, and reached-state anchors plus ordered transition fingerprint—not report title or prose paraphrase. Merge evidence without erasing contradictory observations. Route surviving candidates to `$a1x-validate` and feed refutations back into lane priors.

## Output contract

Return:

1. lane definitions, independence, and budgets;
2. admitted population with evidence and diversity dimensions;
3. generated children and compatibility rationale;
4. executed comparison against parents;
5. preserved refutations and dropped-candidate reasons;
6. marginal gain per scaling round and stop decision.
