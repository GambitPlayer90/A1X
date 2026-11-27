---
name: a1x-compose
description: Compose a code-grounded smart contract vulnerability hypothesis into the shortest reachable multi-call, multi-actor, callback, or multi-transaction state transition sequence. Use when a mapped writer can establish weaker state than a valuable consumer assumes and the hunt must prove prerequisites, ordering, capital, time, roles, and honest-user interleavings. Exclude speculative long chains without a protocol obligation.
---

# Compose reachable adversarial state transitions

Convert a specific obligation contradiction into an executable path. A valid composition explains how every prerequisite is established by the claimed actor under real EVM and protocol semantics.

## Build the transition ledger

Read [transition-ledger.md](references/transition-ledger.md). For each edge record:

- actor and call context (`msg.sender`, `tx.origin` only if relevant, delegated identity);
- starting state and required balances/allowances/roles;
- call, parameters, value, and target;
- guards crossed and external calls made;
- storage, balance, liability, and authorization deltas;
- callbacks or reentrant opportunities;
- time/block/epoch/domain change;
- transaction boundary and revert/atomicity behavior;
- security-relevant state fingerprint after the edge.

Every edge must cite code or a verified external behavior.

## Compose from consumer backwards

1. Start at the valuable consumer or terminal impact.
2. Enumerate the exact conditions it trusts.
3. Trace each condition to all writers.
4. Select the weakest attacker-reachable writer or lifecycle transition.
5. Work backwards until every prerequisite is satisfiable from the pinned starting state.
6. Then replay the sequence forward and identify honest actions or callbacks that may intervene.

Prefer the shortest causal witness. Add complexity only when a prerequisite requires it.

Then perform an adversarial extension pass. Treat every reached capability as a possible prefix, not a final severity: ask which other contract, lifecycle phase, generic message/attestation layer, governance executor, callback, or settlement consumer trusts it. Re-run the path assuming the attacker controls both sides, all apparent users, and any permissionless object or callback. Search setup -> delay/maturity -> trigger -> settlement histories, within-transaction transient reuse, repeatable cycles, reserve compression, and alternate consumers. Do not force long chains, but do not analyze a cross-contract primitive in isolation.

## Model actors, callbacks, and time

Read [actors-and-interleavings.md](references/actors-and-interleavings.md) whenever the path uses multiple identities, helper contracts, callbacks, honest users, keepers, time, or asynchronous settlement. Treat contract deployment and custom callback logic as first-class attacker actions.

## Maintain an execution frontier

Read [frontier-search.md](references/frontier-search.md) when several prefixes or orderings are plausible. Keep replayable prefixes with semantic state fingerprints. Retain a prefix because it reaches a relevant state, not because it is longer or has higher code coverage.

## Check feasibility before execution

Resolve:

- availability and source of capital;
- approvals, tokens, decimals, transfer behavior, and liquidity;
- actual role/permission ownership;
- timestamp/block advancement and who can trigger it;
- oracle update/freshness and dependency configuration;
- atomic versus multi-transaction survivability;
- whether front-running, ordering, or honest participation is required;
- whether any step assumes a cheatcode unavailable to the stated actor.

Route difficult parameter constraints to `$a1x-solve`, broad state search to `$a1x-fuzz`, and concrete candidate tests to `$a1x-execute`.

## Output contract

Update the hypothesis file with:

1. minimal transition sequence and alternate branches;
2. actor/capital/time/permission requirements;
3. replayable state prefix or exact unresolved edge;
4. supporting and refuting execution predictions;
5. chosen next tool and why it is discriminating.

Do not claim reachability if a state was produced only by arbitrary storage mutation or privileged impersonation.
