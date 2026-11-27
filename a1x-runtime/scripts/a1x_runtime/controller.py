from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import exclusive_lock, read_json, write_json_atomic, write_text_atomic
from .completion_sweep import sweep_research_state
from .errors import A1XError, BudgetError, IntegrityError, ValidationError
from .evidence import has_demonstration_pair, has_refuting_evidence, has_strong_refuting_evidence, impact_control_pair, normalize_evidence_refs, verify_evidence_refs
from .records import allocate_id, event, require_campaign, schema_for, utc_now
from .scheduling import resource_snapshot


BOOTSTRAP_AXES = [
    "value-and-numerical: trace asset/claim conservation, denominators, rounding boundaries, and profitable cycles",
    "authority-and-trust: challenge provenance, roles, governance cost, factories, upgrades, and configuration semantics",
    "lifecycle-and-composition: search callbacks, partial completion, ordering, timing, and cross-contract state transitions",
    "adversarial-refutation: attack the strongest apparent safety argument and seek a causal counterexample or clean refutation",
]

EXPANSION_AXES = [
    "impact-extension: propagate the demonstrated primitive through every reachable value, upgrade, governance, settlement, and custody sink",
    "alternate-consumer: find a different valuable consumer that trusts the same weak state, authority, denominator, or provenance",
    "strongest-refutation: independently falsify reachability, actor capability, configuration fidelity, causality, or claimed consequence",
    "causal-minimization: shrink the sequence, remove one prerequisite at a time, and identify the exact necessary transition",
]

COVERAGE_FAMILIES = {"value", "authority", "lifecycle", "numeric", "composition"}
BLOCKER_KINDS = {"budget", "environment", "external-prerequisite", "tooling"}


def _campaign_prompt(campaign: dict[str, Any]) -> str:
    chain = campaign.get("chain", {})
    return (
        f"Conduct a blind adversarial first pass over target `{campaign['target']}`. "
        "Start from valuable or irreversible consumers, derive protocol-specific obligations, map attacker control, "
        "and construct abnormal but reachable state shapes. Do not settle on repository summaries. "
        f"Deployment context: chain_id={chain.get('chain_id')}, block={chain.get('block_number')}. "
        "Return one falsifiable mechanism or a precise evidence-backed refutation for the assigned axis."
    )


def ensure_bootstrap(root: Path, *, per_lane_timeout: int = 7200) -> dict[str, Any]:
    """Create the mandatory blind population once. It is intentionally idempotent."""
    from .scale import create_round

    campaign = require_campaign(root)
    for path in sorted((root / "scale").glob("ROUND-*/plan.json")):
        plan = read_json(path)
        if plan.get("purpose") == "bootstrap":
            return plan
    available = int(campaign.get("budgets", {}).get("max_scale_lanes", 0))
    if available and available < len(BOOTSTRAP_AXES):
        raise ValidationError(f"A1X requires at least {len(BOOTSTRAP_AXES)} scale lanes for the mandatory blind population")
    prompt_path = root / "orchestration" / "bootstrap-prompt.md"
    write_text_atomic(prompt_path, _campaign_prompt(campaign) + "\n")
    return create_round(
        root,
        prompt_file=prompt_path,
        axes=BOOTSTRAP_AXES,
        hypothesis_id=None,
        per_lane_timeout=per_lane_timeout,
        purpose="bootstrap",
    )


