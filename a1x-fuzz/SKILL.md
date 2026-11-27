---
name: a1x-fuzz
description: Design and run focused stateful Solidity/EVM fuzz campaigns with Wake, Foundry, Echidna, Medusa, ItyFuzz, or another available snapshot/concolic fuzzer to resolve a specific protocol obligation or reachable attack-path question. Use after recon and obligation derivation when sequence, state, actor, or input exploration is the blocker. Exclude generic “fuzz everything,” vacuous properties, and clean-scan safety claims.
---

# Run focused stateful fuzzing

Use fuzzing as a discriminating instrument inside a hypothesis-driven hunt. Define the security property, state model, actor capabilities, and useful waypoints before choosing a fuzzer.

## Route the question

Read [tool-routing.md](references/tool-routing.md). Run the v4 target capability probe, then prefer:

- Wake 5 for agent-written Python action flows, independent economic/reference models, boundary construction, and rich multi-actor semantic experiments;
- Foundry fuzz tests for a small parameter space around a deterministic path;
- Foundry invariant tests for repository-native handlers and fast iteration;
- Echidna 2.4 for property/sequence campaigns, shrinking, corpus workflows, and experimental live campaign guidance;
- Medusa for parallel coverage-guided stateful campaigns and runtime-fed mutation;
- ItyFuzz or another installed snapshot/concolic tool when hard-to-reach persistent states, value-aware waypoints, or difficult comparisons dominate.

No specialist backend is universally required. Record exact versions/configuration used, keep native corpora backend-specific, translate promising results into typed evidence/transaction witnesses, and route by the concrete reachability question rather than running every engine.

## Define the campaign

Read [campaign-design.md](references/campaign-design.md). Specify:

- obligation and falsifiable hypothesis;
- independent property oracle and units;
- contracts/functions/assets/actors in scope;
- valid starting state and setup;
- handler actions, preconditions, bounds, and environmental transitions;
- semantic waypoints and coverage goals;
- supporting and refuting outcomes;
- budget, seed persistence, replay, and shrink plan.

## Build honest handlers

Read [handlers-and-ghosts.md](references/handlers-and-ghosts.md). Handlers should expose meaningful protocol actions, multiple actors, callbacks, time/epoch transitions, and honest interleavings without using impossible powers. Keep target code unchanged.

Use ghost state derived independently from the target implementation. Avoid duplicating the exact formula under test. Track assets, liabilities, claims, actor contributions, and expected lifecycle state at the level required by the obligation.

Before treating a campaign as representative, reconcile the harness against six explicit surfaces: relevant state writers, valuable consumers, callback programs, actor capabilities, lifecycle transitions, and numerical boundaries. Mark each item represented, missing, unknown, or not applicable. Completeness of the map itself remains an explicit unknown when dispatch, dependencies, callbacks, or writer discovery are unresolved.

Collect action attempts, precondition failures, reached state fingerprints, and replay outcomes from real runs. A missing action, excessive precondition rejection, or repeated-state loop creates a bounded harness-expansion task. Resolve that task only with a real run and clean replay showing the new surface; adding a handler in prose or source alone is not coverage.

## Run, replay, and interpret

Preserve seed, corpus, configuration, tool version, resource budget, and exact command in a `$a1x-runtime` fuzz-class run and immutable artifacts. Emit CoverageGap, StatePrefix, FailedExperiment, or TransactionWitness evidence as appropriate. Replay minimized sequences deterministically in Foundry. Inspect the first semantic divergence, then route the minimized witness to `$a1x-execute` and `$a1x-validate`.

If a campaign stalls, determine whether the problem is handler reachability, over-restrictive assumptions, a weak waypoint, dependency fidelity, or an unsuitable tool. Use runtime harness telemetry to select the smallest missing surface, expand it under a bounded budget, and replay the resulting sequence. Do not simply multiply runtime.

## Output contract

Return:

1. property and its independence argument;
2. handler/actor/environment model;
3. configuration, budget, coverage, and limitations;
4. replayable minimized counterexamples;
5. evidence-backed negative result as bounded coverage only;
6. exact next action for each useful near-miss.
