---
name: a1x-recon
description: "Map a supplied Solidity/EVM target before exploit research: exact source-to-deployment identity, proxies and libraries, configuration, contracts and actors, assets and liabilities, lifecycle transitions, critical storage, external dependencies, and all relevant writers and consumers. Use at the start of an authorized hunt or whenever execution reveals an unknown actor, dependency, dispatch edge, or state writer. Exclude broad target discovery and generic scanner-only reconnaissance."
---

# Map deployment, value, and state

Build a model precise enough that later hypotheses refer to the code actually executed and the state actually trusted. Keep documentation claims separate from code and on-chain observations.

## Establish identity

Read [deployment-identity.md](references/deployment-identity.md). Pin repository commit, build configuration, compiler, chain, block, target addresses, runtime bytecode hashes, proxy type and implementation, linked libraries, and effective configuration. Resolve diamonds, beacons, clones, metamorphic patterns, and delegated modules when present.

Use existing RPC and explorer environment variables without exposing their values. Prefer the A1X host-side explorer retrieval adapter for verified source/ABI and the pinned credential-free prestate service for deployed reads. If verified source is unavailable or does not match runtime, follow [bytecode-recon.md](references/bytecode-recon.md) and label semantic confidence per component.

## Build the protocol model

Read [value-state-map.md](references/value-state-map.md). Trace:

- asset entry, custody, accounting transformation, claims, reservations, settlement, and exit;
- economic ownership versus token custody;
- units, scales, rounding direction, and conversions;
- untrusted users, privileged roles, keepers, relayers, oracles, bridges, governance, and external protocols;
- synchronous calls, callbacks, async messages, queues, epochs, delays, and failure recovery;
- honest user and protocol actions that can interleave with adversarial actions.

Draw critical flows in protocol terms before reading every function linearly.

## Map security-relevant state

For each critical variable or derived value, identify every writer, guard, reader, downstream consumer, and irreversible effect. Include direct, inherited, library, delegated, emergency, migration, callback, and asynchronous paths. Use compiler AST/call-graph support when useful, then manually resolve assembly, dynamic dispatch, proxy, and external edges.

Read [semantic-surface.md](references/semantic-surface.md) for the required surface pass.

## Rank boundaries

Prioritize boundaries where one component produces state another consumes under stronger assumptions:

- balances versus cached reserves or shares;
- claims versus backing or reservations;
- oracle observations versus settlement;
- local decimals versus normalized units;
- pending versus finalized state;
- role ownership versus operational authorization;
- source-domain success versus destination-domain accounting;
- pre-callback checks versus post-callback state.

## Output contract

Update `deployment.md`, `system-map.md`, and `coverage.md`. Return:

1. target/deployment mapping with confidence and unknowns;
2. asset/liability and lifecycle map;
3. actor and trust-boundary model;
4. critical writer/guard/consumer tables;
5. unresolved dispatch or data dependencies;
6. ranked boundaries for `$a1x-obligations`.

Do not label an observation a vulnerability during recon. State the evidence and the assumption it may challenge.