def ensure_candidate_expansion(root: Path, candidate_id: str, *, per_lane_timeout: int = 7200) -> dict[str, Any]:
    """Open mandatory extension/refutation lanes for every concrete candidate."""
    from .scale import create_round

    candidate_path = root / "candidates" / f"{candidate_id}.json"
    if not candidate_path.exists():
        raise ValidationError(f"unknown candidate: {candidate_id}")
    candidate = read_json(candidate_path)
    for path in sorted((root / "scale").glob("ROUND-*/plan.json")):
        plan = read_json(path)
        if plan.get("purpose") == "candidate-expansion" and plan.get("candidate_id") == candidate_id:
            if candidate.get("expansion_round") != plan["id"] or candidate.get("expansion_status") != "allocated":
                with exclusive_lock(root):
                    current = read_json(candidate_path)
                    current["expansion_round"] = plan["id"]
                    current["expansion_status"] = "allocated"
                    current["expansion_blocker"] = None
                    current["expansion_blocker_kind"] = None
                    write_json_atomic(candidate_path, current)
            return plan
    prompt = f"""A concrete candidate has been demonstrated. Treat it as a starting primitive, not a stopping condition.

Candidate: {candidate_id}
Root cause: {candidate.get('root_cause')}
Reachability: {candidate.get('reachability')}
Current consequence: {candidate.get('impact')}
Consequence class: {candidate.get('consequence_class', 'unknown')}
Terminal impact already demonstrated: {candidate.get('terminal_impact', False)}

Follow the assigned axis. Preserve independent judgment. Any stronger consequence must be executed against a faithful local or pinned-fork state and compared with a causal control. A failed extension is useful only when the exact blocker is evidenced.
"""
    prompt_path = root / "orchestration" / f"{candidate_id}-expansion.md"
    write_text_atomic(prompt_path, prompt)
    plan = create_round(
        root,
        prompt_file=prompt_path,
        axes=EXPANSION_AXES,
        hypothesis_id=candidate.get("hypothesis_id"),
        per_lane_timeout=per_lane_timeout,
        purpose="candidate-expansion",
        candidate_id=candidate_id,
    )
    with exclusive_lock(root):
        current = read_json(candidate_path)
        current["expansion_round"] = plan["id"]
        current["expansion_status"] = "allocated"
        current["expansion_blocker"] = None
        current["expansion_blocker_kind"] = None
        write_json_atomic(candidate_path, current)
    event(root, "controller.candidate-expansion-created", candidate_id=candidate_id, round_id=plan["id"])
    return plan


def record_coverage(root: Path, *, family: str, status: str, evidence_refs: list[dict[str, Any]], limitations: str) -> dict[str, Any]:
    require_campaign(root)
    if family not in COVERAGE_FAMILIES:
        raise ValidationError(f"coverage family must be one of: {', '.join(sorted(COVERAGE_FAMILIES))}")
    if status not in {"challenged", "refuted", "not-applicable"}:
        raise ValidationError("coverage status must be challenged, refuted, or not-applicable")
    evidence = normalize_evidence_refs(root, evidence_refs, required=True)
    record = {
        "schema": schema_for(root),
        "kind": "coverage",
        "family": family,
        "status": status,
        "evidence_refs": evidence,
        "limitations": limitations,
        "updated_at": utc_now(),
    }
    write_json_atomic(root / "orchestration" / f"coverage-{family}.json", record)
    event(root, "controller.coverage-recorded", family=family, status=status)
    return record


