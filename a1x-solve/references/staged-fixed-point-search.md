# Staged fixed-point and revert-tolerant search

Use this pattern when a rounding/accounting primitive is real but ordinary-liquidity tests show zero profit, iterative math reverts near the interesting boundary, or the exploit requires a prepared state before tiny drift becomes material.

## Preserve the prefix

Represent the witness as independently replayable phases:

1. prepare the state using attacker-reachable calls;
2. trigger one precision-sensitive transition;
3. persist or accumulate the local property violation;
4. settle transient debt or restore required balances;
5. realize protocol-internal credit or custody value;
6. measure final impact.

Once a prefix is reached, snapshot it and search only the first unresolved phase. Do not repeatedly rebuild earlier phases while changing the inner numeric condition.

## Measure the local oracle first

Do not wait for external ERC-20 profit to reveal the primitive. Measure the phase-local obligation directly, for example:

- invariant `D` or share-rate monotonicity;
- round-trip normalized value;
- raw-versus-scaled reserve consistency;
- protocol-internal credit, claim, or debt;
- a crossed authorization or settlement boundary.

Attach the exact before/after trace to the witness phase. External profit becomes relevant when the realization phase is reached.

## Mirror exact integer semantics

Build the smallest source-faithful Solidity helper or independent Python integer model that reproduces the target's bit widths, operation order, rounding direction, fee order, casts, and revert conditions. Compare intermediate values against the EVM at known inputs before searching.

For iterative Newton-style math or other discontinuous paths:

1. sweep coarse state regions first;
2. search the inner amount boundary at threshold neighbors;
3. treat reverts as mapped holes, not global refutations;
4. use bounded backoff such as `x := floor(9*x/10)` or significant-digit trimming only when the trace identifies the failing arithmetic region;
5. preserve several feasible boundary candidates;
6. search outer reserve-compression depth and repetition count around those candidates;
7. replay every survivor through the original EVM code.

This is a nested search: outer state-prefix/repetition parameters, inner per-step integer boundary parameters. Halmos/Z3 may solve a narrowed exact predicate, but do not encode an entire iterative AMM plus external state when concrete adaptive search is more faithful.

## Close settlement and internal ledgers

After local drift is demonstrated, inspect every accounting surface through which it can persist or be realized: Vault internal balances, singleton claims, ERC-6909 balances, transient flash accounting, queued withdrawals, shares, debt, and refund paths. A zero external balance delta does not refute an exploit while value remains as attacker-controlled internal credit.

The final replay must start from the pinned pre-state, construct the prefix through available actor actions, settle required temporary obligations, withdraw or otherwise realize the claimed consequence, and reconcile attacker-group net value and victim/protocol loss independently.
