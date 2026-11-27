# Investigation graph

## Phase routing

| Phase | Required work | Exit evidence | Companion |
| --- | --- | --- | --- |
| Identity | Resolve source, runtime bytecode, proxy/implementation, libraries, compiler, configuration, chain, and block | Deployment map with confidence and hashes | `$a1x-recon` |
| Protocol model | Trace custody, economic ownership, liabilities, units, lifecycle, roles, and dependencies | Value/state map and actor model | `$a1x-recon` |
| Obligations | State protocol properties and enumerate writers, guards, consumers, and exceptions | Ranked obligation ledger | `$a1x-obligations` |
| Mechanism | Explain a specific assumption mismatch and its valuable consumer | Falsifiable hypothesis with refuting prediction | `$a1x-obligations` |
| Composition | Establish a reachable sequence, actor capabilities, capital, time, and transaction/callback boundaries | Ordered state-transition witness | `$a1x-compose` |
| Discrimination | Select the least expensive decisive test | Test plan with support and refutation predictions | Execute, fuzz, or solve |
| Validation | Reproduce the property violation and impact; run controls and clean replay | Evidence packet with applicability limits | `$a1x-validate` |
| Impact extension | Propagate any new capability through alternate consumers and terminal sinks; independently refute and minimize | Closed impact branches or concrete blockers | `$a1x-scale`, `$a1x-validate` |
| Completion | Challenge all required coverage families and exhaust cheap high-value branches | Successful runtime completion gate | `$a1x-runtime` |

Phases form a graph. An execution result may reveal a missing dependency and return the hunt to recon. A solver result may make a composed path feasible. A refuting control may force a new obligation or mechanism.

## First pass

1. Read protocol documentation, deployment manifests, build configuration, relevant tests, and the actual implementation transitively.
2. Draw the asset and liability lifecycle before scanning functions in isolation.
3. Select the highest-consequence flow from entry through custody/accounting to exit or settlement.
4. Find every security-relevant writer of the flow's critical state, including inherited, delegated, callback, emergency, and asynchronous paths.
5. Derive falsifiable obligations and test the most informative contradiction first.
6. Execute the runtime's four independent bootstrap lanes before over-investing in the first plausible finding.

## Coverage states

Use `unread`, `mapped`, `challenged`, `executed`, `refuted`, `blocked`, or `not-applicable` for each obligation/path. `executed` requires referenced command output. Record tested state ranges and assumptions. Every `not-applicable` entry needs a reason.

## Common routing mistakes

- Do not ask a fuzzer to invent the security property it should test.
- Do not encode an unverified semantic assumption into an SMT model and call satisfiability proof of exploitability.
- Do not optimize amounts before establishing the mechanism.
- Do not force long attack chains when a one-call contradiction exists.
- Do not stop after one profitable trace without testing whether ordinary behavior explains it.
- Do not let generic AMM reverts collapse exploration into repeated swap variants.
- Do not stop at a new role, ownership right, governance majority, timelock bypass, or configuration capability; trace its consumers and maximum credible consequence.
