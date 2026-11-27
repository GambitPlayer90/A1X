# Semantic frontier search

## Nodes and edges

A node is a replayable protocol state plus the transaction prefix that reaches it. An edge is a valid actor action, callback, honest interleaving, or time/domain transition. Fingerprint nodes using security-relevant balances, liabilities, claims, reserves, roles, epochs, and pending/final flags.

## Waypoints

Retain prefixes that:

- reach a new writer or valuable consumer;
- cross a guard relevant to the obligation;
- create measurable accounting drift;
- change authority or lifecycle status;
- satisfy a previously unresolved prerequisite;
- reduce the remaining constraint to a smaller numeric/search problem.

Coverage alone is secondary. Discard equivalent prefixes under the semantic fingerprint unless transaction history itself matters.

## Search strategy

Use a bounded beam/frontier first. Expand high-information prefixes and retain diverse mechanisms. Use tree-search machinery only when actions and intermediate values are meaningful and reproducible. Generic revert/no-profit is a poor value signal.

Store supporting and refuting observations. A prefix that disproves a branch can be more valuable than a longer near-miss.
