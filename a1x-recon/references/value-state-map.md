# Value, liability, and lifecycle mapping

## Balance sheet

For each asset or claim, record:

| Item | Questions |
| --- | --- |
| Custody | Which address holds the asset at each stage? |
| Economic owner | Who is entitled to it and under what conditions? |
| Liability | Which variable or token represents the obligation? |
| Backing | Which assets or future flows support the claim? |
| Unit | Token units, shares, normalized precision, price units, time basis? |
| Reservation | Is value reserved for pending claims or still reusable? |
| Finality | Which event makes the transition irreversible? |
| Exit | Which consumer releases value, burns claims, or settles debt? |

Reconcile assets, liabilities, and outstanding claims at each lifecycle boundary. Track protocol fees and rounding dust separately.

## Lifecycle state machine

Map valid states and transitions for deposits, borrowing, repayment, liquidation, withdrawals, redemptions, rewards, orders, messages, proposals, and upgrades as applicable. Include cancellation, timeout, partial fill, retry, failure callback, emergency, and migration paths.

For each transition record actor, guard, state read, state write, external call, emitted event, value movement, and later consumer. Mark transitions that can span transactions or domains.

## Dependencies and interleavings

Map token behavior, AMMs, lending markets, price sources, callbacks, hooks, keepers, governance, relayers, bridges, and account-abstraction components. Ask which honest action can occur between attacker steps and whether the protocol assumes it cannot.

## State fingerprints

For execution/search, define a compact semantic fingerprint: critical balances, liabilities, reserves, shares, debt, claim counts, role holders, timestamps/epochs, oracle observations, and pending/finalized flags. Use it to compare reached states; raw storage hashes alone obscure meaning.
