# End-to-end hunt workflow

Use this reference for a new full investigation. The sequence is a dependency graph, not a rigid waterfall: execution can send the investigation back to deployment mapping, obligations, or reachability.

## 1. Bind authorization, scope, and impact

Record before testing:

- program URL/name and supplied authorization;
- in-scope repositories, deployed addresses, proxies, modules, chains, and assets;
- exact eligible impact statements and exclusions;
- prohibited testing methods and rate/resource restrictions;
- attacker starting capabilities and permissionlessly obtainable capabilities;
- pinned block policy: latest finalized for current exposure, explicit historical block for backtesting.

Create one or more ledger `SCOPE` records. Put the exact impact statements in `data.impacts`, not in an informal note. Scope drives prioritization; it does not require a new lead to have already finished every transition to impact. Keep a grounded intermediate primitive only when it names a plausible consumer path or a bounded experiment that can establish one.

## 2. Establish identity and coverage

Run the bundled whole-header scanner before semantic triage. Its JSON file list is the coverage universe; its `entry_points` are mutation surfaces and its `read_surfaces` include public/external `view`/`pure` functions plus generated public getters. If Graphify is available, create only the bundled compact summary and reconcile its Solidity-file set with the scanner. Maintain one `coverage-map.json` row per scanned file, entry point, and read surface. Readers record dependencies, observation timing, external consumers, evidence, and an obligation or justified non-security relevance. Run the bundled coverage gate and bind the successful inputs through `a1x recon bind-coverage`; completion revalidates their seals and current scoped Solidity hashes. A failed or incomplete graph is a recorded gap, never permission to sample files.

Verify source, compiler/settings, libraries, immutables, runtime bytecode, proxy implementation, beacons, facets/modules, upgrade state, roles, pause/configuration, tokens, oracles, bridges, strategies, and live liquidity at the pinned block.

Build deterministic inventories for:

- every in-scope Solidity file and contract;
- external/public mutation entry points and fallback/receive paths;
- valuation, accounting, preview, oracle, and generated-getter read surfaces, including when consumers can observe them;
- privileged and permissionless writers;
- valuable or irreversible consumers;
- callbacks, token hooks, delegatecalls, arbitrary/dynamic calls, and cross-domain message entry points;
- asset, liability, share, internal-credit, debt, and settlement state;
- lifecycle transitions and time/epoch boundaries.

Every inventory item must end as inspected, challenged, unknown with a next probe, or justified not applicable. Static graphs accelerate navigation but cannot close semantic coverage.

If the installed Pashov `x-ray` skill is present, locate it by its `name: x-ray` frontmatter and run its deterministic entry-point scanner and coverage gate rather than recreating them. Preserve `entry-points.json`, the graph summary, and the completed coverage map under the campaign recon directory. Feed each value-moving or authority-changing entry point into the writer/consumer model below; do not leave recon as a disconnected report.

## 3. Model value, authority, and obligations

For each critical value or capability, build:

`writers -> guards -> stored/transient representation -> valuable consumers -> realization`

State an independent obligation with:

- actor and boundary;
- units and exact rounding direction/tolerance;
- preconditions and allowed exceptions;
- security-relevant consequence;
- support prediction;
- strongest alternative explanation and refuting prediction.

Useful families include conservation/backing, solvency, authorization/provenance, uniqueness/replay, settlement completeness, lifecycle monotonicity, order independence where promised, and liveness. Derive the property from protocol meaning and scoped impact, not from the implementation formula under test.

## 4. Create and prioritize investigations

An `INV` should contain one causal mechanism, its grounded code/config facts, the weakest attacker-controlled writer, the valuable consumer, reachability prerequisites, support/refute predictions, and the smallest next discriminator.

Prioritize by plausible scoped consequence, attacker reachability, uncertainty removed per cost, composition leverage, and whether evidence can falsify the mechanism. Preserve separate grounded leads as separate records. Do not equate more hypotheses with greater depth.

## 5. Compose attacker-reachable histories

Model the history as explicit transitions with:

- actor and downstream-observed identity;
- contract/function and transaction/callback boundary;
- required capital and source;
- state before/after, including internal ledgers;
- time, block, epoch, price, liquidity, and ordering assumptions;
- external dependencies and failure/revert regions;
- settlement, withdrawal, claim, liquidation, or other realization transition.

Work consumer-backward from the impact sink while constructing writer-forward reachability. Include attacker-created contracts, tokens, pools, markets, recipients, callback targets, and cyclic paths when the protocol accepts them.

## 6. Execute the cheapest discriminator

Use source-level unit tests for local semantics, a pinned fork for deployed configuration/composition, stateful fuzzing for sequences, exact models for arithmetic boundaries, and bounded symbolic tools for small justified questions. Run a cheap negative control early when it can expose fixture funding, ordinary fees, an incorrect reference model, or a manufactured prerequisite.

Every experiment becomes an `EXP` with property, setup, support/refute predictions, command, environment/fork identity, observations, artifacts, and next decision. Preserve raw logs separately; the ledger stores concise claims and hashes/paths.

## 7. Search deeply without fixed generations

Continue a branch while a bounded experiment can materially change reachability, a security property, exact constraints, or impact. Use visible subagents only for independent questions. Re-synthesize when new grounded information changes what can be tested next.

Stop or park when:

- an executed discriminator causally refutes the mechanism;
- a necessary edge is mechanically unreachable under deployed state and attacker model;
- the next dependency is external/environmental and precisely named;
- the allotted budget is reached and the partial witness plus next action are preserved;
- the path is outside the program scope.

## 8. Validate and account for impact

Before promotion, require:

- exact deployed identity/configuration at the pinned block;
- an attacker-valid end-to-end sequence;
- an independent property violation;
- a support run and clean replay;
- a paired causal control changing only the claimed cause;
- net accounting for flash principal/fees, capital, debt, liabilities, locked positions, internal credits, residual approvals, and gas when material;
- harmed party and exact eligible impact;
- current, historical, or conditional applicability stated separately.

Acquired authority, governance weight, ownership, queue control, internal credit, or upgrade capability is an intermediate primitive until its material consumers are demonstrated, refuted, or bounded.

## 9. Close honestly

Run deterministic coverage reconciliation and inspect the ledger brief. Stop session-owned processes. Verify the event chain, ledger, evidence objects, replay, and candidate gates. Report clean areas as bounded coverage only. Keep unresolved high-consequence paths visible with their exact blocker and next experiment.
