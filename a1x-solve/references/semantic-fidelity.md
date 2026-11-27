# Solidity and EVM semantic fidelity

## Arithmetic

Preserve:

- exact bit widths and signedness;
- Solidity version and checked/unchecked regions;
- narrowing casts, which truncate rather than revert;
- signed/unsigned conversions;
- integer division toward zero and modulo semantics;
- multiplication/division ordering and fixed-point scale;
- assembly arithmetic and shifts;
- custom math libraries and rounding modes.

Encode revert conditions as path constraints, not ignored samples.

## State and calls

Bind the model to the same pre-state as concrete execution. Include only storage, balances, block context, return values, and external side effects relevant to the predicate. If an oracle, AMM, token, or callback is abstracted, state the relation assumed and validate it against the pinned deployment.

## Model integrity checks

Before trusting a witness:

1. evaluate known concrete inputs through model and EVM;
2. compare intermediate values at critical operations;
3. test boundary ±1 values and revert boundaries;
4. verify the same control flow and external-call outcomes;
5. replay the final witness without solver-only state mutation.

Satisfiable means the model admits a witness. Unsatisfiable means only the encoded bounded model has none.
