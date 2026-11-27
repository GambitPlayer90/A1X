---
name: a1x-execute
description: Build, run, and diagnose faithful Foundry/Anvil tests for a specific smart contract vulnerability hypothesis against local code or a pinned EVM fork. Use to validate reachable multi-actor sequences, callbacks, time-dependent flows, accounting violations, and economic impact with traces and controls. Exclude live-chain transactions, source modification disguised as a harness, and broad unfocused fuzzing.
---

# Execute a faithful vulnerability test

Treat execution as a discriminating scientific test, not a code-generation contest. Preserve original target code and separate environment setup from adversarial actions.

## Plan before running

Write the supporting and refuting predictions, target identity, fork block, actor model, prerequisites, security oracle, command, and relevant inputs before observing the result. Use `$a1x-runtime` to seal the plan and declared inputs. Use a new run ID after changing any of these.

Read [fork-fidelity.md](references/fork-fidelity.md) for forked deployments, [harness-integrity.md](references/harness-integrity.md) for all tests, and [untrusted-execution.md](references/untrusted-execution.md) before running target-controlled build or test code.

## Construct the harness

- Keep target source unchanged. Use separate test, attacker, helper, mock, or adapter files.
- Reuse the repository's native framework and build configuration only after inspecting its scripts, hooks, plugins, dependency sources, and FFI/network behavior.
- Reproduce the claimed actor using pranks only to select an identity actually available to that actor.
- Use deal/storage writes/role impersonation only for clearly labeled fixture setup, never as an exploit step or source of measured profit.
- Support multiple attacker identities, deployed callback contracts, multiple transactions, block/time advancement, and honest actors when the composed path requires them.
- Assert the protocol-specific property and measure both attacker group and harmed party/protocol.
- For vault, singleton, flash-accounting, or claim-token systems, inspect protocol-internal balances/credits as well as ERC-20 balances and include every separate withdraw, redeem, burn, settle, or repay transition needed to realize impact.
- Write the support and causal-control entry points before sealing either run so their declared input digests remain identical.

## Execute and inspect

Start with the narrowest deterministic test and sufficient verbosity to observe the relevant calls and state changes. Execute it through `$a1x-runtime` so the replay-exact **redacted** command template, exit status, bounded logs, input hashes, target/harness identity, and process-group outcome are retained. Replace secret expansions with exact `@env:NAME` arguments.

Run deterministic trace analysis for storage writes, external-call boundaries, reverted or overwritten transient values, revert selectors and operand context, and balance/accounting residuals. Treat a transient window as a waypoint inside the original top-level transaction; never resume it as a new transaction. Preserve even one-unit residuals or internal-ledger deltas as phase-local signals, then test whether repetition or a downstream consumer turns them into a security violation.

Read [trace-diagnosis.md](references/trace-diagnosis.md) when the attempt fails or behaves unexpectedly. Classify the failure before editing code.

## Iterate with execution feedback

Revise the contract model or attack path based on observed facts. Keep useful earlier attempts. Compilation repairs and interface corrections are engineering work; record them separately from research progress. Do not repeatedly mutate amounts or swap order without a mechanism explaining why the change should cross a relevant boundary. Record witness progress separately from information progress such as a narrowed feasible interval, mapped revert region, disproved assumption, or newly observed dependency.

If the uncertainty is a large state/sequence space, route to `$a1x-fuzz`. If it is a numeric, branch, or symbolic constraint, route to `$a1x-solve`. For reserve compression, repeated precision drift, or revert-heavy iterative AMM math, preserve the reached prefix and use `$a1x-solve`'s staged fixed-point search: phase-local invariant/internal-credit oracle, exact integer mirror, nested outer repetition/compression and inner boundary search, mapped revert holes, bounded backoff, then settlement and realization. If execution exposes an unknown writer/dependency, return to `$a1x-recon`.

## Demonstration gate

A candidate is locally demonstrated only when:

1. the exact path succeeds from a representative starting state;
2. the claimed security property is violated;
3. actor capabilities and prerequisites match the claim;
4. measured impact excludes fixture funds, debt, and unrelated arbitrage;
5. the suspected enabling mechanism is supported by a causal control;
6. relevant input and output artifacts are preserved.

Route demonstrated candidates to `$a1x-validate` for clean replay and claim calibration.

For protected continuation, first replay the parent assertions from its immutable packet. Perform the attempted extension in a distinct observed run, replay that run, and attach both receipts. Parent replay alone cannot establish extension progress.

## Output contract

Annotate the immutable runtime run with raw observation, interpretation, property outcome, impact, and limitations; update the hypothesis with the next action. Never report a reverting or locally patched demonstration as deployed exploitability.
