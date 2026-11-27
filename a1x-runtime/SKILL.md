---
name: a1x-runtime
description: Operate the deterministic A1X campaign runtime for an authorized Solidity/EVM investigation. Use when Codex must create durable campaign records, seal and execute commands, manage a pinned Anvil fork, preserve redacted evidence, replay a run, enforce impact and completion gates, or run isolated test-time-scaling and recursive self-aggregation populations. Exclude semantic vulnerability judgment, live-chain transactions, target selection, and external submission.
---

# Operate the A1X evidence runtime

Use the bundled `scripts/a1x` CLI for repeatable mechanics. Keep Codex responsible for protocol reasoning, experiment design, trace interpretation, and next-action selection. The runtime never decides whether a vulnerability is real.

## Locate the CLI

Resolve this skill's directory from the active skills catalog, then set a task-specific variable:

```bash
A1X_CLI=/absolute/path/to/a1x-runtime/scripts/a1x
"$A1X_CLI" --version
```

Do not guess an installation path. Do not expose RPC values while locating the CLI.

## Start or resume a campaign

Read [command-guide.md](references/command-guide.md) before first use. Run `doctor`, then initialize one campaign outside target compilation paths. Pin source, chain, block, authorization statement, RPC variable **name**, and resource budgets. Resume an existing `campaign.json` instead of creating parallel state trees.

Initialization also creates `ROUND-0001`, the mandatory blind four-axis population. Run and aggregate it before narrowing the hunt. Treat the hash-chained campaign event log as authoritative. Treat sealed plans, immutable objects, typed EvidenceBundles, Recon Packs, receipts, observations, replays, frontiers, impact branches, and controller assessments as evidence. Read [v4-architecture.md](references/v4-architecture.md) and [artifact-contract.md](references/artifact-contract.md) before modifying or moving them.

Existing v3 campaigns remain readable and continue writing v1 records. Run `campaign migrate` explicitly before using v4-only evidence, recon, operation, RSA graph, or blind-review features. Migration anchors the untouched legacy event log; it never rewrites prior records.

## Record reasoning before execution

1. Add a protocol obligation.
2. Add a falsifiable hypothesis with supporting and refuting predictions.
3. Create a sealed run plan before observing output.
4. Declare every source, harness, configuration, corpus, or model input needed to replay the command.
5. Execute the run once. Create a new run ID after changing the plan or inputs.
6. Interpret the raw logs, then record an observation. Never let an exit code stand in for a security property.

Use `@env:NAME` only as an entire command argument. The runtime resolves it at process launch, redacts it from captured output, and keeps the template in the manifest. Pass other environment variables only when the tool truly requires them.

## Manage fork state

Use `prestate serve` to expose read-only pinned state over a Unix-domain socket. It rewrites dynamic block tags, rejects explicit blocks beyond the campaign pin, and rejects transaction/receipt/trace or block-hash references that resolve after the pin; this prevents historical blind-test leakage through an archive node. For scaled investigations, `scale run --lane-forks auto` creates one independently writable Anvil fork per lane when the campaign's RPC variable is available. The host supervisor keeps the upstream credential in memory, gives Anvil a pinned caching loopback proxy, and exposes only a filtered UDS to the lane. Before Codex starts, the coordinator probes the direct UDS helper, the HTTP bridge needed by Forge/Cast, and the lane-fork MCP server, then writes `.a1x/fork-transport.json`; direct/MCP failure stops the lane as an environment error instead of consuming research turns. The portable lane interface is `a1x-lane-fork rpc METHOD '[params]'`; use `a1x-lane-fork exec -- <command> ... @fork` for HTTP-only clients when its probe is ready. Never pass the upstream URL into a lane. Reset, upstream-retargeting, and node-metadata RPC methods are blocked. Use `--lane-forks require` when a fork is mandatory and `off` for source-only work.

Use `explorer retrieve` or the `explorer_retrieve` campaign MCP tool for host-side Etherscan V2 source/ABI retrieval. Only the environment variable name is recorded. Preserve the raw provider response as immutable evidence, and treat proxy implementation metadata as unpinned until verified at the campaign block.

Never use the fork manager to broadcast a live transaction. A local fork endpoint must remain loopback-only.

## Replay and gate candidates

Replay a sealed supporting run from a clean workspace at the recorded commit. Create a candidate only after reviewing its observation. Add a causal control, applicability fidelity, and clean replay. For v4, E6 requires `review prepare-blind` followed by `review execute-blind`; a manually asserted `independent=true` review cannot satisfy the gate.

`candidate gate` reports a **mechanical evidence ceiling**. Read [artifact-contract.md](references/artifact-contract.md) for E0-E6 semantics. The gate validates artifact relationships and declared outcomes; it cannot verify the protocol model, actor reachability, economics, novelty, or bounty eligibility.

## Scale adaptively

