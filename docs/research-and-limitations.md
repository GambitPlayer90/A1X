# Research design and current limitations

This document distinguishes implemented control machinery from semantic judgments and empirical claims. It describes v4.3.0; the README and diagrams do not upgrade its guarantees.

## Research question

Does protecting the continuation of an executed partial witness, while separately allocating pairwise composition and fresh exploration, improve independently validated vulnerability discovery under matched budgets?

The proposed mechanism addresses premature abandonment: a promising state prefix can require several experiments before it yields a complete security consequence. Closure preserves that prefix and its missing prerequisites. Composition and independent discovery remain separate uses of compute.

## Suggested experiment

Compare a documented A1-style sequential baseline, independent parallel workers, ordinary RSA, full A1X, A1X without protected closure, and A1X without K=2 composition. Hold the model, target information, tools, and budgets constant for controller ablations. Label an A1 reimplementation explicitly and document deviations.

Use separate development and held-out targets. The bundled tests and guidance include Balancer-shaped rounding/closure scenarios; related cases should not silently become an untouched held-out set. Keep reference exploits, incident transactions, answer-bearing reports, and adjudication material outside worker access. Pin pre-incident state for historical trials.

Record configuration, commit, model identifier, reasoning settings, trial/seed identifiers, target identity, chain/block, worker/coordinator/reviewer usage, time, execution resources, and environment failures. Repeat trials and report uncertainty. Report end-to-end success as well as any success conditional on a working environment.

An external adjudicator should verify the property, attacker capabilities, fidelity, reproduction, and impact. Separate successful trial records from distinct root causes and targets. False positives, stalled leads, and negative results belong in the evaluation.

## v4.3.0 integration notes

### Strict lane output schema

`a1x-runtime/scripts/schemas/lane-handoff.schema.json` declares the legacy `unresolved` field in `properties` but omits it from the top-level `required` list. This is valid ordinary JSON Schema but incompatible with strict structured-output providers that require every declared field to be required.

Before a large campaign, correct the schema for the intended provider and run a real Codex structured-output smoke test. Bundled fake-worker and metadata tests do not establish live API compatibility. This documentation update does not change the runtime schema.

### Lane execution evidence

The handoff validator derives evidence levels from declared execution fields and artifact-file presence. It does not independently attest their semantic contents against coordinator-owned EVM execution. Scheduling can therefore depend on incorrect declarations unless the investigator checks the underlying artifacts.

Bind scheduling evidence to recorded receipts and machine-checkable observations where practical, and retain independent validation. A handoff's E3/E4 classification is not an external result label. Final candidate/run gates have additional relationships and should be assessed separately.

### Review and replay

Blind review creates a sealed packet without the original rationale and starts a fresh process. The reviewer declares whether reproduction occurred. Qualification does not independently establish a new EVM replay or prevent inspection of the original investigation directory.

Clean replay checks source/input identity, mapped execution context, exit behavior, and an optional success regex. The security oracle and behavioral interpretation still require validation. A fresh process, valid hash, or passing command is not a proof of the vulnerability claim.

### Evaluation and accounting

`evaluation record` accepts supplied outcomes and costs; a validated-root-cause label can be recorded without an evidence ID. Summary counters aggregate trial records rather than deduplicating vulnerabilities. Use an independently adjudicated trial manifest for paper results.

Lane/run/time limits are not monetary or token spending ceilings. Collect actual usage, count coordinator/reviewer calls, and enforce any external spend cap separately.

### Backends and isolation

Tool discovery is not a working target-specific adapter. Fuzzers and solvers need suitable harnesses, encodings, independent oracles, and concrete replay. A capability probe does not establish that every backend works on a target.

Scale execution defaults to `danger-full-access` in v4.3.0. The README selects `workspace-write` explicitly. Use a disposable environment for unrestricted execution. Environment scrubbing, snapshots, namespace preflight, and RPC facades do not replace complete filesystem/network isolation.

### Composition and allocation

Compatibility ranking uses structural evidence and heuristics. Simultaneous reachability, actor powers, capital reuse, time, and transaction semantics remain questions for investigation and execution. The runtime does not implement formally certified state inclusion or prove exploit composition.

Mandatory initial and candidate-expansion lanes can be costly. Measure their contribution. The current defensible claim is that the policy is implemented and testable; improved detection, efficiency, and generalization require results.

## Evidence for public performance claims

- Frozen source and configuration for each condition.
- A contamination-aware split and documented target preparation.
- Complete trial accounting, including setup and infrastructure failures.
- Independent validity/impact adjudication and clean reproductions.
- Repeated trials, uncertainty estimates, and controller ablations.
- Released replay artifacts where target permissions permit.

The [artifact contract](../a1x-runtime/references/artifact-contract.md) defines mechanical evidence ceilings.
