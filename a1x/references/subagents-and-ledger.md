# Visible subagents and durable ledger

The primary Codex chat owns the investigation. The runtime never invokes a model process.

## Ledger model

The canonical ledger is `audit-work/<campaign>/v5/ledger.json`. `ledger.tsv` and `brief.md` are deterministic projections carrying the ledger digest. Validate before use; rebuild stale projections explicitly. Writes use the campaign lock, expected record revisions, fsync, and same-filesystem atomic replacement.

Record kinds:

- `SCOPE`: target boundary, attacker model, exclusions, and exact eligible impacts.
- `OBL`: independently justified security property and predictions.
- `INV`: one investigation identity across lead, hypothesis, candidate, validated, refuted, or closed stages.
- `EXP`: experiment plan/observation, including fork/run/replay references.
- `FACT`: grounded source/configuration/execution fact, numerical bound, or scoped refutation.
- `TASK`: one bounded primary/subagent decision question.
- `SYN`: evidence-driven attack composition or investigation synthesis.

Immutable run, replay, trace, evidence, and artifact records stay outside the ledger and are referenced by ID/path/hash. Do not paste large logs into ledger records.

Every open item needs a next action. Refutations state their scope—configuration, amount range, sequence, consumer, or mechanism—so a narrow failure does not erase a broader lead. Keep the same `INV` ID when promoting; stage is not identity.

Use `ledger brief` to recover context, `ledger list` for targeted queries, and `ledger verify` after material changes. Updates require the current record revision to prevent silent overwrites.

## When to use a subagent

Delegate only when work is independently executable and can change a decision, such as:

- deployment or configuration verification;
- a fresh alternative mechanism from neutral observations;
- one numerical or reachability blocker;
- alternate-consumer tracing;
- property, harness, accounting, or impact challenge;
- independent replay/refutation.

Do not delegate dependent next steps, repetitive generic review, final judgment, or concurrent writes to shared mutable state. Prefer one or two focused subagents; add another only when it covers a materially different uncertainty. Set explicit time/resource/attempt bounds.

## Task packet

Create a ledger `TASK` before spawning. Its `data` should contain:

- `question`: one decision question;
- `inputs`: immutable record/artifact IDs and reproduction commands;
- `scope_constraints` and attacker model;
- `withheld`: preferred explanations omitted for independence, if any;
- support and refute predictions;
- permitted tools and mutable workspace/fork boundary;
- output contract;
- stop condition and budget;
- `cost`: low, medium, or high.

Announce the spawn in chat. Use the built-in collaboration mechanism in the current session; never a shell or `codex` command. Record the returned subagent/thread label in the task. Concurrent execution experiments must use isolated workspaces and separate disclosed Anvil forks; read-only analysis may share immutable artifacts.

If built-in subagents are unavailable or the session concurrency limit is reached, continue or queue the bounded question in the primary chat. Never fall back to an external Codex process.

Expected result:

- grounded facts with paths/IDs;
- assumptions and unknowns;
- observations separated from interpretation;
- scoped negative evidence and contradictions;
- smallest next discriminating experiment.

The primary investigator checks provenance, reruns critical commands, and closes or updates the task.

For candidate challenge, `review prepare-blind` creates a nonce-bound packet and fixed submission path. The reviewer must echo the packet digest, nonce, candidate, review, and thread label and provide reproduction commands and artifact references. The primary then uses `complete-in-session --attest-visible-subagent`. This is an explicit trust boundary: the runtime checks record consistency but cannot authenticate the Codex UI; `/subagents` is the operator-visible identity source.

## Synthesis

Synthesize only after new grounded information changes the unresolved question. A `SYN` record names input IDs, compatible facts, contradictions, discarded assumptions, and provenance. It must include:

- `revised_attempt`: a concrete executable or mechanically checkable next attempt;
- `next_discriminator`: the test that separates remaining explanations.

The runtime rejects synthesis lacking these fields. A vote, majority conclusion, or summary is not synthesis.

Use attack composition when executable transitions connect. Use investigation synthesis when different attempts establish complementary setup, bounds, settlement behavior, or refutations even though their call sequences cannot be concatenated.

Stop repeated delegation/synthesis when two bounded attempts add no material fact, constraint, state, or evidence improvement. Preserve the blocker and return control to the primary investigator.