Read [scaling-runtime.md](references/scaling-runtime.md). The bootstrap round is unconditional. Later rounds require a grounded mechanism, reached state, narrowed constraint, or discriminating observation. Provide distinct semantic axes, not temperature-only duplicates. The runtime creates isolated worktrees, runs `codex exec --json` with a strict output schema, preserves JSONL/process output, and strips API-key environment variables by default.

Use `scale evolve` when one source-faithful partial witness needs closure or two grounded components exist. It combines protected `K=1` witness-closure lanes, compatibility-tested `K=2` children, reserve rotation, fresh-lane injection, family-first allocation, and exact artifact/sequence deduplication. Runtime-owned lineages and stable prerequisite IDs control progress; lane IDs, round IDs, free-text family overlap, new unresolved prose, or unrelated fresh discoveries cannot reset a stalled lineage. A protected closure failure receives a bounded retry and remains explicit if unresolved. Retention remains fail-closed and lane-unique when anchors are weak. Children receive read-only exported parent artifacts, not only prose. Use typed evidence and `rsa graph` when composing across backends.

## Recover without losing research state

Treat runtime and tool failures as classified observations, never as semantic refutations:

- On SIGINT/SIGTERM, allow `scale run` to cooperatively stop lane process groups and their disposable forks. Resume the same partial round; do not create a replacement round merely to escape stale state.
- Before manually stopping a fork, verify that its recorded round controller is no longer alive. Stop only that campaign's `running` fork IDs. Never use a broad process kill as campaign recovery.
- A permission, approval, sandbox, MCP-startup, RPC-transport, compiler, missing-dependency, or backend crash is an `environment-blocked`/backend-capability result. Preserve the hypothesis unchanged, record the exact failed operation and artifact, repair or route to a compatible backend, then rerun the same discriminator.
- If a target builds in Foundry but fails Wake/crytic-compile/Echidna because of `via-ir`, mixed compilers, Vyper, remappings, or missing packages, record the target-specific `failed_reason` in the capability snapshot. Continue with Foundry and compatible specialists; machine-level installation is not target readiness.
- A failed baseline or withheld incident PoC does not invalidate independently reproduced behavior when the failure is packaging or dependency related. Report the baseline failure separately and do not inflate the independent evidence level.
- Preserve an executed near-miss when it establishes a primitive, waypoint, constraint, reachable prefix, or exact blocker. RSA may inherit it. Refute only the mechanism actually falsified; never erase sibling parents or broader mechanism families through an incompatible composition.

After any recovery, verify the event chain, round receipt, fork statuses, and artifact hashes before allocating more lanes. A repair is complete only when no stale controller ownership or campaign fork remains.

Run `capability probe` per target. Machine installation never implies target compatibility. The probe's immutable lane copy controls routing, campaign-scoped compiler caches are copied into lane homes, and approved executables remain available through the sanitized PATH. When Wake passes the target probe, scaling injects a lane-local stdio `wake-lane` MCP server rooted at `target/`. Route each unresolved causal edge through `operation propose` and evented transitions. Foundry is the final replay substrate; Wake is preferred for independent Python economic models; Echidna 2.4 is preferred for interactive campaign steering; Medusa, Halmos, and ItyFuzz are capability-gated specialists. Read [backend-routing.md](references/backend-routing.md).

## Propagate impact and close

Candidate creation automatically allocates four independent expansion lanes. Record downstream consumers for every non-rejected candidate with `impact add`; there is no authority or terminal-impact bypass. Register the exact downstream property. A demonstrated branch requires a property-violating run and matching replay; high-consequence promotion additionally requires a distinct control run testing that same property. High-consequence refutation requires execution or an anchored unreachability proof. Missing promotion evidence leaves the branch open. Record meaningful challenge of the value, authority, lifecycle, numeric, and composition coverage families. Track high-priority low-cost next actions with `frontier`. Allocation failure preserves the candidate/frontier record and records the blocker.

Run `controller assess` throughout the hunt. `controller close` refuses completion when bootstrap work is incomplete, coverage is missing, a candidate lacks expansion/refutation, impact branches remain open, a cheap high-value action remains, or distinct grounded components have not received an RSA generation. Close with an explicit matching class: clean, budget-exhausted, environment-blocked, or open-risk. Never label a blocked high-consequence sink clean.

## Stop conditions

Stop or pivot when runs cease to resolve material uncertainty, a prerequisite is impossible, fidelity cannot be established, or the campaign budget is reached. A validated intermediate capability is not a stop condition. Do not evade a budget by deleting records. Preserve refutations and near-misses.

## Output contract

Return campaign-relative artifact paths, record IDs, exact redacted command templates, evidence ceiling, observed limitations, and the next discriminating action. Never paste secrets, claim semantic proof from runtime gates, or describe an unreviewed lane handoff as a finding.
