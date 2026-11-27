# Numeric and economic search

## Define the objective

Use protocol-native security impact first. For profit, define net value over the attacker-controlled group after repayment, fees, gas if material, slippage, locked collateral, residual debt, and liquidatability. Keep victim/protocol loss as an independent measurement.

## Bound the space

Derive limits from balances, reserves, caps, collateral, borrow limits, share supply, oracle ranges, queue sizes, and integer widths. Search in native integer units. Include threshold ±1 and scale-boundary candidates.

## Discontinuities

Expect cliffs from:

- integer rounding and casts;
- branch thresholds and reverts;
- AMM tick/fee/liquidity changes;
- min/max/cap operations;
- token transfer fees and callbacks;
- liquidation eligibility;
- discrete loop counts and batch sizes.

Sample across regions before assuming smoothness. Preserve several local optima if different mechanisms or paths produce them.

## Search phases

1. Coarse bounded exploration to identify feasible regions.
2. Local refinement within each region using a method whose assumptions hold.
3. Boundary and neighbor checks.
4. Concrete EVM replay for every leading candidate.
5. Causal control and capital sensitivity analysis.

When a state-construction prefix and a per-step integer cliff interact, search them as nested phases rather than one flat objective. Hold a replayable prefix fixed, map inner revert holes and rounding neighbors, then vary outer compression/repetition parameters. Record invariant/share-rate/internal-credit deltas even when external profit is not yet realized.

The goal during detection is a convincing witness, not necessarily global maximum profit. Optimize further only when it resolves impact or reachability.
