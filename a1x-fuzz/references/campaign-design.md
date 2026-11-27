# Fuzz campaign design

## Property quality

The property must be sensitive to the suspected mechanism and independent enough to catch an implementation error. State units, actors, time boundary, allowed fees/loss, and exceptions.

Reject properties that:

- merely assert no revert;
- duplicate the target's return value or formula;
- can never be reached because handlers reject all interesting inputs;
- pass because the fixture has no value or no external dependency;
- ignore debt, fees, helper addresses, or pending claims;
- depend on global profit while the target impact is authorization or liveness.

## Input and state generation

Seed dictionaries with observed constants, boundaries, decimals, caps, fee denominators, timestamps, reserve ratios, role addresses, and prior near-miss parameters. Bias around zero, one, max/min, threshold ±1, rounding boundaries, and current on-chain values without excluding broad mutation.

Model sequence length, actor switches, asset switches, callback modes, time/block advances, oracle updates, and honest operations. Do not make every action succeed; record rejected-action ratios and avoid campaigns dominated by precondition reverts.

## Waypoints

Track semantic progress such as new claim states, backing drift, role changes, crossed guards, changed reserve/balance relation, debt/collateral boundary, pending/final transitions, and valuable external calls. Branch coverage supplements these signals.

## Negative campaigns

When no counterexample appears, report tool/version/config, duration/executions, sequence bounds, reached waypoints, code/semantic coverage, rejected-action rate, and environmental limitations. Do not say the obligation is proven.
