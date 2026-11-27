# Fork fidelity

## Pin and verify

Record chain ID, block number and hash, RPC variable name, target runtime hashes, implementation/module addresses, and relevant configuration at that block. Verify balances, roles, oracle state, supported assets, liquidity, pending queues/epochs, and dependency code needed by the path.

Use the repository's fork configuration where trustworthy. Never print RPC values. Keep archive-node limitations and missing historical state explicit.

## Historical versus current claims

A historical fork can prove the mechanism at that state. It does not establish current exposure. A current fork must still verify implementation and prerequisites. If state must be constructed through legitimate calls before exploitation, preserve that sequence rather than editing storage.

## Environment-sensitive behavior

Account for chain-specific opcodes/semantics, timestamp and block progression, base fee, precompiles, sequencer/oracle behavior, cross-domain messaging, token implementations, AMM/router versions, and forked external protocol state. Mock only a dependency that cannot be reproduced; state exactly which claim the mock prevents.

## Funding and liquidity

Fixture funds may let the attacker act but are not profit. If flash liquidity is part of reachability, use a faithful provider or measure the maximum required capital separately. Validate liquidation routes and slippage at the pinned state before normalizing value.
