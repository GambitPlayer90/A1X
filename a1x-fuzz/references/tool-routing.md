# Fuzzer routing

| Question shape | Prefer | Reason |
| --- | --- | --- |
| One known path, unknown scalar inputs | Foundry fuzz test | Minimal harness and fast feedback |
| Several protocol actions, custom invariant | Foundry invariant / Echidna / Medusa | Stateful sequence generation |
| CPU-parallel coverage exploration | Medusa | Parallel workers and coverage corpus |
| Mature property workflow and shrinking | Echidna | Property-centered campaign and replay |
| Persistent state is harder than calldata | Available snapshot-based fuzzer | Retain interesting states and mutate singleton actions |
| Narrow branch/comparison barrier | Concolic/symbolic support or `$a1x-solve` | Solve constraint rather than random search |

Tool availability and target build compatibility may override preference. A second tool is justified when it has a distinct search model or independently replays a counterexample. Running every tool is not coverage.

## Static support

Use Slither, Wake, Aderyn, compiler ASTs, or similar tools only to identify state writers, call edges, mutation dictionaries, or instrumentation points. Detector output is a hypothesis source, not a finding.

## Fork versus local deployment

Prefer fork-aware execution when deployed configuration or external state is material. Local deployment is appropriate when constructors/initializers and dependencies can be faithfully reproduced. State which deployment claim the chosen mode supports.
