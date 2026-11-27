# Protocol-specific challenge families

Read only the sections relevant to the target.

## Shares, vaults, staking, and rewards

- Assets, shares, and claims remain mutually consistent across deposits, donations, losses, fee minting, queues, rebases, and partial settlement.
- Preview and execution use compatible snapshots and rounding directions.
- Late entrants cannot capture previously accrued value; exiting users cannot retain future entitlement.
- Reward indexes and user checkpoints advance exactly once under transfer, mint, burn, delegation, and zero-balance transitions.

## Lending and liquidation

- Debt, interest, collateral, ceilings, and isolation accounting use consistent units and update on every mutation path.
- Liquidation cannot create value through stale debt, rounding, bad-debt socialization, or callback ordering.
- Repay, refinance, migration, and write-off do not reset risk accounting without extinguishing the corresponding liability.

## AMMs, pricing, and token behavior

- Cached reserves, actual balances, invariant parameters, fees, and normalized decimals remain aligned.
- A price consumer resists manipulable liquidity and uses the intended market, time window, and freshness.
- Fee-on-transfer, rebasing, reflection, callback, non-returning, reverting, and decimal-extreme tokens cannot create unaccounted value.

## Settlement, orders, and asynchronous flows

- A claim is consumed once and only after the corresponding value movement succeeds.
- Cancellation, partial fill, retry, timeout, and failure callbacks conserve rights and liabilities.
- Pending and finalized state cannot be confused across epochs, batches, or domains.

## Bridges and cross-domain messaging

- Source lock/burn corresponds exactly to destination mint/release in asset, amount, decimals, sender, recipient, domain, nonce, and finality.
- Failure and retry cannot mint twice, strand value through inconsistent state, or consume replay protection before successful settlement.
- Message verification binds all security-relevant metadata and the currently trusted peer.

## Governance, roles, and upgrades

- Proposal, veto, quorum, timelock, execution, and cancellation use the intended voting power snapshot and cannot be transiently diluted or inflated.
- Role transfer, renounce, initializer, upgrade, and emergency paths preserve the authority model.
- Upgrade storage and module routing cannot reinterpret or bypass existing obligations.

## Signatures and authorization

- The signed payload binds chain, contract, action, asset, amount, recipient, deadline, nonce, and role as required.
- Nonces are scoped and consumed at the correct success boundary.
- Alternate encodings, malleability, contract signatures, batch ordering, and delegated callers do not widen authorization.
