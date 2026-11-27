from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import exclusive_lock, read_json, verify_seal, write_json_atomic
from .evidence import has_strong_refuting_evidence, normalize_evidence_refs
from .errors import A1XError, BudgetError, ValidationError
from .records import LEGACY_RUNTIME_SCHEMA, allocate_id, event, require_campaign, schema_for, update_research_counter, utc_now


def _require(path: Path, description: str) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"missing {description}: {path.stem}")
    return read_json(path)


def create_candidate(
    root: Path,
    *,
    hypothesis_id: str,
    support_run: str,
    control_run: str | None,
    replay_id: str | None,
    root_cause: str,
    code_evidence: str,
    reachability: str,
    property_statement: str,
    impact: str,
    implementation_verified: bool,
    configuration_verified: bool,
    actor_verified: bool,
    economics_verified: bool,
    consequence_class: str = "unknown",
    terminal_impact: bool = False,
) -> dict[str, Any]:
    require_campaign(root)
    if any(not value.strip() for value in (root_cause, code_evidence, reachability, property_statement, impact)):
        raise ValidationError("candidate mechanism, code evidence, reachability, property, and impact must be non-empty")
    terminal_classes = {"asset-loss", "insolvency", "permanent-freeze", "integrity"}
    if terminal_impact and consequence_class not in terminal_classes:
        raise ValidationError("terminal impact cannot be declared for an intermediate authorization, governance, configuration, upgrade, role, liveness, or unknown consequence")
    _require(root / "hypotheses" / f"{hypothesis_id}.json", "hypothesis")
    _require(root / "runs" / support_run / "receipt.json", "supporting run")
    if control_run:
        _require(root / "runs" / control_run / "receipt.json", "control run")
    if replay_id:
        _require(root / "replays" / f"{replay_id}.json", "replay")
    candidate_id = allocate_id(root, "CAND")
    record = {
        "schema": schema_for(root),
        "kind": "candidate",
        "id": candidate_id,
        "created_at": utc_now(),
        "hypothesis_id": hypothesis_id,
        "support_run": support_run,
        "control_run": control_run,
        "replay_id": replay_id,
        "root_cause": root_cause,
        "code_evidence": code_evidence,
        "reachability": reachability,
        "property": property_statement,
        "impact": impact,
        "consequence_class": consequence_class,
        "terminal_impact": terminal_impact,
        "expansion_round": None,
        "expansion_status": "pending",
        "expansion_blocker": None,
        "expansion_blocker_kind": None,
        "fidelity": {
            "implementation_verified": implementation_verified,
            "configuration_verified": configuration_verified,
            "actor_verified": actor_verified,
            "economics_verified": economics_verified,
        },
        "reviews": [],
        "status": "candidate",
    }
    candidate_path = root / "candidates" / f"{candidate_id}.json"
    write_json_atomic(candidate_path, record)
    event(root, "candidate.created", candidate_id=candidate_id, hypothesis_id=hypothesis_id)
    # A candidate is a branch point, not a campaign stopping condition. Creating
    # it mechanically opens independent impact, variant, refutation, and
    # minimization lanes so a partial capability cannot silently terminate TTS.
    from .controller import ensure_candidate_expansion

    try:
        expansion = ensure_candidate_expansion(root, candidate_id)
    except A1XError as exc:
        # Evidence-bearing records survive orchestration and budget failures.
        record["expansion_status"] = "blocked"
        record["expansion_blocker"] = f"{type(exc).__name__}: {exc}"
        record["expansion_blocker_kind"] = "budget" if isinstance(exc, BudgetError) else "tooling"
        write_json_atomic(candidate_path, record)
        event(root, "candidate.expansion-allocation-blocked", candidate_id=candidate_id, error_type=type(exc).__name__)
        return record
    except Exception as exc:
        record["expansion_status"] = "blocked"
        record["expansion_blocker"] = f"unexpected {type(exc).__name__}: {exc}"
        record["expansion_blocker_kind"] = "tooling"
        write_json_atomic(candidate_path, record)
        event(root, "candidate.expansion-allocation-error", candidate_id=candidate_id, error_type=type(exc).__name__)
        raise
    record["expansion_round"] = expansion["id"]
    record["expansion_status"] = "allocated"
    record["expansion_blocker"] = None
    record["expansion_blocker_kind"] = None
    write_json_atomic(candidate_path, record)
    return record


