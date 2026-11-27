---
name: a1x-validate
description: Refute, causally control, independently replay, and calibrate a demonstrated Solidity/EVM vulnerability candidate. Use after a concrete path appears to violate a protocol obligation or when a near-miss needs rigorous closure. Verify target identity, harness integrity, actor reachability, economic accounting, deployed-state applicability, and root-cause overlap. Exclude external submission and claims unsupported by clean replay.
---

# Validate and calibrate vulnerability evidence

Assume the candidate may be wrong. Challenge the mechanism, harness, deployment, actor model, accounting, impact, and novelty before raising its evidence level.

## Assign an evidence level

Read [evidence-levels.md](references/evidence-levels.md). Evidence levels are ceilings: missing reachability, property, control, or replay prevents promotion even if the narrative is compelling.

## Refute systematically without killing recall

Test the strongest alternatives:

- intended behavior or permitted rounding/fees;
- fixture funding, impersonation, storage edits, or cooperative mocks;
- ordinary arbitrage or unrelated market movement;
- wrong implementation, configuration, block, asset, pool, or oracle;
- impossible actor, capital, ordering, timing, or cross-domain assumption;
- assertion derived from the same flawed implementation logic;
- profit offset by debt, fees, locked value, or unliquidatable tokens;
- a duplicate causal mechanism already demonstrated inside the campaign.

Read [controls-and-replay.md](references/controls-and-replay.md) and perform a causal control plus clean replay through `$a1x-runtime`.

Validation decides promotion, not whether a suspicious lead is allowed to survive. If support, replay, fidelity, or downstream control is missing, keep the lead open with the exact next discriminator. For a high-consequence lead, reject only after testing its strongest reachable form and eliminating a necessary transition under the deployed attacker model. A first revert, harness failure, happy-path pass, source-only guard argument, or lack of immediate profit is not a refutation.

## Verify applicability

At a pinned block confirm runtime implementation/modules, configuration, roles, state prerequisites, external dependencies, token behavior, liquidity/exit, oracle freshness, timing, and exposed value. Distinguish:

- local mechanism demonstration;
- historical deployed demonstration;
- current deployed applicability;
- conditional applicability with unresolved prerequisite.

## Calibrate the claim

Read [claim-calibration.md](references/claim-calibration.md). State the narrowest root cause and measured consequence supported. Separate gross extraction, net profit, victim/protocol loss, and maximum exposed value. Do not infer protocol-wide exposure from TVL.

## Distinguish candidate validity from campaign completeness

A valid ownership, role, voting, configuration, queue, or upgrade takeover can pass evidence gates while still being an intermediate primitive. Enumerate every reachable value, custody, settlement, governance, and upgrade consumer. For each, record a terminal demonstration, a causal refutation, or a concrete blocker. Run the automatically created expansion round before claiming the maximum credible consequence. E0–E6 validates the stated candidate; it does not authorize the campaign to stop.

## Deduplicate by cause

Compare artifact-bound writer, guard, state, property, valuable consumer, and ordered transition anchors inside the campaign. Similar symptoms with different state construction or action order may be distinct. Treat coarse or unresolved identities as distinct; only exact anchored sequence matches may alias. Do not claim external novelty without a separate evidence-backed prior-art review.

## Runtime evidence gate

Create the runtime candidate from the supporting run, causal control, replay, and applicability declarations. Run its E0-E5 gate, then use `$a1x-runtime` to prepare and execute a mechanically blind review in a fresh process. A manually asserted `independent` flag cannot satisfy v4 E6. Treat the result as a mechanical ceiling, not semantic proof.

## Output contract

Return:

1. evidence level and why each requirement is met;
2. exact replay and control commands plus artifact locations;
3. target/deployment identity and prerequisites;
4. measured property violation and impact accounting;
5. refutations attempted and results;
6. root-cause fingerprint and within-campaign duplicate status;
7. limitations and the strongest defensible claim;
8. closure reason for refuted candidates.

Do not submit externally. A validated candidate remains a technical evidence package, not guaranteed program acceptance.
