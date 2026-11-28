from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import digest_bytes, read_json, verify_seal
from .errors import IntegrityError, ValidationError
from .hashing import file_sha256, is_relative_to, path_digest
from .records import require_campaign, validate_id
from .replay import load_verified_replay


EVIDENCE_TYPES = {
    "run-receipt",
    "replay",
    "fork-snapshot",
    "source-anchor",
    "trace-artifact",
    "state-diff",
    "deployment-observation",
    "solver-witness",
}


def _safe_relative(value: str) -> Path:
    relative = Path(value)
    if not value or relative.is_absolute() or ".." in relative.parts:
        raise ValidationError(f"unsafe evidence path: {value}")
    return relative


def _run_receipt(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    run_id = validate_id(str(ref.get("run_id", "")), "RUN")
    run_dir = root / "runs" / run_id
    receipt_path = run_dir / "receipt.json"
    verify_seal(receipt_path, run_dir / "receipt.sha256")
    receipt = read_json(receipt_path)
    if not receipt.get("mechanical_success"):
        raise ValidationError(f"evidence run did not complete mechanically: {run_id}")
    observation_path = run_dir / "observation.json"
    observation = None
    observation_sha = None
    if observation_path.exists():
        verify_seal(observation_path, run_dir / "observation.sha256")
        observation = read_json(observation_path)
        observation_sha = digest_bytes(observation_path.read_bytes())
    expected = ref.get("outcome")
    if expected and (not observation or observation.get("outcome") != expected):
        raise ValidationError(f"run {run_id} does not have expected observation outcome {expected}")
    return {
        "type": "run-receipt",
        "run_id": run_id,
        "receipt_sha256": digest_bytes(receipt_path.read_bytes()),
        "observation_sha256": observation_sha,
        "outcome": observation.get("outcome") if observation else None,
        "property_violated": observation.get("property_violated") if observation else None,
    }


def load_verified_run_evidence(
    root: Path,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Load one run only after rechecking every promotion-relevant seal."""
    run_id = validate_id(run_id, "RUN")
    run_dir = root / "runs" / run_id
    plan_path = run_dir / "plan.json"
    receipt_path = run_dir / "receipt.json"
    observation_path = run_dir / "observation.json"
    verify_seal(plan_path, run_dir / "plan.sha256")
    verify_seal(receipt_path, run_dir / "receipt.sha256")
    verify_seal(observation_path, run_dir / "observation.sha256")
    plan = read_json(plan_path)
    receipt = read_json(receipt_path)
    observation = read_json(observation_path)
    if plan.get("id") != run_id or receipt.get("run_id") != run_id or observation.get("run_id") != run_id:
        raise IntegrityError(f"sealed run evidence has inconsistent identity: {run_id}")
    if receipt.get("plan_sha256") != digest_bytes(plan_path.read_bytes()):
        raise IntegrityError(f"receipt is not bound to the sealed plan: {run_id}")
    return plan, receipt, observation


def _replay(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    replay_id = validate_id(str(ref.get("replay_id", "")), "REPLAY")
    replay = load_verified_replay(root, replay_id)
    if not replay.get("passed"):
        raise ValidationError(f"replay did not pass: {replay_id}")
    path = root / "replays" / replay_id / "verification.json"
    return {
        "type": "replay",
        "replay_id": replay_id,
        "run_id": replay.get("run_id"),
        "sha256": digest_bytes(path.read_bytes()),
        "passed": True,
    }


def _fork_snapshot(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    fork_id = validate_id(str(ref.get("fork_id", "")), "FORK")
    snapshot_id = str(ref.get("snapshot_id", ""))
    path = root / "forks" / f"{fork_id}.json"
    record = read_json(path)
    if snapshot_id not in {str(item.get("snapshot_id")) for item in record.get("snapshots", [])}:
        raise ValidationError(f"unknown fork snapshot {fork_id}:{snapshot_id}")
    return {"type": "fork-snapshot", "fork_id": fork_id, "snapshot_id": snapshot_id, "sha256": digest_bytes(path.read_bytes())}


def _source_anchor(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    campaign = require_campaign(root)
    anchor = str(ref.get("anchor", "source"))
    if anchor not in {"source", "campaign"}:
        raise ValidationError("source-anchor anchor must be source or campaign")
    base = Path(campaign["source"]["path"]) if anchor == "source" else root
    relative = _safe_relative(str(ref.get("path", "")))
    path = (base / relative).resolve()
    if not is_relative_to(path, base) or not path.exists():
        raise ValidationError(f"source anchor does not exist inside {anchor}: {relative}")
    start = ref.get("line_start")
    end = ref.get("line_end")
    if start is not None and (not isinstance(start, int) or start <= 0):
        raise ValidationError("source anchor line_start must be a positive integer")
    if end is not None and (not isinstance(end, int) or end < int(start or 1)):
        raise ValidationError("source anchor line_end must be at least line_start")
    if path.is_dir() and (start is not None or end is not None):
        raise ValidationError("directory source anchors cannot declare line ranges")
    if path.is_file() and (start is not None or end is not None):
        content = path.read_bytes()
        line_count = content.count(b"\n") + (0 if content.endswith(b"\n") else 1)
        if int(start or 1) > line_count or int(end or start or 1) > line_count:
            raise ValidationError(f"source anchor line range exceeds file length ({line_count} lines)")
    return {
        "type": "source-anchor",
        "anchor": anchor,
        "path": relative.as_posix(),
        "line_start": start,
        "line_end": end,
        "digest": path_digest(path),
    }


def _run_artifact(root: Path, ref: dict[str, Any], evidence_type: str) -> dict[str, Any]:
    run_id = validate_id(str(ref.get("run_id", "")), "RUN")
    relative = _safe_relative(str(ref.get("path", "")))
    run_dir = (root / "runs" / run_id).resolve()
    path = (run_dir / relative).resolve()
    if not is_relative_to(path, run_dir) or not path.is_file():
        raise ValidationError(f"{evidence_type} does not exist inside {run_id}: {relative}")
    return {"type": evidence_type, "run_id": run_id, "path": relative.as_posix(), "sha256": file_sha256(path)}


def _deployment_observation(root: Path, ref: dict[str, Any]) -> dict[str, Any]:
    run_id = validate_id(str(ref.get("run_id", "")), "RUN")
    path = root / "runs" / run_id / "observation.json"
    if not path.exists():
        raise ValidationError(f"missing deployment observation for {run_id}")
    verify_seal(path, path.parent / "observation.sha256")
    observation = read_json(path)
    return {
        "type": "deployment-observation",
        "run_id": run_id,
        "sha256": digest_bytes(path.read_bytes()),
        "outcome": observation.get("outcome"),
        "property_violated": observation.get("property_violated"),
    }


def normalize_evidence_refs(root: Path, refs: list[dict[str, Any]], *, required: bool = True) -> list[dict[str, Any]]:
    require_campaign(root)
    if required and not refs:
        raise ValidationError("at least one typed evidence reference is required")
    normalized: list[dict[str, Any]] = []
    for raw in refs:
        if not isinstance(raw, dict):
            raise ValidationError("evidence references must be JSON objects")
        evidence_type = str(raw.get("type", ""))
        if evidence_type not in EVIDENCE_TYPES:
            raise ValidationError(f"unsupported evidence type: {evidence_type}")
        if evidence_type == "run-receipt":
            item = _run_receipt(root, raw)
        elif evidence_type == "replay":
            item = _replay(root, raw)
        elif evidence_type == "fork-snapshot":
            item = _fork_snapshot(root, raw)
        elif evidence_type == "source-anchor":
            item = _source_anchor(root, raw)
        elif evidence_type in {"trace-artifact", "state-diff", "solver-witness"}:
            item = _run_artifact(root, raw, evidence_type)
        else:
            item = _deployment_observation(root, raw)
        normalized.append(item)
    return normalized


def verify_evidence_refs(root: Path, refs: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for index, stored in enumerate(refs):
        try:
            checked = normalize_evidence_refs(root, [stored], required=True)[0]
            if checked != stored:
                errors.append(f"evidence[{index}] changed or no longer matches its referenced artifact")
        except (IntegrityError, ValidationError, OSError, ValueError) as exc:
            errors.append(f"evidence[{index}] invalid: {exc}")
    return errors


def has_demonstration_pair(refs: list[dict[str, Any]]) -> bool:
    supporting_runs = {
        item["run_id"]
        for item in refs
        if item.get("type") == "run-receipt" and item.get("outcome") == "supports" and item.get("property_violated") is True
    }
    replayed_runs = {item.get("run_id") for item in refs if item.get("type") == "replay" and item.get("passed")}
    return bool(supporting_runs & replayed_runs)


def has_refuting_evidence(refs: list[dict[str, Any]]) -> bool:
    if any(item.get("type") == "run-receipt" and item.get("outcome") == "refutes" for item in refs):
        return True
    return any(item.get("type") in {"source-anchor", "deployment-observation", "trace-artifact", "state-diff"} for item in refs)


def _run_plan_matches(
    root: Path,
    run_id: str,
    *,
    expected_property: str = "",
    expected_hypothesis_id: str = "",
    expected_support_run: str = "",
    expected_candidate_id: str = "",
    expected_parent_run: str = "",
) -> bool:
    run_dir = root / "runs" / run_id
    try:
        verify_seal(run_dir / "plan.json", run_dir / "plan.sha256")
        plan = read_json(run_dir / "plan.json")
    except (IntegrityError, OSError, ValueError):
        return False
    if expected_property and " ".join(str(plan.get("property", "")).split()) != " ".join(expected_property.split()):
        return False
    if expected_hypothesis_id and plan.get("hypothesis_id") != expected_hypothesis_id:
        return False
    if expected_support_run:
        contract = plan.get("control_contract")
        if (
            plan.get("run_class") != "control"
            or plan.get("control_for_run") != expected_support_run
            or not isinstance(contract, dict)
            or contract.get("support_run") != expected_support_run
            or not str(contract.get("claim", "")).strip()
            or not contract.get("changed_argv")
        ):
            return False
    if expected_candidate_id or expected_parent_run:
        if not expected_candidate_id or not expected_parent_run:
            return False
        contract = plan.get("extension_contract")
        if (
            plan.get("run_class") != "candidate"
            or not isinstance(contract, dict)
            or contract.get("candidate_id") != expected_candidate_id
            or contract.get("parent_run") != expected_parent_run
        ):
            return False
        try:
            candidate = read_json(root / "candidates" / f"{validate_id(expected_candidate_id, 'CAND')}.json")
            parent_run = validate_id(expected_parent_run, "RUN")
            parent_dir = root / "runs" / parent_run
            verify_seal(parent_dir / "plan.json", parent_dir / "plan.sha256")
            verify_seal(parent_dir / "receipt.json", parent_dir / "receipt.sha256")
            parent_plan_path = parent_dir / "plan.json"
            parent_receipt_path = parent_dir / "receipt.json"
            parent_plan = read_json(parent_plan_path)
            parent_receipt = read_json(parent_receipt_path)
            campaign = require_campaign(root)
            prefix = contract.get("prefix")
            if not isinstance(prefix, dict):
                return False
            anchor = prefix.get("anchor")
            relative = _safe_relative(str(prefix.get("path", "")))
            base = Path(campaign["source"]["path"]) if anchor == "source" else root if anchor == "campaign" else None
            if base is None:
                return False
            prefix_path = (base / relative).resolve()
            if not is_relative_to(prefix_path, base):
                return False
        except (IntegrityError, ValidationError, OSError, ValueError):
            return False
        if (
            candidate.get("hypothesis_id") != plan.get("hypothesis_id")
            or candidate.get("support_run") != parent_run
            or parent_plan.get("hypothesis_id") != plan.get("hypothesis_id")
            or not parent_receipt.get("mechanical_success")
            or contract.get("parent_plan_sha256") != digest_bytes(parent_plan_path.read_bytes())
            or contract.get("parent_receipt_sha256") != digest_bytes(parent_receipt_path.read_bytes())
            or contract.get("execution_identity") != plan.get("execution_identity")
            or prefix.get("digest") != path_digest(prefix_path)
            or prefix not in plan.get("inputs", [])
        ):
            return False
    return True


def has_strong_refuting_evidence(
    root: Path,
    refs: list[dict[str, Any]],
    *,
    expected_property: str = "",
    expected_hypothesis_id: str = "",
    expected_support_run: str = "",
    expected_candidate_id: str = "",
    expected_parent_run: str = "",
) -> bool:
    """Require execution or a mechanically anchored impossibility argument.

    This deliberately excludes a lone source excerpt. High-consequence leads
    are not closed merely because the intended guard looks persuasive.
    """
    for item in refs:
        run_id = str(item.get("run_id", ""))
        causal_artifact = any(
            other.get("type") in {"trace-artifact", "state-diff"}
            and other.get("run_id") == run_id
            for other in refs
        )
        if (
            item.get("type") == "run-receipt"
            and item.get("outcome") == "refutes"
            and item.get("property_violated") is False
            and (not (expected_support_run or expected_parent_run) or causal_artifact)
            and _run_plan_matches(
                root,
                run_id,
                expected_property=expected_property,
                expected_hypothesis_id=expected_hypothesis_id,
                expected_support_run=expected_support_run,
                expected_candidate_id=expected_candidate_id,
                expected_parent_run=expected_parent_run,
            )
        ):
            return True
    anchors = any(item.get("type") == "source-anchor" for item in refs)
    deployment_refutation = any(
        item.get("type") == "deployment-observation"
        and item.get("outcome") == "refutes"
        and item.get("property_violated") is False
        and _run_plan_matches(
            root,
            str(item.get("run_id", "")),
            expected_property=expected_property,
            expected_hypothesis_id=expected_hypothesis_id,
            expected_support_run=expected_support_run,
            expected_candidate_id=expected_candidate_id,
            expected_parent_run=expected_parent_run,
        )
        for item in refs
    )
    solver_proof = any(
        item.get("type") == "solver-witness"
        and _run_plan_matches(
            root,
            str(item.get("run_id", "")),
            expected_property=expected_property,
            expected_hypothesis_id=expected_hypothesis_id,
            expected_candidate_id=expected_candidate_id,
            expected_parent_run=expected_parent_run,
        )
        for item in refs
    )
    return anchors and (deployment_refutation or solver_proof)


def impact_control_pair(
    root: Path,
    refs: list[dict[str, Any]],
    impact_property: str,
    expected_hypothesis_id: str = "",
    expected_candidate_id: str = "",
    expected_parent_run: str = "",
) -> dict[str, str] | None:
    """Return a mechanically linked support/control pair for a downstream impact.

    A pair is impact-specific only when the downstream support plan has sealed
    lineage to the candidate's original support run, both plans test the exact
    registered downstream property and share a hypothesis, the support violates
    the property and has a passing replay, and a distinct causal control removes
    the downstream transition. Absence of a pair keeps the lead open.
    """
    expected_property = " ".join(impact_property.split())
    if not expected_property:
        return None
    supporting = {
        item["run_id"]
        for item in refs
        if item.get("type") == "run-receipt"
        and item.get("outcome") == "supports"
        and item.get("property_violated") is True
    }
    replay_by_run = {
        str(item.get("run_id")): str(item.get("replay_id"))
        for item in refs
        if item.get("type") == "replay" and item.get("passed") and item.get("run_id")
    }
    controls = {
        item["run_id"]
        for item in refs
        if item.get("type") == "run-receipt"
        and item.get("outcome") == "refutes"
        and item.get("property_violated") is False
    }
    for support_run in sorted(supporting & set(replay_by_run)):
        support_dir = root / "runs" / support_run
        try:
            verify_seal(support_dir / "plan.json", support_dir / "plan.sha256")
            support_plan = read_json(support_dir / "plan.json")
        except (IntegrityError, OSError, ValueError):
            continue
        if " ".join(str(support_plan.get("property", "")).split()) != expected_property:
            continue
        if expected_hypothesis_id and support_plan.get("hypothesis_id") != expected_hypothesis_id:
            continue
        if not _run_plan_matches(
            root,
            support_run,
            expected_property=expected_property,
            expected_hypothesis_id=expected_hypothesis_id,
            expected_candidate_id=expected_candidate_id,
            expected_parent_run=expected_parent_run,
        ):
            continue
        for control_run in sorted(controls):
            if control_run == support_run:
                continue
            control_dir = root / "runs" / control_run
            try:
                verify_seal(control_dir / "plan.json", control_dir / "plan.sha256")
                control_plan = read_json(control_dir / "plan.json")
            except (IntegrityError, OSError, ValueError):
                continue
            if control_plan.get("run_class") != "control":
                continue
            if control_plan.get("control_for_run") != support_run:
                continue
            contract = control_plan.get("control_contract")
            if (
                not isinstance(contract, dict)
                or contract.get("support_run") != support_run
                or not str(contract.get("claim", "")).strip()
                or not contract.get("changed_argv")
            ):
                continue
            control_artifacts = [
                item
                for item in refs
                if item.get("type") in {"trace-artifact", "state-diff"}
                and item.get("run_id") == control_run
            ]
            if not control_artifacts:
                continue
            if support_plan.get("hypothesis_id") != control_plan.get("hypothesis_id"):
                continue
            if " ".join(str(control_plan.get("property", "")).split()) != expected_property:
                continue
            return {
                "support_run": support_run,
                "replay_id": replay_by_run[support_run],
                "control_run": control_run,
                "control_claim": str(contract.get("claim", "")),
                "control_artifact_sha256": ",".join(sorted(str(item.get("sha256", "")) for item in control_artifacts)),
                "hypothesis_id": str(support_plan.get("hypothesis_id", "")),
                "property": expected_property,
                "candidate_id": expected_candidate_id,
                "parent_run": expected_parent_run,
            }
    return None
