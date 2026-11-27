# Deployment identity and provenance

## Pin the subject

Record repository commit, submodule/dependency locks, build profile, compiler version and settings, chain ID, block number/hash, target address, runtime bytecode hash, storage implementation slots, and resolved implementation/module addresses.

For proxies, inspect standard and nonstandard slots, admin/beacon ownership, initializer state, upgrade history when relevant, and effective implementation at the pinned block. For diamonds, map selectors to facets. For clones, resolve the template and immutable arguments. For linked libraries and delegatecall routers, map runtime targets and storage ownership.

## Establish correspondence

Classify each component:

- exact verified match;
- reproducibly compiled match;
- high-confidence source with metadata mismatch;
- partial source or unresolved library;
- bytecode-only;
- source-only with deployment unverified.

Never silently substitute a nearby tag, upstream repository, or current implementation for the pinned runtime. Semantic-diff forks and upgrades at security-relevant boundaries.

## Configuration is code

Capture effective roles, owners, fee parameters, caps, pause state, supported assets, decimals, oracle/router endpoints, bridge peers, epoch state, implementation addresses, and dependency versions. Distinguish constructor inputs, initializer inputs, later governance changes, and transient state.

## RPC hygiene

Use variable names already exported in the shell. Discover names only. Do not run commands that print all environment values, shell startup files containing secrets, expanded RPC URLs, or API keys. Keep secrets out of command transcripts and campaign files. If a command would expose a secret in logged argv, prefer a tool/config mechanism that resolves the environment variable internally.
