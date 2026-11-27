# A1X v4 evidence architecture

The authoritative campaign is an event-sourced state machine. MCP and CLI are frontends; neither owns campaign state. In v4.3, every authoritative JSON materialization is appended and fsynced into the hash chain before its filesystem view is replaced. The event-state head advances last; startup recovery replays any valid tail events left pending by interruption. Existing v4 campaigns receive a one-time baseline event before further mutation.

## Evidence layers

- `source/` remains the original target and is never polluted with generated conclusions.
- `recon/vNNNN/` contains immutable facts, explicit unknowns, target capabilities, and references to immutable objects.
- `evidence/objects/sha256/` stores content-addressed raw artifacts.
- `evidence/bundles/` stores typed observations and interpretations with provenance, backend/version, budget, target hash, and replay context.
- lane workspaces are writable overlays. Parent evidence is exported read-only for RSA children.

## Credential-free execution plane

The coordinator resolves RPC and explorer environment variables. It never copies their values into a lane. Each fork supervisor receives its upstream URL through a one-shot pipe, serves pinned cached reads to Anvil over host loopback, and exposes a filtered writable-local-fork UDS to exactly one lane. The pinned reader rejects explicit future blocks and post-pin transaction/trace/block-hash references. Per-command lane bridges translate the filtered UDS into an ephemeral loopback HTTP URL. Before a worker starts, the coordinator probes direct UDS RPC, that HTTP bridge, and the lane-fork MCP facade and records the result inside the lane. Reset, upstream-retargeting, and metadata methods are denied; all accepted RPC methods are accounted.

Verified-source retrieval is host-side. Provider responses become immutable artifacts and versioned Recon Pack inputs. Provider proxy metadata is not pinned-state evidence.

Allowed EvidenceBundle payloads are TransactionWitness, StatePrefix, CoverageGap, SolverConstraint, UnreachabilityEvidence, ReconFact, FailedExperiment, OracleDefinition, SemanticWaypoint, and ImpactExtension. An execution-grounded E3+ bundle needs an immutable artifact. E6 is reserved for independently reviewed impact evidence.

## Modern EVM context

Execution evidence records chain, pinned block, EVM revision, and transaction type. EIP-7702 records delegation already present at the starting block, delegate code hash, and an authorization list when the current transaction carries one. `tx.origin == msg.sender` is not evidence of non-programmability.

EIP-1153 records transaction lifetime, revert behavior, CALL versus DELEGATECALL ownership, and static-context restrictions. Reentrant observations of transient state belong in the witness.

## Progress and refutation

Population retention is fail-closed: weak identities remain unique. The host assigns runtime-owned lineages and stable prerequisite identities. Marginal-gain accounting excludes lane and round IDs and is tracked independently per lineage. Progress requires a runtime-derived, evidence-bound phase advance, prerequisite transition, causal edge, reachable waypoint, stronger oracle, cleaner setup, or mechanism-specific refutation. Added open edges and attack-path fixture taint remain visible as regressions. A protected `K=1` lane advances an incomplete source-faithful witness; `K=2` lanes compose compatible parents; fresh lanes provide breadth. Fitness, new prose identity, and unrelated-lane progress never reset a stalled lineage.

A high-consequence lead is not closed by prose, a failed harness, or a normal-state pass. Use a mechanism-specific negative execution or anchored unreachability evidence.
