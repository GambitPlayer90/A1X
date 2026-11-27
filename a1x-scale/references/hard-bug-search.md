# Adversarial chain search for difficult mechanisms

Hard vulnerabilities often do not appear as one obviously unsafe function. Search for a reachable composition in which individually plausible primitives establish a state that a later consumer interprets too strongly.

## Build chains, not warnings

For every suspicious primitive, repeatedly ask:

1. What new capability, state, identity, balance, denominator, or timing condition does this create?
2. Which other contract or lifecycle phase consumes it?
3. What additional attacker-controlled primitive turns it into a stronger state?
4. Which irreversible consumer realizes unauthorized value, authority, insolvency, or settlement failure?

Use the smallest applicable chain shape, not a mandatory template:

`attacker-controlled setup -> trusted state/provenance -> amplifier or lifecycle transition -> valuable consumer -> realization/settlement`

Two weak primitives may be enough. Do not force artificial chain length, but do not dismiss a non-terminal primitive because it is harmless in isolation.

## Flip the perspective

Re-run the analysis under adversarial ownership assumptions:

- attacker controls both sides of a trade, liquidation, auction, vote, loan, claim, or settlement;
- attacker deploys the pool, market, token, strategy, callback, receiver, module, proxy, or counterparty;
- every apparent user is one attacker-controlled identity unless independence is proved;
- an approved address may later acquire different code or an attacker-selected implementation;
- a factory-created or attested object proves only the exact fact the guard establishes, not economic legitimacy;
- a dormant, empty, thinly used, settled, deprecated, or emergency-mode subsystem may still custody value or authority;
- capital can be temporary, recycled, split across identities, recovered before execution, or sourced through a real flash facility.

If the current perspective says a lead is benign, change one ownership, timing, lifecycle, or consumer assumption and test again.

## Traverse contract and trust boundaries

Follow the complete call and authority graph through proxies, delegates, modules, routers, callbacks, token hooks, generic message systems, factories, governance executors, settlement contracts, and external strategies. Track both `msg.sender` and the identity a downstream contract observes.

Specifically test:

- direct calls to code intended only for delegatecall or proxy use;
- caller-selected targets, pools, strategies, recipients, hooks, assets, maturities, strikes, domains, or proofs;
- authentication established in one call and consumed or reused in another;
- generic primitives whose guarantee is weaker than the protocol's interpretation of it;
- approvals, roles, ownership, and configuration attached to an address rather than immutable code or economic identity;
- one module converting a limited capability into a broader role, queue action, upgrade, withdrawal, or asset transfer.

## Search time and state shape

Construct the entire reachable history, including setup transactions that precede the trigger. Explore:

- setup -> wait/block/epoch/maturity -> trigger -> claim/settle/withdraw;
- partial completion, cancellation, retry, replay, emergency, shutdown, and final-settlement modes;
- transient state reused within one transaction and persistent state left stale across transactions;
- empty, dust, one-sided, thin-supply, final-user, first-user, and near-threshold states;
- state prepared by earlier ordinary calls and consumed later under different assumptions.

Fork immediately before the earliest attacker-controlled prerequisite when validating reachability. Inheriting an already-captured or already-corrupted state proves consequence, not the attack path.

## Look for amplifiers

When one iteration produces tiny drift or only an intermediate capability, search:

- repetition until rounding or accounting error becomes material;
- round trips, cycles, split-versus-unsplit operations, and inverse operations;
- reserve compression before precision-sensitive math;
- self-trades, wash trades, multiple helper identities, or both sides of an auction;
- integer-width boundaries, normalization mismatches, duplicated credit, missing debit, stale checkpoints, and denominator collapse;
- a second consumer with greater value or weaker validation.

Use numerical search, fuzzing, or a solver for parameters and iteration counts. The investigator invents the mechanism; tools search the numbers and sequence variants.

### Precision-amplification closure

When a truncation or rounding primitive is inert at ordinary liquidity, do not optimize end-to-end token profit first. Preserve the best reachable state prefix and proceed in phases:

1. measure the local obligation directly: invariant drift, share/rate distortion, round-trip loss, debt/credit mismatch, or protocol-internal balance;
2. compress balances, reserves, supply, or denominators to the smallest source-faithful reachable state, including transient deficits and internal accounting;
3. mirror the exact deployed integer math in Solidity or integer/rational code, then search an outer compression/repetition count and an inner boundary amount separately;
4. treat arithmetic reverts as mapped holes rather than refutations; use bounded neighbor sweeps, digit trimming, and multiplicative backoff such as `9/10` when justified by observed convergence behavior;
5. repay transient obligations, inspect internal ledgers and claim tokens, then execute every withdrawal/redemption step needed to realize value and compute final net impact.

Balancer-style vaults, singleton managers, and flash-accounting systems can show zero external ERC-20 delta while the decisive signal lives in an internal balance or claim ledger. Always inspect and attempt the separate realization transition.

## Refute the strongest attack, not the first attempt

A failed first PoC is not a refutation. Before closing a high-consequence lead:

- repair harness and environment failures;
- test the strongest reachable state-construction prefix;
- vary attacker identities, ordering, transaction boundaries, amounts, repetition, and alternate consumers;
- identify the exact necessary edge that cannot be crossed;
- support unreachability with an executed negative discriminator or a mechanically anchored proof covering the real deployed configuration.

Ordinary-state success, intended-use reasoning, a revert on one parameter set, current lack of profit, or a guard whose semantic guarantee is weaker than the consumer's assumption remains inconclusive.

## Scale without collapse

Assign independent lanes to different perspective flips, missing edges, state shapes, consumers, and amplifiers. Preserve suspicious near-misses even when their present evidence is weaker. During aggregation, combine compatible prerequisites or pass one lane's reached state to another lane, but execute the child. Keep distinct or coarsely identified leads in the reserve; only exact artifact-bound and sequence-matched identities may alias.
