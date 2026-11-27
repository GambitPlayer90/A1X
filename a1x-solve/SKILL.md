---
name: a1x-solve
description: Resolve a concrete numeric, symbolic, branch, timing, ordering, or discrete parameter constraint blocking a mapped smart contract attack path. Use after the mechanism and target semantics are established, selecting bounded enumeration, optimization, Python analysis, SMT/Symbolic testing, compiler SMTChecker, Halmos, or another available solver as appropriate. Exclude unconstrained whole-protocol symbolic execution and solver results treated as EVM proof.
---

# Solve exploit constraints without outsourcing semantics

Separate mechanism discovery from computational search. Encode only the smallest question whose answer will change reachability or impact, and validate every solution through concrete EVM execution.

## Classify the constraint

Read [solver-routing.md](references/solver-routing.md). Identify variables, domains, objective or predicate, monotonicity/unimodality assumptions, integer widths, signedness, casts, rounding, revert conditions, state dependencies, and external behavior.

Typical questions include:

- exact amount around a rounding or reserve boundary;
- loop count or action ordering;
- timestamp/block condition;
- signature/hash/preimage structure within authorized bounds;
- satisfying branch comparisons;
- profitable region under fees/slippage;
- smallest state prefix that makes a consumer reachable.

## Encode faithfully

Read [semantic-fidelity.md](references/semantic-fidelity.md). Match Solidity/EVM arithmetic, including checked/unchecked overflow, narrowing casts, signed conversion, division truncation, fixed-point scaling, and revert paths. Model external calls only to the fidelity needed by the question and state any abstraction.

## Search progressively

1. Derive analytical bounds and simplify.
2. Enumerate small discrete domains.
3. Use binary search only for a verified monotone predicate.
4. Use ternary/golden search only for a verified unimodal objective.
5. Use gradient/local methods only when discontinuities and reverts do not invalidate them.
6. Use SMT or symbolic testing for exact path predicates and bounded domains. Python Z3 dependencies may be installed or used when the concrete encoding requires them; pin and record the version and keep the solver environment separate from target build hooks.
7. Use heuristic/global search for discontinuous mixed objectives, retaining multiple candidates.

Read [numeric-search.md](references/numeric-search.md) for economic objectives.

For reserve compression, repeated rounding drift, iterative AMM math, or revert-heavy fixed-point cliffs, read [staged-fixed-point-search.md](references/staged-fixed-point-search.md). Preserve the latest reached prefix, solve the first missing phase with an exact integer mirror and bounded revert-aware search, then continue through settlement and internal-ledger realization. Do not optimize end-to-end token profit while the local invariant violation is still below an unresolved state-construction edge.

## Validate and falsify

Record the solver job as a `$a1x-runtime` solve-class run. For each solution, run the original concrete target/harness at boundary neighbors and at least one negative point. If execution disagrees, inspect the first model divergence and revise the encoding. Do not weaken the target or silently widen actor capabilities to fit a solver witness.

## Output contract

Return:

1. exact question, variables, domains, and assumptions;
2. chosen method and why its preconditions hold;
3. model/analysis artifacts and reproducible command;
4. candidate solutions and neighboring controls;
5. concrete execution result;
6. remaining abstraction or deployment gap.

A solver witness is a candidate input. Only concrete execution can raise the attack path's evidence level.
