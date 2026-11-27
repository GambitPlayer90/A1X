# Solver and search routing

| Constraint | First choice | Escalate when |
| --- | --- | --- |
| Tiny integer/ordering space | Exhaustive enumeration | Domain grows beyond practical bound |
| Monotone threshold | Binary search plus neighbor checks | Predicate has reversals/reverts |
| Unimodal continuous-like objective | Ternary/golden search | Integer discontinuities create multiple peaks |
| Exact Solidity path predicate | Halmos/SMT/symbolic test if available | External/state model becomes dominant |
| Compiler-local assertion | Solidity SMTChecker | Cross-contract/stateful behavior is required |
| Stateful sequence and inputs | Focused fuzzer | Hard comparisons block progress |
| Discontinuous economic objective | Bounded grid, adaptive sampling, evolutionary/global search | Search region can be narrowed analytically |
| Prepared-state repetition × per-step rounding/revert boundary | Snapshot the reached prefix; outer bounded compression/repetition search plus inner exact-integer adaptive/backoff search | A narrowed branch predicate becomes suitable for Halmos/Z3 |
| Hash/randomness/timing calculation | Direct programmatic analysis | Unknown state or ordering dominates |

Do not launch Mythril, symbolic execution, or a solver over the entire protocol without a concrete predicate. Timeouts and unknown results are coverage limitations.

Read [staged-fixed-point-search.md](staged-fixed-point-search.md) for nested precision/amplification searches. Preserve the latest reached prefix and optimize a phase-local invariant or internal-credit signal before end-to-end profit.

## Method preconditions

Document monotonicity, unimodality, differentiability, independence, and bounds before choosing an algorithm that assumes them. EVM objectives often contain truncation, fee tiers, liquidity cliffs, and revert holes; default to methods robust to discontinuity.
