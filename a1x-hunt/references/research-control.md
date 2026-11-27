# Research control and adaptive budgets

## Active frontier

Maintain a small Pareto frontier across:

- evidence strength;
- potential security impact;
- reachability confidence;
- novelty of mechanism/state;
- cost of the next discriminating action.

Do not collapse these into one opaque score. Allocate active slots family-first and keep distinct overflow or coarsely identified mechanisms in reserve. Prefer questions whose answers change the investigation.

Register high-consequence branches and cheap discriminators in the runtime frontier with their grounding evidence. A high-priority item with low or medium test cost automatically opens independent direct, alternate, and refutation lanes. An open high-priority, low-cost item mechanically blocks campaign completion.

## Default allocation

Treat these as adjustable starting points, not hard limits:

- Map two or three critical asset/lifecycle flows before deep testing.
- Keep three to six active hypotheses.
- Allow two or three discriminating runs on an unchanged hypothesis before requiring a new observation, revised mechanism, or pivot.
- Reserve roughly one quarter of remaining budget for refutation, alternate consumers, emergency/asynchronous paths, and clean replay.

The number of EVM executions inside a fuzzer or symbolic campaign is not the number of research attempts. Record both.

## Continue, pivot, or stop

Continue when a run:

- reaches a new security-relevant state;
- resolves a prerequisite, actor, ordering, or numerical constraint;
- increases or decreases confidence in a falsifiable claim;
- exposes a missing writer, consumer, or dependency;
- produces a smaller or more faithful witness.

Pivot when repeated runs reproduce the same failure without new information, the required state is unreachable under attacker capabilities, or a cheaper hypothesis offers greater information value.

Stop a hypothesis only when its strongest reachable mechanism is contradicted by a causal negative experiment, a necessary prerequisite is mechanically shown outside the attacker model, or the exact impact property is disproved. Budget or environment exhaustion pauses/blocks the lead; it does not establish safety. Preserve the closure evidence.

Stop the campaign only after critical flows received meaningful challenge, the active frontier is exhausted or concretely blocked, demonstrated candidates have independent extension/refutation lanes, and every material downstream impact branch is demonstrated, refuted, or concretely blocked. Run `controller assess`, then require `controller close` to succeed with the matching closure class. A blocked material sink is an explicit open risk, budget exhaustion, or environment limitation—not a clean completion. Report gaps rather than filling them with confidence.

## Parallel work

Delegate only independent, bounded work with explicit inputs and outputs. Give workers the target identity, one obligation or mechanism lane, budget, allowed tools, and evidence contract. Do not reveal known answers during blind evaluation. Isolate write-heavy work in separate worktrees or directories. The initial blind population is mandatory; later generations may see structured parent handoffs only during recombination. The coordinator owns synthesis and conflict resolution.

Parallelism is useful for recon partitions, distinct hypotheses, test construction, fuzz campaigns, and independent refutation. It is counterproductive when workers edit the same harness or inherit one another's unverified conclusions.