def add_frontier(
    root: Path,
    *,
    kind: str,
    statement: str,
    grounding_refs: list[dict[str, Any]],
    next_action: str,
    priority: str,
    cost: str,
    candidate_id: str | None,
) -> dict[str, Any]:
    require_campaign(root)
    if priority not in {"low", "medium", "high"} or cost not in {"low", "medium", "high"}:
        raise ValidationError("priority and cost must be low, medium, or high")
    if candidate_id and not (root / "candidates" / f"{candidate_id}.json").exists():
        raise ValidationError(f"unknown candidate: {candidate_id}")
    if not statement.strip() or not next_action.strip():
        raise ValidationError("frontier statement and next action must be non-empty")
    grounding = normalize_evidence_refs(root, grounding_refs, required=True)
    item_id = allocate_id(root, "FRONTIER")
    record = {
        "schema": schema_for(root),
        "kind": "frontier-item",
        "id": item_id,
        "created_at": utc_now(),
        "candidate_id": candidate_id,
        "frontier_kind": kind,
        "statement": statement,
        "grounding_refs": grounding,
        "next_action": next_action,
        "priority": priority,
        "cost": cost,
        "status": "open",
        "evidence_refs": [],
        "scale_status": "not-required",
        "scale_blocker": None,
        "scale_blocker_kind": None,
    }
    write_json_atomic(root / "frontier" / f"{item_id}.json", record)
    event(root, "controller.frontier-opened", frontier_id=item_id, priority=priority, cost=cost)
    if priority == "high" and cost in {"low", "medium"}:
        from .scale import create_round

        candidate = read_json(root / "candidates" / f"{candidate_id}.json") if candidate_id else None
        prompt_path = root / "orchestration" / f"{item_id}-adaptive-scale.md"
        write_text_atomic(
            prompt_path,
            f"""A grounded high-priority frontier has multiple material branches.

Frontier: {statement}
Grounding records: {grounding}
Current next action: {next_action}

Independently resolve the assigned branch with the cheapest discriminating experiment. Preserve exact state, actor, consumer, and blocker evidence.
""",
        )
        try:
            plan = create_round(
                root,
                prompt_file=prompt_path,
                axes=[
                    "direct-discriminator: execute the stated next action and measure the security property",
                    "alternate-branch: test a different consumer, ordering, state shape, or consequence of the same grounded primitive",
                    "strongest-refutation: independently attack reachability, causality, fidelity, or impact",
                ],
                hypothesis_id=candidate.get("hypothesis_id") if candidate else None,
                per_lane_timeout=7200,
                purpose="adaptive-frontier",
                candidate_id=candidate_id,
            )
        except A1XError as exc:
            record["scale_status"] = "blocked"
            record["scale_blocker"] = f"{type(exc).__name__}: {exc}"
            record["scale_blocker_kind"] = "budget" if isinstance(exc, BudgetError) else "tooling"
            write_json_atomic(root / "frontier" / f"{item_id}.json", record)
            event(root, "controller.frontier-allocation-blocked", frontier_id=item_id, error_type=type(exc).__name__)
            return record
        except Exception as exc:
            record["scale_status"] = "blocked"
            record["scale_blocker"] = f"unexpected {type(exc).__name__}: {exc}"
            record["scale_blocker_kind"] = "tooling"
            write_json_atomic(root / "frontier" / f"{item_id}.json", record)
            event(root, "controller.frontier-allocation-error", frontier_id=item_id, error_type=type(exc).__name__)
            raise
        record["scale_round"] = plan["id"]
        record["scale_status"] = "allocated"
        record["scale_blocker"] = None
        record["scale_blocker_kind"] = None
        write_json_atomic(root / "frontier" / f"{item_id}.json", record)
    return record


def resolve_frontier(
    root: Path,
    *,
    frontier_id: str,
    status: str,
    evidence_refs: list[dict[str, Any]],
    blocker_kind: str | None,
    resolution_condition: str,
) -> dict[str, Any]:
    if status not in {"demonstrated", "refuted", "blocked", "superseded"}:
        raise ValidationError("frontier resolution must be demonstrated, refuted, blocked, or superseded")
    evidence = normalize_evidence_refs(root, evidence_refs, required=True)
    if status == "blocked":
        if blocker_kind not in BLOCKER_KINDS or not resolution_condition.strip():
            raise ValidationError("blocked frontier requires blocker kind and resolution condition")
    elif blocker_kind:
        raise ValidationError("blocker kind is valid only for blocked frontier items")
    path = root / "frontier" / f"{frontier_id}.json"
    if not path.exists():
        raise ValidationError(f"unknown frontier item: {frontier_id}")
    with exclusive_lock(root):
        record = read_json(path)
        record.update(
            {
                "status": status,
                "evidence_refs": evidence,
                "blocker_kind": blocker_kind,
                "resolution_condition": resolution_condition,
                "resolved_at": utc_now(),
            }
        )
        write_json_atomic(path, record)
    event(root, "controller.frontier-resolved", frontier_id=frontier_id, status=status)
    return record


