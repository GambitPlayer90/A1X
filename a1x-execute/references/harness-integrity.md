# Harness integrity

## Setup/action boundary

Label fixture setup and attack execution explicitly. Setup may select the fork, instantiate local actors, seed only stated initial capital, and reproduce an otherwise external prerequisite. The attack phase must use externally reachable behavior available to the claimed actor.

Reject demonstrations that depend on:

- writing target or dependency storage to create the vulnerable condition;
- impersonating a privileged account without a demonstrated privilege-escalation path;
- minting, dealing, or gifting assets counted as extraction;
- changing target source, compiler semantics, or production configuration;
- replacing a difficult external dependency with a cooperative mock while claiming full applicability;
- asserting only the test's own calculations instead of target state/value.

## Economic measurement

Snapshot all attacker-controlled addresses, protocol/victim balances, liabilities, borrowed principal, fees, locked value, and residual positions. Normalize only assets with a demonstrated exit. Report gross extraction, net profit, and victim/protocol loss separately.

## Liveness and authorization

For liveness, demonstrate persistence, affected legitimate operation, recovery authority, and bounded cost/duration. For authorization, verify the actual caller context and role state before the action.

## Negative controls

Remove or neutralize the suspected enabling step while keeping the environment and remaining sequence comparable. A control that changes several prerequisites cannot isolate causality.
