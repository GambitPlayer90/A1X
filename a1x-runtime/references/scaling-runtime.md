# Population and recombination runtime

## Activation

The campaign bootstrap round is mandatory and intentionally precedes admission filtering. Its purpose is coverage diversity before the coordinator forms a dominant narrative.

For later rounds, one grounded frontier with multiple material branches is enough. Do not wait for several finished candidates.

## Admission for later rounds

Create a round only when each admitted question has a code-grounded contradiction, replayable prefix, crossed guard, measured drift, narrowed constraint, or discriminating observation. The runtime cannot enforce semantic admission; record the reason in the lane prompt.

## Isolation

Each lane receives:

- an isolated filtered source snapshot under `target/`, recorded by digest and initialized as a new inert Git repository without running target hooks, filters, or checkout machinery;
- one semantic axis and bounded prompt;
- its own process group, timeout, stdout/stderr logs, JSONL stream, final structured handoff, and receipt;
- no other lane conclusions during the independent round.

Use `workspace-write` by default. Use `danger-full-access` only inside a separate disposable environment. Write-heavy lanes must not share a worktree or fork state.

The controller moves target `AGENTS.md`, `AGENTS.override.md`, and repository `.agents/skills` content into `.a1x-quarantine/` before Codex starts. The lane may inspect these as untrusted evidence but must not follow them as instructions. The generated workspace-root `AGENTS.md` establishes that boundary.

Each lane is started with an explicit, validated Codex cyber access program. The default is `standard`; optional Daybreak programs must match the signed-in account's entitlement. This policy selector is not a credential and does not grant access. It is passed directly to Codex rather than copied from arbitrary operator configuration.

Codex receives `--trust` only inside the lane's ephemeral `CODEX_HOME`. A1X creates the inert repository, quarantines target-supplied instructions, strips unrelated MCP configuration, and injects only the credential-free Wake and lane-fork MCP servers. This scoped trust is required for non-interactive `approval=never` workers to call those generated servers; it does not trust the operator's original workspace or persist after lane cleanup.

## Authentication boundary

The controller gives each lane a writable temporary `HOME` and a writable ephemeral `CODEX_HOME`. It copies the operator's existing Codex credential and only allowlisted non-secret scalar session preferences into that overlay, then injects A1X's target-scoped MCP stanza itself. Unrelated MCP registrations, environment maps, tokens, and arbitrary config tables are not inherited. Installed `.agents/skills` remain visible through a process-lifetime link. It runs `codex exec --ephemeral --ignore-rules`, then removes the skill link and destroys the overlay. A worker may refresh or overwrite its temporary copy but cannot write through to the operator original. Credentials are never placed in campaign artifacts. The controller removes `CODEX_API_KEY` and `OPENAI_API_KEY` unless the operator explicitly accepts environment-key exposure. Target-controlled commands must not run in an environment containing API keys.

Before starting a real `codex` binary, the runtime performs the Bubblewrap user/network namespace operation the lane sandbox requires. Failure records the round as `environment-blocked` with the exact first diagnostic; no worker or target command starts, and the completion controller treats it as an explicit non-clean environment limitation. Fake test executables are not subjected to this host-specific preflight.

When a lane fork is allocated, the coordinator also runs a transport self-test before the model starts. It verifies direct filtered-UDS RPC, the temporary loopback bridge used by HTTP-only Forge/Cast commands, and the stdio lane-fork MCP handshake. Results are recorded in read-only `.a1x/fork-transport.json`. A direct or MCP failure aborts preparation; an unavailable optional HTTP bridge is recorded so the lane does not waste turns rediscovering it.

## Handoff

The strict output schema records the tested obligation, discriminator, human-readable causal identity, artifact anchors for writer/guard/consumer/state/property, a stable attacker fingerprint, reached-state fingerprint, ordered transition sequence, mechanism family, valuable consumer, impact stage, concrete execution, evidence, refutations, next action, and visible Pareto dimensions. It also requires typed prerequisites, an executable-continuation replay declaration, a reachability-writer guard, and a bug-class witness: source fidelity, setup taint, ordered phase states, and artifact-backed phase-local signals such as invariant drift, share-rate drift, internal credit, authorization, liveness, custody loss, or attacker net. A structurally absent phase is `not-applicable`; it is never invented merely to satisfy a ladder. The host assigns lineage and prerequisite identities; a child cannot erase an inherited blocker by omission or declare it narrowed/resolved without evidence. Safe deduplication requires dedicated one-line attacker/state artifacts whose exact text equals the two declared fingerprints; generic shared traces fail closed into lane-unique reserve identities. It intentionally has no self-reported total quality score.

Every evidence path and blocker artifact must exist inside the lane workspace or process artifacts. The runtime hashes them and derives an evidence ceiling. A refutation must name the obligation, mechanism, discriminator, and evidence. A blocker must name the exact missing prerequisite, resolution condition, and evidence artifact. Empty “nothing found” handoffs are invalid. Treat invalid or missing handoffs as failed lanes and preserve their process logs for diagnosis.

## Aggregation

Aggregation validates and collates handoffs. `scale auto-select` reserves one active elite per artifact-anchored mechanism family before Pareto ranking, falling back conservatively when anchors are weak. Distinct overflow and coarsely anchored leads remain in `reserve`; they are eligible for later recombination. Only exact runtime-verified artifact regions plus the same attacker model, reached state shape, and ordered transition fingerprint may alias. It allocates compute; it does not establish truth. Manual selection automatically reserves omitted live leads and permits `drop` only for a retained exact duplicate.

## RSA-style recombination

`scale evolve` runs bounded generations with three explicit roles. A protected `K=1W` lane advances the first open edge of a source-faithful incomplete witness without changing target/root cause/consumer. A separately budgeted `K=1R` lane replaces a specific artificial prerequisite with permitted actions, but only after a static/call-graph/executed writability artifact shows a plausible unprivileged writer in the needed direction. `K=2` lanes combine structurally compatible grounded parents in sequential, nested callback, and temporal modes. Fresh blind lanes preserve independent breadth. The active pool is family-first and every other distinct lead is serialized into an immutable reserve. Incompatible parents remain separate evidence, not a forced merge.

The controller derives semantic deltas from runtime-verified causal anchors, waypoint/transition artifacts, witness phases, stable prerequisite transitions, setup fidelity, evidence level, impact stage, and refutation artifacts. Structured progress distinguishes witness advancement from information gain such as a narrowed feasible interval, mapped revert region, required ordering, dependency, or refuted assumption. It maintains attempt-aware state per runtime-owned lineage, so waiting alone is not stagnation and progress in an unrelated fresh lane cannot conceal a stalled partial exploit. Operational failures consume a separate allowance. Fair selection gives every eligible waiting lineage an opportunity; verified progress can extend work through a bounded adaptive-depth allowance. Added blockers and attack-path setup taint remain visible regressions. A protected closure lane is retried once after an operational failure and cannot be silently replaced by unrelated successful siblings. Rewording, lane/round identity, and fitness alone cannot count as progress.

Every protected continuation first replays the exact parent contract and its assertions. A semantic `advanced`, `narrowed`, `resolved`, or `refuted` result then requires a distinct observed extension run, exact extension replay, and evidence for the selected prerequisite observation. Between-transaction checkpoints may resume after committed state. Within-transaction waypoints must replay the entire enclosing transaction and may not be resumed as synthetic state.