def add_impact(
    root: Path,
    *,
    candidate_id: str,
    capability: str,
    sink: str,
    consequence: str,
    impact_property: str,
    status: str,
    evidence_refs: list[dict[str, Any]],
    next_action: str,
    high_consequence: bool,
    low_cost: bool,
    blocker_kind: str | None = None,
    resolution_condition: str = "",
) -> dict[str, Any]:
    require_campaign(root)
    candidate_path = root / "candidates" / f"{candidate_id}.json"
    if not candidate_path.exists():
        raise ValidationError(f"unknown candidate: {candidate_id}")
    candidate = read_json(candidate_path)
    if status not in {"open", "demonstrated", "refuted", "blocked"}:
        raise ValidationError("impact status must be open, demonstrated, refuted, or blocked")
    if any(not value.strip() for value in (capability, sink, consequence, impact_property, next_action)):
        raise ValidationError("impact capability, sink, consequence, property, and next action must be non-empty")
    evidence = normalize_evidence_refs(root, evidence_refs, required=True)
    requested_status: str | None = None
    promotion_status = "not-applicable" if status in {"open", "blocked"} else "satisfied"
    promotion_blocker: str | None = None
    candidate_hypothesis = str(candidate.get("hypothesis_id", ""))
    control = impact_control_pair(
        root,
        evidence,
        impact_property,
        expected_hypothesis_id=candidate_hypothesis,
        expected_candidate_id=candidate_id,
        expected_parent_run=str(candidate.get("support_run", "")),
    ) if status == "demonstrated" and high_consequence else None
    if status == "demonstrated" and not has_demonstration_pair(evidence):
        requested_status, status, promotion_status = "demonstrated", "open", "deferred"
        promotion_blocker = "missing supporting property-violating run plus matching replay; lead retained open"
    elif status == "demonstrated" and high_consequence and control is None:
        requested_status, status, promotion_status = "demonstrated", "open", "deferred"
        promotion_blocker = "missing impact-specific causal control for the exact downstream property; lead retained open"
    elif status == "refuted" and not (
        has_strong_refuting_evidence(
            root,
            evidence,
            expected_property=impact_property,
            expected_hypothesis_id=candidate_hypothesis,
            expected_candidate_id=candidate_id,
            expected_parent_run=str(candidate.get("support_run", "")),
        )
        if high_consequence
        else has_refuting_evidence(evidence)
    ):
        requested_status, status, promotion_status = "refuted", "open", "deferred"
        promotion_blocker = "refutation lacks a mechanism-specific negative experiment or anchored impossibility proof; lead retained open"
    if status == "blocked":
        if blocker_kind not in BLOCKER_KINDS or not resolution_condition.strip():
            raise ValidationError("blocked impact requires blocker kind and resolution condition")
    elif blocker_kind:
        raise ValidationError("blocker kind is valid only for blocked impact branches")
    impact_id = allocate_id(root, "IMPACT")
    record = {
        "schema": schema_for(root),
        "kind": "impact-branch",
        "id": impact_id,
        "created_at": utc_now(),
        "candidate_id": candidate_id,
        "capability": capability,
        "sink": sink,
        "consequence": consequence,
        "impact_property": impact_property,
        "status": status,
        "requested_status": requested_status,
        "promotion_status": promotion_status,
        "promotion_blocker": promotion_blocker,
        "impact_control": control,
        "evidence_refs": evidence,
        "next_action": next_action,
        "high_consequence": high_consequence,
        "low_cost": low_cost,
        "blocker_kind": blocker_kind,
        "resolution_condition": resolution_condition,
    }
    write_json_atomic(root / "impact" / f"{impact_id}.json", record)
    event(root, "controller.impact-branch-recorded", candidate_id=candidate_id, impact_id=impact_id, status=status, promotion_status=promotion_status)
    return record


