from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import exclusive_lock, read_json, write_json_atomic
from .completion_sweep import sweep_research_state
from .errors import IntegrityError, ValidationError
from .evidence import has_demonstration_pair, has_refuting_evidence, has_strong_refuting_evidence, impact_control_pair, normalize_evidence_refs, verify_evidence_refs
from .records import allocate_id, event, require_campaign, schema_for, utc_now
from .scheduling import resource_snapshot


COVERAGE_FAMILIES = {"value", "authority", "lifecycle", "numeric", "composition"}
BLOCKER_KINDS = {"budget", "environment", "external-prerequisite", "tooling"}




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
    from .ledger import require_scope_impact

    scope_id = str(candidate.get("scope_id") or "")
    eligible_impact = str(candidate.get("eligible_impact") or "")
    require_scope_impact(root, scope_id, eligible_impact)
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
        "scope_id": scope_id,
        "eligible_impact": eligible_impact,
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
    ledger_investigation_id = str(candidate.get("ledger_investigation_id") or "")
    if ledger_investigation_id:
        from .ledger import link_runtime_ref

        link_runtime_ref(
            root,
            ledger_investigation_id,
            f"impact/{impact_id}.json",
            expected_kind="INV",
            reason=f"linked downstream impact branch {impact_id}",
        )
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
    from .ledger import load_ledger, verify_ledger

    try:
        verify_ledger(root)
        ledger = load_ledger(root)
    except (IntegrityError, ValidationError) as exc:
        ledger = {"records": {}}
        blockers.append({"gate": "LEDGER-INTEGRITY", "reason": str(exc)})
    ledger_records = list(ledger.get("records", {}).values())
    scopes = [item for item in ledger_records if item.get("kind") == "SCOPE" and item.get("status") == "active"]
    if not scopes:
        blockers.append({"gate": "PROGRAM-SCOPE", "reason": "no active program scope and impact record exists"})
    elif not any(isinstance(item.get("data", {}).get("impacts"), list) and item["data"]["impacts"] for item in scopes):
        blockers.append({"gate": "PROGRAM-IMPACTS", "reason": "program scope does not enumerate the exact eligible impact classes"})
    eligible_scope_impacts = {
        (str(item["id"]), str(impact))
        for item in scopes
        for impact in item.get("data", {}).get("impacts", [])
    }
    open_ledger = [
        item["id"] for item in ledger_records
        if item.get("kind") in {"INV", "TASK", "EXP"}
        and item.get("status") in {"open", "active"}
        and item.get("priority") in {"high", "critical"}
        and item.get("data", {}).get("cost", "low") in {"low", "medium"}
    ]
    if open_ledger:
        blockers.append({"gate": "MARGINAL-GAIN", "reason": "high-value bounded ledger work remains open: " + ", ".join(open_ledger)})
    for item in ledger_records:
        if item.get("status") == "blocked" and item.get("priority") in {"high", "critical"}:
            open_risks.append({"kind": "external-prerequisite", "record": item["id"], "reason": item.get("next_action") or item["statement"]})

    for path in sorted((root / "forks").glob("FORK-*.json")):
        fork = read_json(path)
        if fork.get("status") == "running":
            blockers.append({"gate": "PROCESS-CLEANUP", "reason": f"session-owned Anvil fork is still running: {fork.get('id')} (pid {fork.get('supervisor_pid')})"})

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
        candidate_scope_impact = (
            str(candidate.get("scope_id") or ""),
            str(candidate.get("eligible_impact") or ""),
        )
        if candidate_scope_impact not in eligible_scope_impacts:
            blockers.append({
                "gate": "PROGRAM-IMPACT-MAPPING",
                "reason": f"{candidate_id} does not reference one exact eligible impact under an active SCOPE record",
            })
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
        elif candidate.get("status") == "validated" and not independently_rejected:
            try:
                from .candidates import check_gates

                current_gates = check_gates(root, candidate_id)
                if current_gates.get("mechanical_evidence_ceiling") != "E6":
                    blockers.append({
                        "gate": "CANDIDATE-REVALIDATION",
                        "reason": f"{candidate_id} no longer passes its current sealed E0-E6 evidence chain",
                    })
            except (IntegrityError, ValidationError, OSError, ValueError) as exc:
                blockers.append({
                    "gate": "CANDIDATE-REVALIDATION",
                    "reason": f"{candidate_id} evidence could not be revalidated: {exc}",
                })
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
            if (
                str(impact.get("scope_id") or ""),
                str(impact.get("eligible_impact") or ""),
            ) != candidate_scope_impact:
                blockers.append({
                    "gate": "PROGRAM-IMPACT-MAPPING",
                    "reason": f"{impact['id']} is not bound to {candidate_id}'s exact eligible impact",
                })
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
            "legacy_rounds_preserved": len(_rounds(root)),
            "candidates": len(candidates),
            "impact_branches": len(impacts),
            "ledger_records": len(ledger_records),
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
