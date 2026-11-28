<h1 align="center">A1X</h1>

<p align="center">
  <strong>Single-session, execution-guided smart-contract vulnerability research for Codex CLI</strong>
</p>

<p align="center">
  Scope-bound · Deployed-state aware · Composition-first · Replayable evidence
</p>

<p align="center">
  <a href="#why-a1x">Why A1X</a> ·
  <a href="#end-to-end-workflow">Workflow</a> ·
  <a href="#installation">Install</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#durable-research-state">Ledger</a> ·
  <a href="#evidence-and-promotion">Evidence</a>
</p>

![A1X V5 single-session vulnerability research workflow: authorized scope and deployment, recon and obligations, reachable experiments, selective synthesis, validation and impact accounting, all supported by an atomic research ledger and local-only execution.](docs/images/a1x-v5-single-session.png)

<p align="center">
  <sub>One Codex chat. Visible built-in subagents. Pinned-fork execution. Durable evidence.</sub>
</p>

A1X is an authorized Solidity/EVM bug-bounty and audit workflow for investigations that do not fit inside one function or one transaction. It works backward from the program's exact eligible impacts, reconstructs the deployed system, derives protocol-specific obligations, builds attacker-reachable histories, and tests them with source-faithful execution.

The current runtime is **5.2.0**. V5 replaces A1X's external lane/population controller with a persistent primary Codex session, selective visible subagents, deterministic local helpers, and an atomic campaign ledger. V5.1 bound candidate replay and sealed evidence to the exact support run, made recon coverage a completion gate, and inventoried security-relevant read surfaces. V5.2 binds recon scans to the exact parsed source bytes, requires performed or content-addressed synthesis follow-through, and preserves deferred high-consequence synthesis in completion risks.

> [!IMPORTANT]
> A1X is for explicitly authorized research. Adversarial transactions run only in local simulations or pinned local forks. A1X does not authorize live-chain exploitation, target selection, disclosure, submission, or automated transactions against live assets.

## Why A1X

Difficult smart-contract failures often emerge from interactions among deployed configuration, internal accounting, exact integer arithmetic, callbacks, lifecycle transitions, external protocols, and multiple transactions. Static analysis and formal verification are valuable, but neither automatically proves that the modeled property, environment, or composition boundary matches the deployed economic system.

A1X therefore treats tools as evidence producers inside an investigation loop:

- begin with exact program scope, attacker capabilities, and payable impacts;
- establish source, bytecode, proxy, module, library, and configuration identity;
- reason in terms of assets, liabilities, internal claims, authority, writers, guards, representations, and valuable consumers;
- compose the shortest attacker-valid sequence that reaches a falsifiable security property;
- route the blocker to concrete execution, stateful fuzzing, exact arithmetic, or bounded solving;
- preserve useful failures and partial witnesses instead of restarting from prose;
- require causal controls, clean replay, net impact accounting, and exact scope binding before promotion.

The workflow is designed to support hard accounting, rounding, provenance, settlement, composability, transient-state, cross-contract, lifecycle, and cross-domain investigations. It does **not** hard-code historical incidents as patterns to match, and it does not guarantee that every vulnerability will be found.

## What changed in V5

| Preserved and strengthened | Removed from the active workflow |
|---|---|
| Deployment and value-flow reconstruction | External `codex exec`/fork/resume worker processes |
| Protocol-specific obligations | Blind bootstrap lanes and fixed worker populations |
| Unprivileged attacker reachability | Mandatory generations and predetermined allocation ratios |
| Pinned Anvil execution and adversarial sequencing | Lane handoffs as the primary research representation |
| Stateful invariant fuzzing and exact numerical search | Automatic RSA schedules disconnected from evidence |
| Partial witnesses, blockers, refutations, controls, and replay | Hidden model subprocesses and background model orchestration |
| Selective attack composition and investigation synthesis | Phase skills that fragmented one investigation across contexts |

The useful research principle remains: independent attempts can contribute executable steps, numerical constraints, reachable preparation, or negative evidence to a better next experiment. Aggregation occurs only when grounded information changes what can be tested next. There are no mandatory worker counts or generation schedules.

## End-to-end workflow

| Stage | Primary question | Durable result |
|---|---|---|
| **1. Scope and deployment** | What is authorized, deployed, attacker-reachable, excluded, and paid by this program? | Exact scope strings, attacker model, deployment identity, pinned block and hash |
| **2. Recon and obligations** | What must remain true across assets, claims, authority, lifecycle, and consumers? | Sealed file, mutation-entry-point, and reader-surface coverage; system map; independent properties; falsifiable mechanisms |
| **3. Reachable experiments** | What is the shortest faithful history that distinguishes the mechanism from its strongest alternative? | Forge/Anvil runs, traces, state deltas, fuzz counterexamples, numerical bounds, scoped refutations |
| **4. Selective synthesis** | Can compatible transitions or complementary findings unlock a materially better test? | Revised executable attempt and next discriminator—not a vote or summary |
| **5. Validate and account** | Is the behavior reachable, causal, replayable, economically real, and exactly in scope? | Clean replay, controls, net impact, harmed party, limitations, independent challenge |

