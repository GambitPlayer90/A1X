# Impact propagation and completion

## Capability-to-consequence graph

When an experiment grants a new capability, treat it as a producer and reverse-slice every consumer that accepts it. Include asset movement, strategy/debt allocation, mint/burn, settlement, custody, queue control, role management, upgrades, parameter changes, emergency paths, and cross-domain messages.

Record each branch with `impact add`. This is mandatory for every non-rejected candidate, not only authority-derived candidates. An open branch names the capability, sink, consequence, next experiment, consequence level, test cost, and typed grounding references. Resolve it only as:

- `demonstrated`: a new support run with sealed lineage to the candidate's original support run reaches the consumer and violates the exact downstream property, its replay passes, and a distinct control for that downstream run preserves the property;
- `refuted`: low-consequence branches need grounded refuting evidence; high-consequence branches require a mechanism-specific negative run or a source anchor combined with deployment/solver proof that a necessary transition is unreachable;
- `blocked`: a specific budget, environment, tooling, or external prerequisite is evidenced together with the condition that would resolve it.

Absence of a drain is not a refutation. Likewise, ownership is not automatically terminal merely because it is persistent.

The primitive run and impact run are deliberately separate. Plan the impact run with `--extends-candidate`, `--extends-run`, and `--extension-prefix`; then plan the causal control with `--control-for` pointing to that impact run. This permits authority acquisition in RUN-A, sink realization in RUN-B, and a negative control for RUN-B in RUN-C while retaining sealed RUN-A → RUN-B provenance.

If attempted demonstration or refutation does not meet its evidence bar, the runtime records the attempted status and promotion blocker but keeps the branch `open`. Promotion strictness must never erase the exploration lead.

## Mandatory post-candidate lanes

Every candidate opens four independent lanes:

1. impact propagation to terminal sinks;
2. alternate consumers of the weak state or authority;
3. strongest independent refutation;
4. causal minimization and prerequisite removal.

Run and aggregate the round even if the initial consequence already appears valid. If one executed partial witness has an open closure edge, run population evolution with a protected single-parent closure lane. If at least two grounded components survive, also use compatible pairwise recombination.

## Completion gate

`controller close` requires:

- a completed and aggregated blind bootstrap population;
- recorded challenge of value, authority, lifecycle, numeric, and composition surfaces;
- completed post-candidate lanes;
- no unresolved candidate awaiting validation or explicit closure;
- no open impact branches;
- no high-priority low-cost frontier action;
- a recombination generation when multiple grounded components exist.

The assessment distinguishes:

- `READY_CLEAN`: no mechanical blockers and no material blocked risk;
- `BUDGET_EXHAUSTED`: only evidenced budget blockers remain;
- `ENVIRONMENT_BLOCKED`: only evidenced environment/tooling blockers remain;
- `COMPLETE_WITH_OPEN_RISK`: the mechanical work is complete but another evidenced material prerequisite remains;
- `INCOMPLETE`: mandatory work or evidence is still missing.

Closing requires an explicit matching class: `clean`, `budget-exhausted`, `environment-blocked`, or `open-risk`. A blocked high-consequence sink can therefore be handed off honestly, but can never masquerade as a clean completion. Candidate/frontier allocation failures preserve the underlying record and appear as completion blockers.

This is a mechanical floor. The investigator still owns semantic completeness and must report unresolved gaps explicitly.
