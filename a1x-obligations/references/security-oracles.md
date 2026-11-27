# Security oracle design

## Choose the property first

An oracle should distinguish a vulnerability from intended operation. Examples:

- `assets_after + permitted_loss >= liabilities_after`;
- an unprivileged actor cannot cause issuance or transfer without the corresponding authorized debit;
- one claim cannot settle more than once;
- sum of user/protocol value after fees cannot exceed funded value under stated assumptions;
- a legitimate operation remains executable within a bounded adversarial state;
- destination credit cannot exceed finalized source debit after decimal normalization.

Define exact units and tolerated rounding.

## Economic accounting

Measure all attacker-controlled addresses and helper contracts. Include initial capital, borrowed principal, fees, debt, locked collateral, unrealized positions, and tokens that cannot be liquidated. Measure victim/protocol loss or liability increase independently. Separate gross extraction, net profit, and exposed value.

Do not treat prefunded harness assets as profit. Do not count ordinary arbitrage or unrelated dust. If value must be normalized, record routes, liquidity, slippage, and price source.

## Authorization and liveness

Profit may be irrelevant. For authorization, prove the actor lacks the required authority under the actual call context. For liveness, demonstrate a reachable persistent state that blocks a valuable legitimate action, identify who can recover it, and quantify cost/duration rather than asserting a theoretical revert.

## Differential and metamorphic checks

Where possible compare:

- exploit path versus the same path with the suspected enabling step removed;
- vulnerable behavior versus an intended/locally corrected relation;
- equivalent operation orderings that should produce the same economic state;
- actor identities or token types that should not change the outcome.

A passing assertion is only as strong as its independence from the implementation under test.