Execution can send the investigation back to recon whenever it reveals an unknown writer, consumer, identity, configuration, callback, or dependency.

### Impact-backward search

A1X does not treat a generic vulnerability category as the objective. It records the bug-bounty program's exact eligible impact strings, identifies the valuable consumers capable of realizing those impacts, and searches backward through guards and representations to attacker-controlled or attacker-obtainable writers.

Early grounded discoveries can receive bounded research time before their final consequence is known. Candidate promotion, however, requires an exact `(scope ID, eligible impact string)` binding.

### Reachable attack composition

Experiments can model multiple actors, attacker-deployed components, flash liquidity, callbacks, reentrancy boundaries, honest interleavings, multi-transaction ordering, time or epoch movement, settlement, withdrawal, residual obligations, and acquired authority. Cheatcodes may create ordinary test setup; they may not manufacture the exploit prerequisite or attacker capability being claimed.

### Stateful and numerical search

Sequence-heavy state machines route to stateful invariant fuzzing with realistic handlers and independent oracles. Arithmetic blockers route to exact integer models, boundary search, or bounded symbolic solving. A minimized counterexample becomes a deterministic Forge/Anvil regression with neighboring positive and negative controls.

### Selective subagents

The primary investigator stays in one Codex CLI chat. Built-in subagents are visible through `/subagents` and are invoked only when independent work can change a decision—for example:

- deployment or configuration verification;
- an unbiased alternative mechanism;
- one blocker-specific numerical or reachability question;
- alternate-consumer tracing;
- harness, accounting, replay, or impact challenge.

A rationale-withheld challenger reviews every candidate before the highest evidence level. Scripts may prepare ledger tasks and sealed review packets, but scripts never launch agents. No unavailable subagent is replaced with a hidden model subprocess.

## Tool routing

A1X selects tools by the unresolved question instead of running every backend:

| Question | Typical evidence producer |
|---|---|
| Complete source, mutation, and reader coverage | Bundled manifest/coverage gates, generated-getter inventory, compiler AST, Slither, Graphify |
| Deployed code and configuration identity | Cast/RPC, verified source, bytecode and proxy/module resolution |
| Concrete behavior and traces | Forge tests and a disclosed pinned Anvil fork |
| Sequence-dependent state-machine failures | Forge invariant tests, Echidna, Medusa, Wake, or ItyFuzz when target-compatible |
| Exact rounding, amount, ordering, or boundary constraints | Exact integer models, bounded Python search, Z3/Halmos when useful |
| Candidate causality and consequence | Independent oracle, negative control, clean replay, trace facts, net impact accounting |

Scanner output, a symbolic witness, an exit code, or a generated PoC is a lead—not a security conclusion. Optional tools are capability- and target-gated; a missing specialist does not block unrelated work.

## Durable research state

Each campaign stores a compact authoritative ledger in `v5/ledger.json`, with deterministic `ledger.tsv` and `brief.md` views for recovery and querying.

| Record | Purpose |
|---|---|
| `SCOPE` | Authorized target, attacker model, exclusions, and exact eligible impacts |
| `OBL` | Independently justified protocol property and oracle |
| `INV` | Stable investigation identity from lead through validated/refuted state |
| `EXP` | One falsifiable experiment attached to an investigation |
| `FACT` | Grounded source, configuration, execution, numerical, or negative evidence |
| `TASK` | One bounded question for the primary investigator or visible subagent |
| `SYN` | Grounded inputs and information delta, revised attempt, next discriminator, and inspectable follow-through |

Large logs, traces, receipts, replays, and immutable artifacts remain outside the ledger and are referenced by ID, path, and hash. Revision-checked updates prevent stale writers from silently overwriting current state.

The typed evidence chain is:

```text
SCOPE → OBL → INV → EXP → RUN → observation/replay → candidate → exact eligible impact
```

An investigation keeps the same `INV` identity as it moves from lead to hypothesis, candidate, validated, or refuted. V4 campaigns migrate additively into a V5 sidecar; legacy evidence is not rewritten or resumed as external lanes.

## Evidence and promotion

Evidence levels are mechanical ceilings over linked records, not semantic truth:

| Level | Required relationship |
|---|---|
| **E0–E2** | Recorded mechanism, code grounding, and justified reachability |
| **E3** | Concrete execution reaches the predicted suspicious state |
| **E4** | Independent property violation plus causal control |
| **E5** | Deployment, configuration, actor, and economic fidelity |
| **E6** | Clean replay plus sealed, rationale-withheld review by a distinct visible built-in subagent |