def add_review(
    root: Path,
    *,
    candidate_id: str,
    reviewer: str,
    verdict: str,
    notes: str,
    independent: bool,
    evidence_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    require_campaign(root)
    if verdict not in {"confirmed", "rejected", "needs-work"}:
        raise ValidationError(f"invalid review verdict: {verdict}")
    candidate_path = root / "candidates" / f"{candidate_id}.json"
    candidate = _require(candidate_path, "candidate")
    evidence = normalize_evidence_refs(root, evidence_refs or [], required=False)
    requested_verdict: str | None = None
    promotion_status = "satisfied"
    promotion_blocker: str | None = None
    if verdict == "rejected" and not has_strong_refuting_evidence(
        root,
        evidence,
        expected_property=str(candidate.get("property", "")),
        expected_hypothesis_id=str(candidate.get("hypothesis_id", "")),
        expected_support_run=str(candidate.get("support_run", "")),
    ):
        # A review can expose uncertainty without erasing an executed lead.
        # Terminal rejection needs a mechanism-specific negative execution or
        # an artifact-bound impossibility proof.
        requested_verdict = "rejected"
        verdict = "needs-work"
        promotion_status = "deferred"
        promotion_blocker = "candidate rejection lacks strong refuting evidence; lead retained for adversarial continuation"
    review_id = allocate_id(root, "REVIEW")
    record = {
        "schema": schema_for(root),
        "kind": "candidate-review",
        "id": review_id,
        "created_at": utc_now(),
        "candidate_id": candidate_id,
        "reviewer": reviewer,
        "verdict": verdict,
        "notes": notes,
        "independent": independent,
        "requested_verdict": requested_verdict,
        "promotion_status": promotion_status,
        "promotion_blocker": promotion_blocker,
        "evidence_refs": evidence,
    }
    write_json_atomic(root / "reviews" / f"{review_id}.json", record)
    with exclusive_lock(root):
        candidate = _require(candidate_path, "candidate")
        candidate.setdefault("reviews", []).append(review_id)
        write_json_atomic(candidate_path, candidate)
    event(root, "candidate.reviewed", candidate_id=candidate_id, review_id=review_id, verdict=verdict)
    return record


def _run_evidence(root: Path, run_id: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not run_id:
        return None, None
    run_dir = root / "runs" / run_id
    receipt = read_json(run_dir / "receipt.json") if (run_dir / "receipt.json").exists() else None
    observation = read_json(run_dir / "observation.json") if (run_dir / "observation.json").exists() else None
    return receipt, observation


def check_gates(root: Path, candidate_id: str) -> dict[str, Any]:
    campaign = require_campaign(root)
    candidate = _require(root / "candidates" / f"{candidate_id}.json", "candidate")
    support_receipt, support_observation = _run_evidence(root, candidate.get("support_run"))
    control_receipt, control_observation = _run_evidence(root, candidate.get("control_run"))
    replay = read_json(root / "replays" / f"{candidate['replay_id']}.json") if candidate.get("replay_id") else None
    reviews = [read_json(root / "reviews" / f"{review_id}.json") for review_id in candidate.get("reviews", [])]
    paired_control = False
    if candidate.get("support_run") and candidate.get("control_run"):
        support_dir = root / "runs" / str(candidate["support_run"])
        control_dir = root / "runs" / str(candidate["control_run"])
        try:
            verify_seal(support_dir / "plan.json", support_dir / "plan.sha256")
            verify_seal(control_dir / "plan.json", control_dir / "plan.sha256")
            support_plan = read_json(support_dir / "plan.json")
            control_plan = read_json(control_dir / "plan.json")
            control_contract = control_plan.get("control_contract")
            paired_control = (
                control_plan.get("run_class") == "control"
                and control_plan.get("control_for_run") == candidate.get("support_run")
                and isinstance(control_contract, dict)
                and control_contract.get("support_run") == candidate.get("support_run")
                and bool(str(control_contract.get("claim", "")).strip())
                and bool(control_contract.get("changed_argv"))
                and control_plan.get("hypothesis_id") == support_plan.get("hypothesis_id") == candidate.get("hypothesis_id")
                and " ".join(str(control_plan.get("property", "")).split())
                == " ".join(str(support_plan.get("property", "")).split())
                == " ".join(str(candidate.get("property", "")).split())
            )
        except (A1XError, OSError, ValueError):
            paired_control = False
    if campaign.get("schema") == LEGACY_RUNTIME_SCHEMA:
        independent_review = any(r.get("independent") and r.get("verdict") == "confirmed" for r in reviews)
        review_requirement = "legacy declared independent confirming review"
    else:
        from .blind_review import qualifies

        independent_review = any(qualifies(root, review_id, candidate_id) for review_id in candidate.get("blind_reviews", []))
        review_requirement = "fresh-process mechanically blind confirming review"
    gates = [
        ("E0", bool(candidate.get("root_cause") and candidate.get("hypothesis_id")), "recorded mechanism and hypothesis"),
        ("E1", bool(candidate.get("code_evidence")), "exact writer/guard/consumer code evidence recorded"),
        (
            "E2",
            bool(candidate.get("reachability")),
            "reachable sequence with actor and prerequisite justification recorded",
        ),
        (
            "E3",
            bool(support_receipt and support_receipt.get("mechanical_success") and support_observation and support_observation.get("outcome") == "supports"),
            "concrete execution reached the predicted suspicious state",
        ),
        (
            "E4",
            bool(
                support_observation
                and support_observation.get("property_violated") is True
                and candidate.get("impact")
                and control_receipt
                and control_receipt.get("mechanical_success")
                and control_observation
                and control_observation.get("outcome") == "refutes"
                and control_observation.get("property_violated") is False
                and paired_control
            ),
            "protocol property violation plus explicitly paired causal negative control",
        ),
        ("E5", all(candidate.get("fidelity", {}).values()), "implementation, configuration, actor, and economics fidelity verified"),
        (
            "E6",
            bool(replay and replay.get("passed") and independent_review),
            f"clean mechanical replay plus {review_requirement}",
        ),
    ]
    highest = "none"
    details = []
    chain_intact = True
    for level, passed, requirement in gates:
        chain_intact = chain_intact and passed
        details.append({"level": level, "requirement_met": passed, "promoted": chain_intact, "requirement": requirement})
        if chain_intact:
            highest = level
    return {
        "candidate_id": candidate_id,
        "mechanical_evidence_ceiling": highest,
        "gates": details,
        "warning": "These gates check artifact structure and declared review outcomes; they do not establish semantic truth or bounty eligibility.",
    }


def promote_validated(root: Path, candidate_id: str) -> dict[str, Any]:
    result = check_gates(root, candidate_id)
    if result["mechanical_evidence_ceiling"] != "E6":
        raise ValidationError("candidate has not passed every E0-E6 gate")
    path = root / "candidates" / f"{candidate_id}.json"
    changed = False
    with exclusive_lock(root):
        candidate = read_json(path)
        if candidate.get("status") != "validated":
            candidate["status"] = "validated"
            candidate["validated_at"] = utc_now()
            write_json_atomic(path, candidate)
            changed = True
    if changed:
        update_research_counter(root, "validated_root_causes")
        event(root, "candidate.validated", candidate_id=candidate_id)
    return candidate
