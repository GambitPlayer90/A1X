# Hard-bug search operators

These operators generalize recurring difficult incidents. Apply them conditionally from the target's semantics; never search for a named historical exploit or assume the same root cause.

## Transient versus settled state

At every callback, unlock, flash-accounting, batch, claim, liquidation, queue, and finalize boundary, compare what consumers can observe before and after settlement. Ask whether a guard executes while debt, liability, mode, reserve, or authorization state is temporarily absent or stale. Test nested callbacks and operations that are individually valid but compose inside the transient window.

Properties:

- settlement closes every temporary credit/debit;
- guards use the state that will exist after the enclosing operation completes;
- transient authentication is consumed, scoped, and rechecked per call;
- failures/reverts cannot leave reusable authorization or partial accounting.

## Internal ledgers and realization

Track protocol-internal balances, claims, shares, credit, debt, per-user/group buckets, and fee-growth separately from ERC-20 balances. Look for double counting, gross-versus-net confusion, cyclic paths, stale checkpoints, shared-pool payout, or a writer updating one representation but not another.

An internal discrepancy is a waypoint, not yet impact. Find the exact consumer and realization transition—withdraw, claim, swap, redeem, liquidation, settlement, migration, or upgrade—that converts it into an eligible consequence.

## Repetition and exact rounding

Test whether splitting one logically equivalent action into many small actions changes conserved quantities, active liquidity, shares, supply, debt, fees, or checkpoints. Exercise values that round to zero on one leg while a state transition still occurs elsewhere. Compare one-shot versus partitioned execution and forward versus reverse operation.

Mirror exact integer math. Measure local drift after each step. Preserve revert holes and search around them. Check whether repeated dust, zero-fee updates, ceiling/floor asymmetry, width truncation, or stale denominators can be amplified with permissionless capital.

## State compression and boundary creation

Ask whether an attacker can first move the protocol into an unusual but permitted region—low reserves, extreme price/tick, zero supply, high utilization, empty debt, expired lifecycle, sparse liquidity, or uninitialized checkpoint—and only then exercise ordinary logic. Search the preparation transition separately from the consumer transition.

Use an outer search for repetitions/state compression and an inner search for the exact amount or boundary. Do not reject a mechanism because the first amount reverts.

## Attacker-supplied components and provenance

For every accepted token, pool, market, oracle, router, executor, source, callback, recipient, module, proof tuple, or implementation, trace how its identity and behavior are authenticated. Test attacker-deployed but interface-conforming objects. Separate caller authentication from downstream provenance and from the object whose state is trusted.

## Cycles, aliases, and double-entry mismatches

Test paths whose start and end assets/accounts are equal, repeated elements, self-transfers, aliased tokens, multiple share classes, same asset on input/output, or logically identical identifiers encoded differently. Verify the ledger nets changes once and duplicate/replay guards bind every security-relevant field.

## Lifecycle and time composition

Exercise create/initialize/migrate/pause/unpause/upgrade/settle/cancel/release/claim/reopen boundaries, including one-block and one-epoch transitions. Look for state copied without checkpoints, counters decremented twice, delayed actions becoming permissionless, and old signatures/approvals/capabilities remaining usable after lifecycle change.

## Authority acquisition and downstream consumers

Do not stop at “requires privilege” if public actions can acquire that privilege: governance weight, ownership, role membership, module enablement, queue control, approved spender status, borrower identity, or upgrade authority. Model acquisition cost and timing, then trace every valuable consumer. Reject only capabilities unavailable under the declared attacker model.

## Composition challenge

For each promising mechanism, attempt at least the applicable forms:

- sequential transactions with persistent state;
- nested callback/reentrancy composition;
- temporal/lifecycle composition across block/epoch/delay;
- multi-actor or self-controlled counterparty composition;
- attacker-created component composition;
- cross-contract consumer substitution;
- cross-domain message/replay/failure composition.

The goal is not to execute every form. Record why each is applicable, disproven, blocked, or not applicable.

## Required causal challenge

For a strong result, vary the proposed cause while holding setup constant: one-shot versus split action, cyclic versus non-cyclic path, nested versus settled timing, real versus attacker-supplied component, boundary versus neighboring amount, or enabled versus disabled consumer. This is often more informative than another unconstrained fuzz campaign.
