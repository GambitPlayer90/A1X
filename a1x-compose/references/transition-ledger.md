# Transition ledger

Use one row per semantic action, splitting callbacks and asynchronous finalization into separate rows.

| Field | Required content |
| --- | --- |
| Step | Stable identifier and transaction number |
| Actor | EOA/contract/role and actual call identity |
| Preconditions | State, balances, approvals, roles, time, messages |
| Action | Target, selector, parameters, value |
| Guards | Conditions crossed and their snapshot |
| Effects | Storage, balances, liabilities, claims, roles |
| External boundary | Call/callback/message and reversion behavior |
| Fingerprint | Security-relevant state after the step |
| Evidence | Code location or observed trace |

## Causal minimization

After a working path exists, remove steps one at a time. A step is causal if removing or neutralizing it eliminates the property violation while preserving the rest of the environment. Keep convenience steps separate from enabling steps.

## Atomicity

For each transaction boundary ask which state becomes observable, which actor can intervene, and whether a failure rolls back all relevant components. Cross-domain and asynchronous systems may commit source and destination state independently; model each finality boundary explicitly.
