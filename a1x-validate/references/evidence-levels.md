# Evidence levels

| Level | Required evidence | Claim ceiling |
| --- | --- | --- |
| E0 | Idea without code-grounded mechanism | Speculation |
| E1 | Exact writer/guard/consumer contradiction | Code-grounded hypothesis |
| E2 | Reachable sequence with actor/prerequisite justification | Reachable candidate |
| E3 | Concrete execution reaches predicted suspicious state | Observed mechanism |
| E4 | Protocol-specific property violation plus causal negative control | Local demonstration |
| E5 | Unmodified deployed runtime and production-relevant dependencies at a pinned state, attacker-reachable pre-state, full impact accounting, and prerequisite verification | Deployed-state demonstration |
| E6 | Clean replay from pinned declared inputs plus a separate blind semantic review of raw source, harness, oracle, and observations | Independently reviewed evidence package |

Promotion requires all lower-level conditions. A storage-edited state cannot establish E2. Profit without a protocol property cannot establish E4. Cooperative mocks or substituted dependencies cap the claim at E4 unless the claim explicitly concerns only that local model. A historical fork cannot establish current E5. Modified target code, privileged fixture state that lacks an attacker-reachable prefix, or material dependency substitution cannot establish E5. Re-running the same workspace or using the same reasoning context cannot establish E6; if blind semantic review is unavailable, cap at E5.

For non-profit authorization or liveness findings, substitute the relevant measurable consequence while retaining reachability, control, fidelity, and replay requirements.
