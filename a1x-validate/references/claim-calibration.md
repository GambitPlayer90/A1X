# Claim and impact calibration

## Root-cause fingerprint

Record:

```text
producer/writer -> missing or inconsistent guard -> corrupted/weak state
-> valuable consumer -> consequence
```

Add actor capabilities, transaction/time/domain boundaries, and configuration prerequisites. Use this fingerprint for within-campaign deduplication. External novelty requires a separate review of prior audits, disclosures, issues, accepted risks, and program known-issue sources when the user requests it.

## Impact accounting

Report separately:

- gross assets moved or claims created;
- attacker net profit after principal, debt, fees, and realizable exit;
- direct victim/protocol loss or liability increase;
- capital/time/ordering requirements;
- demonstrated amount at the pinned state;
- maximum exposed value only when bounded from verified state and mechanics.

Do not use total TVL as exposed value without a path reaching it.

## Wording

Use “demonstrates” only for executed observations. Use “can” only for reachable actor capabilities. Use “may” for unresolved hypotheses. Name historical, current, conditional, local-only, mocked, or source-only applicability explicitly.

Avoid severity labels until the mechanism and consequence are established. Avoid “arbitrary,” “permanent,” “anyone,” “all funds,” or “no privileges” unless the evidence supports the quantifier.

After validation, state the remediation principle and preserve the protocol-specific property as a regression assertion. Do not edit production code unless requested.

## Closure

For refuted candidates record the exact broken link: guard holds, actor unavailable, state unreachable, property intact, impact neutralized, deployment not affected, duplicate root cause, or unresolved due to a named evidence gap. Preserve useful partial evidence for future variants.