Execution alone does not validate the security property, attacker model, accounting interpretation, or impact. A clean campaign is a bounded coverage statement, never proof of safety.

## Installation

### Requirements

- Linux and Python 3.11+
- Git and `rsync`
- Codex CLI with built-in subagents
- Foundry (`forge`, `cast`, and `anvil`)
- a historical-state-capable RPC endpoint for deployed-state work

Optional target-gated specialists include Slither, Graphify, Wake, Echidna, Medusa, ItyFuzz, Halmos/Z3, and Aderyn.

### Clone over SSH

```bash
git clone git@github.com:GambitPlayer90/A1X.git
cd A1X
```

### Install the V5 skill surface

V5 installs only the canonical skill, its compatibility alias, and the deterministic runtime. Quarantined V4 worker code remains in the repository for regression history and is excluded from installation.

```bash
mkdir -p "$HOME/.agents/skills"
rsync -a --delete --delete-excluded --exclude=tests/ --exclude=__pycache__/ --exclude='*.pyc' \
  a1x/ "$HOME/.agents/skills/a1x/"
rsync -a --delete a1x-hunt/ "$HOME/.agents/skills/a1x-hunt/"
rsync -a --delete --delete-excluded --exclude-from=a1x-runtime/install-exclude.txt \
  a1x-runtime/ "$HOME/.agents/skills/a1x-runtime/"
```

If upgrading from V4, remove or archive the old discoverable phase-skill entrypoints (`a1x-recon`, `a1x-obligations`, `a1x-compose`, `a1x-execute`, `a1x-fuzz`, `a1x-solve`, `a1x-scale`, and `a1x-validate`) so Codex cannot route into the retired workflow.

Verify the runtime:

```bash
A1X_CLI="$HOME/.agents/skills/a1x-runtime/scripts/a1x"
"$A1X_CLI" --version
"$A1X_CLI" doctor
```

Restart Codex CLI after installing so the skill catalog reloads.

## Quick start

Open one fresh Codex CLI chat and invoke `$a1x` with a concrete authorized target:

```text
$a1x

Investigate the authorized Immunefi target at /absolute/path/to/protocol.
Program scope: <URL or supplied scope document>.
Deployment: <addresses>, chain <chain-id>, pinned block <number> with hash <0x...>.
RPC variable name: MAINNET_RPC_URL. Never print its value.

Use one Codex chat, visible built-in subagents only when justified,
local simulations and a pinned Anvil fork, stateful invariant fuzzing,
exact arithmetic search, clean replay, and exact in-scope impact validation.
```

That single skill invocation is the end-to-end entrypoint. The primary Codex session runs the lower-level runtime commands and invokes visible built-in subagents when the evidence checkpoints justify them; the operator does not invoke each phase separately.

The primary investigator creates or resumes an `audit-work/<campaign>/` directory outside the target build tree. Campaign initialization records state only: it does not start Anvil, a worker, or a model process. Forks and fuzzers are started visibly when an experiment requires them and are stopped before closure.

Detailed runtime examples are in the [V5 command guide](a1x-runtime/references/command-guide.md).

## Packages

| Package | Role |
|---|---|
| [`a1x`](a1x/SKILL.md) | Canonical end-to-end single-session hunt workflow |
| [`a1x-hunt`](a1x-hunt/SKILL.md) | Small compatibility alias that forwards to `$a1x` |
| [`a1x-runtime`](a1x-runtime/SKILL.md) | Deterministic ledger, fork, execution, evidence, replay, review-packet, and closure mechanics |

Supporting guides live in [`a1x/references/`](a1x/references/) and runtime mechanics in [`a1x-runtime/references/`](a1x-runtime/references/).

## Release validation

The V5 transformation was validated with:

- 52 unit, regression, ledger, integrity, process-guard, and recon-helper checks;
- 8 Foundry/Anvil integration checks;
- installed-surface smoke tests and skill-package validation;
- two independent fresh-context reviews.

The runtime rejects known model executables and opaque inline interpreter programs at its sealed execution boundary. This is a guardrail, not an operating-system sandbox: reviewable deterministic scripts remain part of the trusted local research surface.

## Research status

A1X is a research workflow, not evidence that any particular orchestration strategy outperforms expert auditing, fuzzing, or formal verification at matched cost. Effectiveness should be evaluated on independently adjudicated targets using unique root causes, time and cost to valid witnesses, false positives, partial-to-complete conversion, and coverage limitations.

The design is influenced by work on AI-assisted exploit generation, long-horizon attempt reuse, and recursive improvement. V5 retains selective evidence-driven synthesis while removing mandatory population schedules and external model-process orchestration.

---

<p align="center">
  Use A1X only within an explicitly authorized testing scope.
</p>
