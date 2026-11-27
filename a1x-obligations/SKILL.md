---
name: a1x-obligations
description: Derive protocol-specific security obligations and falsifiable vulnerability hypotheses from a mapped Solidity/EVM system. Use after deployment/value-flow recon or when a suspected accounting, authorization, oracle, settlement, bridge, governance, signature, or lifecycle contradiction needs a precise property and security oracle. Exclude generic vulnerability checklists and ungrounded issue generation.
---

# Derive obligations and falsifiable hypotheses

Turn protocol intent and code behavior into properties that can be challenged. An obligation states what must hold, for whom, at which boundary, in which units, and under which permitted exceptions.

## Derive the obligation ledger

Read [obligation-method.md](references/obligation-method.md). Start from assets, liabilities, claims, authority, and lifecycle terminal states. For each obligation record:

- quantifier and actors;
- precondition and boundary;
- exact variables and units;
- permitted loss/rounding/latency;
- all writers, guards, and consumers;
- observable violation and impact;
- current evidence and unknowns.

Use [primitive-families.md](references/primitive-families.md) only for domains present in the target. It supplies perturbation questions, not presumed findings.

## Build writer/guard/consumer maps

For every critical consumer, ask:

1. Which state does it trust?
2. Who and what can write that state?
3. Do all writers enforce the assumptions the consumer needs?
4. Can a writer use a different actor, asset, unit, epoch, domain, or snapshot?
5. Can a lifecycle interruption leave state valid longer than intended?

The highest-value hypotheses usually arise when a producer establishes weaker state than a valuable consumer assumes.

## Form a falsifiable hypothesis

Use this shape:

> An actor with capabilities C can execute reachable sequence S from state P, causing consumer X to accept state Y even though obligation O requires Z, producing observable impact I.

Record one supporting prediction and one refuting prediction before running a test. Name the strongest intended-behavior explanation.

## Design a security oracle

Read [security-oracles.md](references/security-oracles.md). Prefer a protocol-specific assertion over profit alone. Measure the attacker-controlled group and the harmed party or protocol together. Include debt, fees, consumed principal, residual positions, and backing.

## Rank without hiding uncertainty

Rank by potential consequence, reachability, evidence, exposed value, and discriminating-test cost. Keep dimensions visible; do not let an arbitrary total score decide truth.

## Output contract

Update `obligations.md`, `coverage.md`, and one hypothesis file per selected mechanism. Return:

1. precise obligations with units and boundaries;
2. writer/guard/consumer contradictions;
3. ranked falsifiable hypotheses;
4. supporting and refuting predictions;
5. candidate security oracles;
6. the cheapest next action for `$a1x-compose`, `$a1x-execute`, `$a1x-fuzz`, or `$a1x-solve`.
