from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifacts import verify_artifact
from .atomic import digest_json, read_json, write_json_atomic
from .errors import ValidationError
from .modern_evm import validate_execution_context
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now

PAYLOAD_TYPES = {
    "transaction-witness", "state-prefix", "coverage-gap", "solver-constraint",
    "unreachability-evidence", "recon-fact", "failed-experiment", "oracle-definition",
    "semantic-waypoint", "impact-extension",
}
EVIDENCE_LEVELS = {"E0": 0, "E1": 1, "E2": 2, "E3": 3, "E4": 4, "E5": 5, "E6": 6}
EXECUTION_TYPES = {"transaction-witness", "state-prefix", "failed-experiment", "semantic-waypoint", "impact-extension"}


def validate_bundle(value: dict[str, Any], *, root: Path | None = None) -> dict[str, Any]:
    payload_type = value.get("payload_type")
    if payload_type not in PAYLOAD_TYPES:
        raise ValidationError(f"unknown EvidenceBundle payload_type: {payload_type}")
    for field in ("observation", "interpretation", "producer", "backend", "backend_version", "target_sha256"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            raise ValidationError(f"EvidenceBundle.{field} must be non-empty")
    if value["observation"].strip() == value["interpretation"].strip():
        raise ValidationError("observation and interpretation must be independently stated")
    level = value.get("evidence_level")
    if level not in EVIDENCE_LEVELS:
        raise ValidationError("EvidenceBundle.evidence_level must be E0..E6")
    payload = value.get("payload")
    if not isinstance(payload, dict) or not payload:
        raise ValidationError("EvidenceBundle.payload must be a non-empty object")
    refs = value.get("artifact_ids", [])
    if not isinstance(refs, list) or any(not isinstance(item, str) for item in refs):
        raise ValidationError("EvidenceBundle.artifact_ids must be strings")
    if payload_type in EXECUTION_TYPES and EVIDENCE_LEVELS[level] >= EVIDENCE_LEVELS["E3"] and not refs:
        raise ValidationError("execution-grounded E3+ evidence requires an immutable artifact")
    if level == "E6" and payload_type != "impact-extension":
        raise ValidationError("E6 is reserved for independently reviewed impact evidence")
    if level == "E6":
        for field in ("candidate_id", "replay_id", "blind_review_id"):
            if not isinstance(value.get(field), str) or not value[field].strip():
                raise ValidationError(f"E6 EvidenceBundle requires {field}")
        if root is not None:
            from .blind_review import qualifies

            candidate = read_json(root / "candidates" / f"{value['candidate_id']}.json")
            replay = read_json(root / "replays" / f"{value['replay_id']}.json")
            if candidate.get("replay_id") != value["replay_id"] or replay.get("passed") is not True:
                raise ValidationError("E6 EvidenceBundle requires the candidate's passing clean replay")
            if not qualifies(root, value["blind_review_id"], value["candidate_id"]):
                raise ValidationError("E6 EvidenceBundle requires a qualifying mechanically blind review")
    context = value.get("execution_context")
    if context is not None:
        validate_execution_context(context)
    elif payload_type in EXECUTION_TYPES:
        raise ValidationError(f"{payload_type} requires execution_context")
    budget = value.get("resource_budget")
    if not isinstance(budget, dict) or not budget:
        raise ValidationError("EvidenceBundle.resource_budget is required")
    return value


def create_bundle(root: Path, value: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    body = validate_bundle(dict(value), root=root)
    for artifact_id in body.get("artifact_ids", []):
        if not (root / "evidence" / f"{artifact_id}.json").is_file():
            raise ValidationError(f"unknown immutable artifact: {artifact_id}")
        if not verify_artifact(root, artifact_id)["valid"]:
            raise ValidationError(f"immutable artifact failed verification: {artifact_id}")
    bundle_id = allocate_id(root, "EVIDENCE")
    record = {
        "schema": schema_for(root), "kind": "evidence-bundle", "id": bundle_id,
        "created_at": utc_now(), **body,
    }
    record["bundle_sha256"] = digest_json(record)
    write_json_atomic(root / "evidence" / "bundles" / f"{bundle_id}.json", record)
    event(root, "evidence.created", evidence_id=bundle_id, payload_type=record["payload_type"], evidence_level=record["evidence_level"])
    return record


def load_bundle(root: Path, bundle_id: str) -> dict[str, Any]:
    return read_json(root / "evidence" / "bundles" / f"{bundle_id}.json")


def verify_bundle(root: Path, bundle_id: str) -> dict[str, Any]:
    record = load_bundle(root, bundle_id)
    claimed = record.get("bundle_sha256")
    body = dict(record)
    body.pop("bundle_sha256", None)
    errors: list[str] = []
    try:
        validate_bundle(body, root=root)
    except ValidationError as exc:
        errors.append(str(exc))
    if digest_json(body) != claimed:
        errors.append("bundle hash mismatch")
    for artifact_id in record.get("artifact_ids", []):
        if not (root / "evidence" / f"{artifact_id}.json").is_file():
            errors.append(f"missing artifact record: {artifact_id}")
        else:
            if not verify_artifact(root, artifact_id)["valid"]:
                errors.append(f"artifact content mismatch: {artifact_id}")
    return {"evidence_id": bundle_id, "valid": not errors, "errors": errors, "bundle_sha256": claimed}