def resolve_impact(
    root: Path,
    *,
    impact_id: str,
    status: str,
    evidence_refs: list[dict[str, Any]],
    next_action: str,
    blocker_kind: str | None,
    resolution_condition: str,
) -> dict[str, Any]:
    if status not in {"demonstrated", "refuted", "blocked"}:
        raise ValidationError("impact resolution must be demonstrated, refuted, or blocked")
    evidence = normalize_evidence_refs(root, evidence_refs, required=True)
    if status == "blocked":
        if blocker_kind not in BLOCKER_KINDS or not resolution_condition.strip():
            raise ValidationError("blocked impact requires blocker kind and resolution condition")
    elif blocker_kind:
        raise ValidationError("blocker kind is valid only for blocked impact branches")
    path = root / "impact" / f"{impact_id}.json"
    if not path.exists():
        raise ValidationError(f"unknown impact branch: {impact_id}")
    with exclusive_lock(root):
        record = read_json(path)
        candidate = read_json(root / "candidates" / f"{record['candidate_id']}.json")
        candidate_hypothesis = str(candidate.get("hypothesis_id", ""))
        requested_status: str | None = None
        promotion_status = "satisfied"
        promotion_blocker: str | None = None
        control = impact_control_pair(
            root,
            evidence,
            str(record.get("impact_property", "")),
            expected_hypothesis_id=candidate_hypothesis,
            expected_candidate_id=str(record.get("candidate_id", "")),
            expected_parent_run=str(candidate.get("support_run", "")),
        ) if status == "demonstrated" and record.get("high_consequence") else None
        effective_status = status
        if status == "demonstrated" and not has_demonstration_pair(evidence):
            requested_status, effective_status, promotion_status = "demonstrated", "open", "deferred"
            promotion_blocker = "missing supporting property-violating run plus matching replay; lead retained open"
        elif status == "demonstrated" and record.get("high_consequence") and control is None:
            requested_status, effective_status, promotion_status = "demonstrated", "open", "deferred"
            promotion_blocker = "missing impact-specific causal control for the exact downstream property; lead retained open"
        elif status == "refuted" and not (
            has_strong_refuting_evidence(
                root,
                evidence,
                expected_property=str(record.get("impact_property", "")),
                expected_hypothesis_id=candidate_hypothesis,
                expected_candidate_id=str(record.get("candidate_id", "")),
                expected_parent_run=str(candidate.get("support_run", "")),
            )
            if record.get("high_consequence")
            else has_refuting_evidence(evidence)
        ):
            requested_status, effective_status, promotion_status = "refuted", "open", "deferred"
            promotion_blocker = "refutation lacks a mechanism-specific negative experiment or anchored impossibility proof; lead retained open"
        record.update(
            {
                "status": effective_status,
                "requested_status": requested_status,
                "promotion_status": promotion_status,
                "promotion_blocker": promotion_blocker,
                "impact_control": control,
                "evidence_refs": evidence,
                "next_action": next_action,
                "blocker_kind": blocker_kind,
                "resolution_condition": resolution_condition,
            }
        )
        if effective_status != "open":
            record["resolved_at"] = utc_now()
        else:
            record.pop("resolved_at", None)
        write_json_atomic(path, record)
    event(root, "controller.impact-branch-resolved", impact_id=impact_id, status=record["status"], requested_status=status, promotion_status=record["promotion_status"])
    return record


def _rounds(root: Path) -> list[dict[str, Any]]:
    return [read_json(path) for path in sorted((root / "scale").glob("ROUND-*/plan.json"))]


def _eligible_handoffs(root: Path) -> int:
    from .scale import _rsa_eligible

    causal_keys: set[tuple[str, ...]] = set()
    for path in (root / "scale").glob("ROUND-*/aggregate.json"):
        aggregate = read_json(path)
        for handoff in [*aggregate.get("handoffs", []), *aggregate.get("reserve_handoffs", [])]:
            verification = handoff.get("runtime_verification", {})
            key = verification.get("causal_key")
            level = verification.get("evidence_level", "E0")
            if _rsa_eligible(handoff) and isinstance(key, list) and key and level != "E0":
                causal_keys.add(tuple(str(item) for item in key))
    return len(causal_keys)


