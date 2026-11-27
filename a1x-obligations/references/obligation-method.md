# Obligation method

## Property form

Write an obligation as:

```text
For all relevant actors/claims/epochs/domains,
when PRECONDITION holds at BOUNDARY,
RELATION over explicitly named values and units must hold,
except for PERMITTED EXCEPTIONS,
otherwise SECURITY IMPACT follows.
```

Avoid words such as “correct,” “fair,” “safe,” or “proper” without a measurable relation.

## Sources of obligations

Derive from:

- asset conservation and liability coverage;
- access and delegation intent;
- lifecycle terminal-state uniqueness;
- protocol documentation and tests, checked against implementation;
- economic design and fee/rounding rules;
- standards and external dependency contracts;
- cross-domain correspondence and message finality;
- honest-user guarantees required for valuable operations.

Documentation is evidence of intent, not proof of implementation.

## Challenge dimensions

Perturb actor, amount, unit, order, timing, epoch, domain, callback depth, token behavior, role transition, partial failure, repetition, and honest-user interleaving. Challenge both missing validation and validation performed against the wrong snapshot or identity.

## Evidence discipline

Separate:

- code fact: exact read/write/guard;
- deployment fact: effective value or address at the pinned block;
- semantic inference: why the consumer requires a stronger condition;
- hypothesis: reachable sequence that may violate it;
- observation: output of a specific run.

Never promote inference to fact merely because an LLM produced compilable code.
