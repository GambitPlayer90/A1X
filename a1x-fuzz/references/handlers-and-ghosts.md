# Handlers and independent ghosts

## Handler design

Each action should correspond to a valid protocol transition with bounded, meaningful parameters. Select actors explicitly. Use helper contracts for callbacks and contract-only behavior. Include approval/funding preparation only when the real actor can perform it.

Keep preconditions permissive enough to expose edge states. Prefer clamping or choosing from valid resources over `assume` statements that discard most inputs. Track action invocation, success, revert reason class, and semantic state change.

## Ghost state

Maintain independent accounting for:

- funded assets and withdrawals;
- issued/burned shares or claims;
- debt principal, accrued interest, repayment, and bad debt;
- reserved versus available liquidity;
- reward entitlement and checkpoints;
- processed nonces/messages/epochs;
- attacker group capital and liabilities.

Use conservation and lifecycle relations rather than mirroring internal implementation variables one-for-one.

## Stateful adversaries

Include actor rotation, repeated actions, zero and dust amounts, max bounds, callback reentry, token-behavior variants, time/epoch movement, partial operations, cancellation/retry, and honest-user interleavings when relevant. Do not add behaviors unrelated to the selected obligation merely to inflate exploration.

## Counterexample handoff

Minimize sequence and inputs while preserving the same property violation and causal mechanism. Convert the final sequence into a deterministic test with explicit assertions and a control. Preserve the raw fuzzer replay for independent verification.
