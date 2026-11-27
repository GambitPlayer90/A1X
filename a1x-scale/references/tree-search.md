# Tree and semantic frontier search

## Representation

Define:

- state: replayable prefix plus semantic fingerprint;
- action: actor, target, selector, parameters, value, and environment transition;
- transition: concrete execution result;
- terminal: property violation, refutation, blocked state, or budget exhaustion;
- value vector: evidence, obligation progress, reachability, impact, novelty, and cost.

Do not use free-form “thoughts” as tree nodes when concrete EVM states are available.

## Expansion

Generate actions from mapped writers, valuable consumers, callbacks, lifecycle transitions, and unresolved prerequisites. Prune impossible permissions, missing assets, duplicate semantic states, and paths that only reproduce known generic reverts.

## Strategy

Begin with best-first or beam search over semantic waypoints. Retain diverse state regions. Use MCTS only if repeated transitions have a meaningful value signal before terminal profit and the branching factor can be controlled. Backpropagate evidence-aware vectors or explicit dominance rather than a single arbitrary scalar where possible.

## Near misses

A useful near miss reaches a state that reduces the remaining proof obligation. Store its exact prefix and blocker. “Almost profitable” without a causal state relation is weak evidence.
