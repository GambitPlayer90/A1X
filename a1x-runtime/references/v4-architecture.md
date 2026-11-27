# A1X v4 evidence architecture

The authoritative campaign is an event-sourced state machine. MCP and CLI are frontends; neither owns campaign state. In v4.4, every authoritative JSON materialization, including continuation, trace, surface, composition, actor, oracle, harness, and solver records, is appended and fsynced into the hash chain before its filesystem view is replaced. The event-state head advances last; startup recovery replays any valid tail events left pending by interruption. Existing v4 campaigns receive a one-time baseline event before further mutation. Migration from v4.3 is additive and does not rewrite prior records.

## Evidence layers

- `source/` remains the original target and is never polluted with generated conclusions.
- `recon/vNNNN/` contains immutable facts, explicit unknowns, target capabilities, and references to immutable objects.
- `evidence/objects/sha256/` stores content-addressed raw artifacts.
- `evidence/bundles/` stores typed observations and interpretations with provenance, backend/version, budget, target hash, and replay context.
- lane workspaces are writable overlays. Parent evidence is exported read-only for RSA children.
- `continuations/` stores immutable continuation contracts plus attempts; advancement requires a distinct observed extension run after exact parent replay and a clean replay of that extension.
- `compositions/`, `actors/`, `harnesses/`, `trace-facts/`, `surfaces/`, `oracles/`, and `solver-jobs/` hold the executable controller state used by completion assessment.

## Credential-free execution plane

The coordinator resolves RPC and explorer environment variables. It never copies their values into a lane. Each fork supervisor receives its upstream URL through a one-shot pipe, serves pinned cached reads to Anvil over host loopback, and exposes a filtered writable-local-fork UDS to exactly one lane. The pinned reader rejects explicit future blocks and post-pin transaction/trace/block-hash references. Per-command lane bridges translate the filtered UDS into an ephemeral loopback HTTP URL. Before a worker starts, the coordinator probes direct UDS RPC, that HTTP bridge, and the lane-fork MCP facade and records the result inside the lane. Reset, upstream-retargeting, and metadata methods are denied; all accepted RPC methods are accounted.

Verified-source retrieval is host-side. Provider responses become immutable artifacts and versioned Recon Pack inputs. Provider proxy metadata is not pinned-state evidence.

Allowed EvidenceBundle payloads are TransactionWitness, StatePrefix, CoverageGap, SolverConstraint, UnreachabilityEvidence, ReconFact, FailedExperiment, OracleDefinition, SemanticWaypoint, and ImpactExtension. An execution-grounded E3+ bundle needs an immutable artifact. E6 is reserved for independently reviewed impact evidence.

## Modern EVM context

Execution evidence records chain, pinned block, EVM revision, and transaction type. EIP-7702 records delegation already present at the starting block, delegate code hash, and an authorization list when the current transaction carries one. `tx.origin == msg.sender` is not evidence of non-programmability.

EIP-1153 records transaction lifetime, revert behavior, CALL versus DELEGATECALL ownership, and static-context restrictions. Reentrant observations of transient state belong in the witness.

## Progress and refutation

Population retention is fail-closed: weak identities remain unique. The host assigns runtime-owned lineages and stable prerequisite identities. Marginal-gain accounting excludes lane and round IDs and is tracked independently per lineage. Progress requires a runtime-derived, evidence-bound phase advance, prerequisite transition, causal edge, reachable waypoint, stronger oracle, cleaner setup, or mechanism-specific refutation. Added open edges and attack-path fixture taint remain visible as regressions. Protected `K=1W` lanes advance incomplete source-faithful witnesses, `K=1R` lanes replace exact artificial predicates through evidence-backed unprivileged writers in the required direction, and `K=2` lanes test sequential, nested, or temporal compositions; fresh lanes provide breadth. Fitness, new prose identity, waiting, operational failure, and unrelated-lane progress never reset a stalled lineage.

A high-consequence lead is not closed by prose, a failed harness, or a normal-state pass. Use a mechanism-specific negative execution or anchored unreachability evidence.

## Continuity, composition, and completion

A continuation contract binds one lineage to its actor model, transaction program, inherited assertions, selected prerequisite, execution topology, and either a between-transaction checkpoint or a within-transaction trace waypoint. A waypoint can be reproduced only by replaying the whole top-level transaction. Reachability closure is allocated separately from evidence promotion and requires an evidence-backed unprivileged writer path toward the artificial predicate.

Executable component contracts expose preconditions, effects, resources, obligations, invalidations, and transaction/callback/time context. Composition has three explicit topologies: sequential `A ; B`, nested `A_pre -> B -> A_post`, and temporal `A@t0 -> transition -> B@t1`. Every promoted composition has an exact run and replay. Multi-actor programs similarly bind actor capability, honest policy, ordering assumptions, every planned step, and replay.

The scheduler counts stagnation only after an attributable research attempt. Operational failure uses a separate allowance. Waiting eligible lineages receive fair closure opportunities, while verified witness or information progress can use a bounded adaptive-depth allowance. Completion automatically sweeps open continuations, prerequisite nodes, backtracking branches, executable components, actor programs, solver witnesses, harness-expansion tasks, and protected evolution failures. Silence never converts an unresolved lineage into a clean result.
