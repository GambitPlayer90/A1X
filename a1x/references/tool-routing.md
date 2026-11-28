# Tool routing

Choose tools by the unresolved question. Do not run a scanner suite for its own sake, and do not treat tool output as a vulnerability claim.

## Static inventory and control flow

Start with `$a1x/scripts/entry_points.py`; use `$a1x/scripts/graph_summary.py` after Graphify and `$a1x/scripts/coverage_gate.py` after classification. These are deterministic scope-accounting helpers inherited from the X-Ray workflow. They do not decide access control, reachability, or vulnerability.

Use the compiler AST and Slither first for deterministic inventory, inheritance, storage writers, call relationships, modifiers, delegatecalls, external calls, and candidate CFG paths. Useful Slither printers/detectors may include contract/function summaries, call graphs, CFGs, data dependencies, inheritance, modifiers, and human summaries. Save tool version, command, build configuration, and raw output.

Use graph tools such as Graphify/Wake only when they materially improve navigation. Resolve proxies, facets, assembly, dynamic dispatch, callbacks, and external dependencies manually. Confirm every security-relevant edge in source or bytecode and deployed configuration.

Use `cast` and RPC reads for code hashes, storage/configuration, roles, balances, implementations, and logs at the pinned block. Never print or persist RPC URLs or API keys.

## Concrete EVM execution

Use Forge for source-faithful unit, integration, invariant, trace, and deterministic regression tests. Use a session-owned Anvil fork when the question depends on deployed code, configuration, liquidity, external protocols, historical state, or multi-contract composition.

Start the fork through the runtime so it records chain, block/hash, PID, endpoint, logs, snapshot, and cleanup. Announce these fields in chat. Revert to the baseline snapshot between independent experiments. Serialize fork mutations or create separate disclosed forks.

Do not use `vm.store`, mocked protocol returns, impersonated protocol identities, or free balances to establish the claimed exploit edge. Such tools may build ordinary environment setup only when the resulting attacker capabilities and accounting remain faithful and explicitly separated.

## Stateful invariant fuzzing

Route sequence-dependent protocols as follows:

- **Foundry invariant:** repository-native handlers, fast iteration, trace/replay, and final deterministic regressions.
- **Wake:** semantic Python actor models, rich chain interaction, and independent reference/oracle logic.
- **Echidna:** coverage-guided property exploration and shrinkable call sequences.
- **Medusa:** parallel mutation/corpus exploration when its compilation/harness route is healthy.
- **ItyFuzz:** difficult deployed-state or persistent-state reachability when supported by the target.

Probe target compatibility before routing. Use one backend first; add another only for a distinct search advantage or independent challenge.

A stateful harness should represent real state writers, valuable consumers, actor identities, callbacks, time/lifecycle actions, permissionless deployments, numerical boundary generators, and honest/adversarial interleavings. Track action attempts, precondition rejects, unique state fingerprints, reached waypoints, corpus, seeds, shrink output, and resource budget. High rejection rates or one-state plateaus require generator/harness repair, not more executions.

Replay every minimized counterexample as an explicit Forge/Anvil sequence. Fuzzer success alone does not establish deployed reachability or eligible impact.

## Exact arithmetic and bounded solving

Use a small exact-integer mirror for fixed-point arithmetic, shares/assets, reserves, fees, supply, width/casts, rounding, and settlement. Match Solidity evaluation order, truncation direction, unchecked/wrapping behavior, and revert conditions. Search phase-local signals before final profit: invariant drift, share-rate movement, internal credit, reserve compression, debt/backing divergence, or stuck settlement.

Preserve revert regions and test neighboring values. Use hierarchical search when two scales interact: outer state compression/repetition and inner amount/boundary. Route small bounded constraints to Halmos or Z3 only when the abstraction is justified. Every witness returns to concrete EVM execution with positive and negative neighbors.

## Cross-contract and cross-domain systems

For cross-contract behavior, use the real downstream consumer and identity it observes. For cross-chain behavior, model both domains and the actual message authentication, replay key, ordering, finality, timeout, refund, retry, and failure semantics. A one-chain mock cannot promote a cross-domain claim.

## Validation tools

Use sealed run plans/receipts, trace facts, evidence objects, clean replay, and paired controls. Static findings and symbolic witnesses remain hypotheses until concrete execution establishes the claimed behavior. Execution remains insufficient until the property, attacker model, accounting, and impact interpretation are independently checked.