def assess_completion(root: Path) -> dict[str, Any]:
    require_campaign(root)
    blockers: list[dict[str, str]] = []
    open_risks: list[dict[str, str]] = []
    sweep = sweep_research_state(root)
    for item in sweep.get("invalid", []):
        blockers.append({"gate": "RESEARCH-INTEGRITY", "reason": f"{item['source']}: {item['reason']}"})
    for item in sweep.get("open", []):
        blockers.append({"gate": "RESEARCH-CONTINUITY", "reason": f"{item['source']}: {item['reason']} (next: {item['next_action']})"})
    for item in sweep.get("risks", []):
        open_risks.append({"kind": item["kind"], "record": item["source"], "reason": item["reason"]})
    rounds = _rounds(root)
    environment_rounds = [r for r in rounds if r.get("status") == "environment-blocked"]
    for round_record in environment_rounds:
        open_risks.append(
            {
                "kind": "environment",
                "record": round_record["id"],
                "reason": round_record.get("blocker") or "scale round blocked by the execution environment",
            }
        )
    bootstrap = [r for r in rounds if r.get("purpose") == "bootstrap"]
    if not bootstrap:
        blockers.append({"gate": "TTS-BOOTSTRAP", "reason": "mandatory independent blind population was not created"})
    elif any(r.get("status") == "environment-blocked" for r in bootstrap):
        pass
    elif not any(r.get("status") == "completed" and int(r.get("completed_lanes", 0)) == len(r.get("lanes", [])) == len(BOOTSTRAP_AXES) for r in bootstrap):
        blockers.append({"gate": "TTS-BOOTSTRAP", "reason": "all four independent bootstrap lanes must complete"})
    elif not any((root / "scale" / r["id"] / "aggregate.json").exists() for r in bootstrap):
        blockers.append({"gate": "TTS-AGGREGATE", "reason": "bootstrap evidence has not been aggregated"})
    else:
        completed_bootstrap = next(
            r
            for r in bootstrap
            if r.get("status") == "completed"
            and int(r.get("completed_lanes", 0)) == len(r.get("lanes", [])) == len(BOOTSTRAP_AXES)
            and (root / "scale" / r["id"] / "aggregate.json").exists()
        )
        aggregate = read_json(root / "scale" / completed_bootstrap["id"] / "aggregate.json")
        handoffs = aggregate.get("handoffs", [])
        substantive = [
            handoff
            for handoff in handoffs
            if handoff.get("runtime_verification", {}).get("evidence_level") != "E0"
            and handoff.get("runtime_verification", {}).get("artifact_bound") is True
            and handoff.get("runtime_verification", {}).get("evidence_artifact_sha256")
            and handoff.get("tested_obligation")
            and handoff.get("discriminator")
        ]
        if aggregate.get("invalid_lanes") or len(handoffs) != len(BOOTSTRAP_AXES) or len(substantive) != len(BOOTSTRAP_AXES):
            blockers.append(
                {
                    "gate": "TTS-HANDOFF",
                    "reason": "all bootstrap lanes require artifact-anchored obligation, discriminator, and causal identity handoffs",
                }
            )

    incomplete_adaptive = [
        r["id"]
        for r in rounds
        if r.get("purpose") == "adaptive-frontier"
        and r.get("status") != "environment-blocked"
        and (
            r.get("status") != "completed"
            or int(r.get("completed_lanes", 0)) != len(r.get("lanes", []))
            or not (root / "scale" / r["id"] / "aggregate.json").exists()
        )
    ]
    if incomplete_adaptive:
        blockers.append({"gate": "TTS-ADAPTIVE", "reason": "grounded adaptive scale rounds remain incomplete: " + ", ".join(incomplete_adaptive)})

    missing_coverage = [family for family in sorted(COVERAGE_FAMILIES) if not (root / "orchestration" / f"coverage-{family}.json").exists()]
    if missing_coverage:
        blockers.append({"gate": "SEARCH-COVERAGE", "reason": "unrecorded adversarial coverage: " + ", ".join(missing_coverage)})
    for family in sorted(COVERAGE_FAMILIES - set(missing_coverage)):
        coverage = read_json(root / "orchestration" / f"coverage-{family}.json")
        errors = verify_evidence_refs(root, coverage.get("evidence_refs", []))
        if errors:
            blockers.append({"gate": "COVERAGE-EVIDENCE", "reason": f"{family} coverage evidence invalid: {'; '.join(errors)}"})

    open_frontier = []
    for path in sorted((root / "frontier").glob("FRONTIER-*.json")):
        item = read_json(path)
        evidence_errors = verify_evidence_refs(root, item.get("grounding_refs", []))
        evidence_errors.extend(verify_evidence_refs(root, item.get("evidence_refs", [])))
        if evidence_errors:
            blockers.append({"gate": "FRONTIER-EVIDENCE", "reason": f"{item['id']} evidence invalid: {'; '.join(evidence_errors)}"})
        if item.get("scale_status") == "blocked":
            open_risks.append(
                {
                    "kind": item.get("scale_blocker_kind") or "tooling",
                    "record": item["id"],
                    "reason": f"scaling allocation blocked: {item.get('scale_blocker')}",
                }
            )
        if item.get("status") == "open" and item.get("priority") == "high" and item.get("cost") == "low":
            open_frontier.append(item["id"])
        if item.get("status") == "blocked" and item.get("priority") == "high":
            open_risks.append(
                {
                    "kind": item.get("blocker_kind") or "external-prerequisite",
                    "record": item["id"],
                    "reason": item.get("resolution_condition") or "blocked high-priority frontier",
                }
            )
    if open_frontier:
        blockers.append({"gate": "MARGINAL-GAIN", "reason": "high-priority low-cost frontier remains open: " + ", ".join(open_frontier)})

    impacts = [read_json(path) for path in sorted((root / "impact").glob("IMPACT-*.json"))]
    candidates = [read_json(path) for path in sorted((root / "candidates").glob("CAND-*.json"))]
    for candidate in candidates:
        candidate_id = candidate["id"]
        reviews = [
            read_json(root / "reviews" / f"{review_id}.json")
            for review_id in candidate.get("reviews", [])
            if (root / "reviews" / f"{review_id}.json").exists()
        ]
        independently_rejected = False
        for review in reviews:
            if not (review.get("independent") and review.get("verdict") == "rejected"):
                continue
            review_errors = verify_evidence_refs(root, review.get("evidence_refs", []))
            if review_errors or not has_strong_refuting_evidence(
                root,
                review.get("evidence_refs", []),
                expected_property=str(candidate.get("property", "")),
                expected_hypothesis_id=str(candidate.get("hypothesis_id", "")),
                expected_support_run=str(candidate.get("support_run", "")),
            ):
                blockers.append(
                    {
                        "gate": "CANDIDATE-REFUTATION",
                        "reason": f"{candidate_id} rejection {review.get('id')} lost strong artifact-bound refuting evidence"
                        + (f": {'; '.join(review_errors)}" if review_errors else ""),
                    }
                )
                continue
            independently_rejected = True
        if candidate.get("status") != "validated" and not independently_rejected:
            blockers.append({"gate": "CANDIDATE-VALIDATION", "reason": f"{candidate_id} remains unvalidated or unrefuted"})
        if candidate.get("expansion_status") == "blocked":
            open_risks.append(
                {
                    "kind": candidate.get("expansion_blocker_kind") or "tooling",
                    "record": candidate_id,
                    "reason": f"expansion allocation blocked: {candidate.get('expansion_blocker')}",
                }
            )
        expansion = [r for r in rounds if r.get("purpose") == "candidate-expansion" and r.get("candidate_id") == candidate_id]
        completed_expansion = [
            r
            for r in expansion
            if r.get("status") == "completed"
            and int(r.get("completed_lanes", 0)) == len(r.get("lanes", [])) == len(EXPANSION_AXES)
            and (root / "scale" / r["id"] / "aggregate.json").exists()
        ]
        environment_blocked_expansion = any(r.get("status") == "environment-blocked" for r in expansion)
        if not completed_expansion and candidate.get("expansion_status") != "blocked" and not environment_blocked_expansion:
            blockers.append({"gate": "IMPACT-EXTENSION", "reason": f"{candidate_id} lacks completed impact, alternate-consumer, refutation, and minimization lanes"})
        candidate_impacts = [i for i in impacts if i.get("candidate_id") == candidate_id]
        if independently_rejected:
            continue
        if not candidate_impacts:
            blockers.append({"gate": "IMPACT-GRAPH", "reason": f"{candidate_id} has no downstream consumer/sink analysis"})
        if candidate_impacts and not any(i.get("high_consequence") for i in candidate_impacts):
            blockers.append({"gate": "IMPACT-GRAPH", "reason": f"{candidate_id} has no registered high-consequence downstream sink"})
        open_impacts = [i["id"] for i in candidate_impacts if i.get("status") == "open"]
        if open_impacts:
            blockers.append({"gate": "IMPACT-GRAPH", "reason": f"{candidate_id} has unresolved impact branches: {', '.join(open_impacts)}"})
        for impact in candidate_impacts:
            evidence_errors = verify_evidence_refs(root, impact.get("evidence_refs", []))
            if evidence_errors:
                blockers.append({"gate": "IMPACT-EVIDENCE", "reason": f"{impact['id']} evidence invalid: {'; '.join(evidence_errors)}"})
            if impact.get("status") == "demonstrated" and not has_demonstration_pair(impact.get("evidence_refs", [])):
                blockers.append({"gate": "IMPACT-EVIDENCE", "reason": f"{impact['id']} lacks a supporting run and matching replay"})
            if (
                impact.get("status") == "demonstrated"
                and impact.get("high_consequence")
                and impact_control_pair(
                    root,
                    impact.get("evidence_refs", []),
                    str(impact.get("impact_property", "")),
                    expected_hypothesis_id=str(candidate.get("hypothesis_id", "")),
                    expected_candidate_id=candidate_id,
                    expected_parent_run=str(candidate.get("support_run", "")),
                ) is None
            ):
                blockers.append({"gate": "IMPACT-CONTROL", "reason": f"{impact['id']} lacks an impact-specific causal control linked to the exact downstream property"})
            if (
                impact.get("status") == "refuted"
                and impact.get("high_consequence")
                and not has_strong_refuting_evidence(
                    root,
                    impact.get("evidence_refs", []),
                    expected_property=str(impact.get("impact_property", "")),
                    expected_hypothesis_id=str(candidate.get("hypothesis_id", "")),
                    expected_candidate_id=candidate_id,
                    expected_parent_run=str(candidate.get("support_run", "")),
                )
            ):
                blockers.append({"gate": "IMPACT-REFUTATION", "reason": f"{impact['id']} high-consequence refutation lacks execution or a mechanically anchored impossibility proof"})
            if impact.get("status") == "blocked" and impact.get("high_consequence"):
                open_risks.append(
                    {
                        "kind": impact.get("blocker_kind") or "external-prerequisite",
                        "record": impact["id"],
                        "reason": impact.get("resolution_condition") or "blocked high-consequence impact",
                    }
                )
        if candidate_impacts and not any(i.get("status") in {"demonstrated", "refuted", "blocked"} for i in candidate_impacts):
            blockers.append({"gate": "TERMINAL-CONSEQUENCE", "reason": f"{candidate_id} consequence was not propagated, refuted, or bounded with evidence"})

    eligible = _eligible_handoffs(root)
    recombination = [r for r in rounds if r.get("purpose") == "recombination"]
    if eligible >= 2 and not any(r.get("status") == "completed" and int(r.get("completed_lanes", 0)) == len(r.get("lanes", [])) for r in recombination) and not any(r.get("status") == "environment-blocked" for r in recombination):
        blockers.append({"gate": "RSA", "reason": "multiple grounded components exist but no recombination generation completed"})

    kinds = {risk["kind"] for risk in open_risks}
    if blockers:
        disposition = "INCOMPLETE"
    elif not open_risks:
        disposition = "READY_CLEAN"
    elif kinds and kinds <= {"budget"}:
        disposition = "BUDGET_EXHAUSTED"
    elif kinds and kinds <= {"environment", "tooling"}:
        disposition = "ENVIRONMENT_BLOCKED"
    else:
        disposition = "COMPLETE_WITH_OPEN_RISK"
    result = {
        "schema": schema_for(root),
        "kind": "completion-assessment",
        "created_at": utc_now(),
        "ready": not blockers and not open_risks,
        "closable": not blockers,
        "disposition": disposition,
        "blockers": blockers,
        "open_risks": open_risks,
        "summary": {
            "rounds": len(rounds),
            "candidates": len(candidates),
            "impact_branches": len(impacts),
            "eligible_handoffs": eligible,
            "automatically_registered_open_research": len(sweep.get("open", [])),
            "automatically_registered_risks": len(sweep.get("risks", [])),
        },
        "resource_snapshot": resource_snapshot(root),
        "completion_hierarchy": [
            "mechanism-found",
            "candidate-demonstrated",
            "vulnerability-validated",
            "terminal-impact-demonstrated-or-bounded",
            "maximum-credible-consequence-explored",
            "campaign-complete",
        ],
    }
    write_json_atomic(root / "orchestration" / "completion-assessment.json", result)
    return result


def close_campaign(root: Path, *, conclusion: str, closure: str) -> dict[str, Any]:
    if not conclusion.strip():
        raise ValidationError("campaign conclusion must be non-empty")
    result = assess_completion(root)
    allowed = {"clean": "READY_CLEAN", "open-risk": "COMPLETE_WITH_OPEN_RISK", "budget-exhausted": "BUDGET_EXHAUSTED", "environment-blocked": "ENVIRONMENT_BLOCKED"}
    if closure not in allowed:
        raise ValidationError(f"unknown closure class: {closure}")
    if not result["closable"]:
        reasons = "; ".join(item["reason"] for item in result["blockers"])
        raise IntegrityError("campaign completion refused: " + reasons)
    if result["disposition"] != allowed[closure]:
        raise IntegrityError(f"requested {closure} closure does not match assessed disposition {result['disposition']}")
    record = {
        "schema": schema_for(root),
        "kind": "campaign-completion",
        "closed_at": utc_now(),
        "conclusion": conclusion,
        "closure": closure,
        "assessment": result,
    }
    write_json_atomic(root / "orchestration" / "completion.json", record)
    event(root, "campaign.completed")
    return record
