# Semantic surface pass

## Required questions

For each critical flow, answer:

1. Who can initiate it directly and through another contract?
2. Which functions write the state its terminal consumer trusts?
3. Are checks applied to the same actor, asset, unit, epoch, domain, and snapshot later consumed?
4. Can a callback or external token hook change checked state before it is used?
5. Can an emergency, migration, admin, or asynchronous path establish a state normal paths cannot?
6. Can state be reset, deleted, reused, replayed, or finalized twice?
7. Does failure leave partial state or consume a one-time right?
8. Can two legitimate operations compose into an illegitimate result?

## Code features requiring explicit resolution

- inheritance and overrides;
- delegatecall and dynamic target selection;
- inline assembly and low-level calls;
- storage packing and upgrade-layout changes;
- ERC token callbacks, ERC-777 hooks, ERC-1155/721 receivers, flash callbacks;
- fallback/receive and proxy fallback paths;
- permit/signature domain separation and nonce writers;
- multicall, batching, meta-transactions, and trusted forwarders;
- cross-chain message origin, replay, ordering, and failure handling;
- selfdestruct/create2/metamorphic assumptions where chain semantics permit them.

Use static tools only to answer concrete mapping questions. A clean scan does not close a semantic boundary.
