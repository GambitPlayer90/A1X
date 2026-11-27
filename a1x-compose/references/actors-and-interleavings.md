# Actors, callbacks, and interleavings

## Actor model

Distinguish:

- unprivileged attacker EOA;
- attacker-deployed contracts and multiple controlled addresses;
- honest users whose legitimate actions may be induced or ordered;
- keepers, liquidators, solvers, relayers, sequencers, and validators;
- governance/admin/emergency actors;
- external protocols and token contracts;
- source- and destination-domain identities.

State exactly which capabilities each actor has. “Anyone” does not imply the same call context through a router, forwarder, proxy, or callback.

## Callback composition

For every external call, identify caller/callee state before the call, callback selectors available, functions reachable during the callback, and state used after return. Explore cross-function and cross-contract reentrancy, token hooks, flash callbacks, receiver hooks, and nested protocol composition. Do not assume a reentrancy guard covers sibling contracts or functions.

## Honest interleavings

Consider deposits, withdrawals, oracle updates, liquidations, queue processing, governance actions, reward updates, and bridge relays between attacker steps. An attack may depend on an honest action, but record whether the attacker can induce, predict, front-run, or merely hope for it.

## Time and blocks

Separate timestamp, block number, epoch counters, oracle periods, cooldowns, and cross-domain finality. Local warp/roll may establish a test environment, but the path is reachable only if the same progression can occur under stated real-world timing and actor assumptions.
