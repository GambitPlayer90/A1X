# Bytecode-first reconnaissance

Use bytecode-first work when source is missing, mismatched, incomplete, or proxy dispatch remains unresolved. Keep inferred semantics below source-confirmed confidence.

## Recovery sequence

1. Capture runtime and creation bytecode, code hash, deployment transaction, creator, block, and constructor tail when available.
2. Strip and decode compiler metadata; identify compiler family/version range and linked-library placeholders.
3. Resolve proxy, clone, beacon, diamond, and delegatecall targets from bytecode patterns, storage, events, and live read-only calls.
4. Recover selectors from dispatch and lookup databases or verified interacting ABIs; label collisions and uncertain signatures.
5. Disassemble and build control-flow/basic-block maps. Identify storage reads/writes, external calls, delegatecalls, create/create2, selfdestruct semantics, and revert branches.
6. Infer storage slots and layouts from access patterns, proxy standards, constructor/initializer calls, events, public getter behavior, and state diffs.
7. Use decompilation only as an aid. Cross-check every security-relevant expression against opcodes and concrete calls.
8. Reconstruct minimal interfaces for observed selectors and validate them with `eth_call` or local-fork execution.

## Confidence

Label each fact `opcode-direct`, `concrete-observed`, `cross-source corroborated`, `decompiler-inferred`, or `unknown`. Do not reason from a decompiler variable name as if it were source intent.

## Evidence limits

Bytecode can support concrete reachability and state-change claims. Source-level intent, names, types, signedness, struct boundaries, and high-level arithmetic may remain uncertain. Narrow the obligation and candidate claim accordingly. If an unknown expression is causal, resolve it with concrete boundary tests or a faithful symbolic model before promotion.
