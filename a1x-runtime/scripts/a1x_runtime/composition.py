from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


TOPOLOGIES = {"sequential", "nested", "temporal"}
PREDICATE_KINDS = {"state", "balance", "authority", "timing", "callback", "obligation", "other"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"component {field} must be non-empty")
    return result


def _predicates(raw: Any, field: str) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ValidationError(f"component {field} must be an array of objects")
    output = []
    ids: set[str] = set()
    for item in raw:
        predicate_id = _text(item.get("id"), f"{field}.id")
        if predicate_id in ids:
            raise ValidationError(f"duplicate component predicate: {predicate_id}")
        ids.add(predicate_id)
        kind = str(item.get("kind") or "other")
        if kind not in PREDICATE_KINDS:
            raise ValidationError(f"unsupported component predicate kind: {kind}")
        output.append(
            {
                "id": predicate_id,
                "kind": kind,
                "predicate": _text(item.get("predicate"), f"{field}.predicate"),
                "value": _text(item.get("value"), f"{field}.value"),
            }
        )
    return output


def create_component_contract(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "three_mode_rsa"):
        raise ValidationError("component contracts are disabled by runtime feature policy")
    if not isinstance(payload, dict):
        raise ValidationError("component payload must be an object")
    evidence_refs = normalize_evidence_refs(root, payload.get("evidence_refs", []), required=True)
    component_id = allocate_id(root, "COMP")
    record = {
        "schema": schema_for(root),
        "kind": "executable-component-contract",
        "id": component_id,
        "created_at": utc_now(),
        "name": _text(payload.get("name"), "name"),
        "lineage_id": _text(payload.get("lineage_id"), "lineage_id"),
        "target_identity": _text(payload.get("target_identity"), "target_identity"),
        "actor_capabilities": [str(item).strip() for item in payload.get("actor_capabilities", []) if str(item).strip()],
        "preconditions": _predicates(payload.get("preconditions", []), "preconditions"),
        "effects": _predicates(payload.get("effects", []), "effects"),
        "resources_consumed": _predicates(payload.get("resources_consumed", []), "resources_consumed"),
        "obligations_created": _predicates(payload.get("obligations_created", []), "obligations_created"),
        "invalidates": [str(item).strip() for item in payload.get("invalidates", []) if str(item).strip()],
        "transaction_context": _text(payload.get("transaction_context"), "transaction_context"),
        "callback_context": str(payload.get("callback_context") or "").strip() or None,
        "temporal_context": str(payload.get("temporal_context") or "").strip() or None,
        "evidence_refs": evidence_refs,
    }
    if not record["actor_capabilities"]:
        raise ValidationError("component contract requires explicit actor capabilities")
    if not record["effects"]:
        raise ValidationError("component contract requires at least one observed effect")
    write_json_atomic(root / "compositions" / f"{component_id}.json", record)
    event(root, "composition.component-created", component_id=component_id, lineage_id=record["lineage_id"])
    return record


def _predicate_map(component: dict[str, Any], field: str) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in component.get(field, [])}


def compose_components(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    topology = str(payload.get("topology") or "")
    if topology not in TOPOLOGIES:
        raise ValidationError(f"unsupported composition topology: {topology}")
    left_id = validate_id(_text(payload.get("left_component"), "left_component"), "COMP")
    right_id = validate_id(_text(payload.get("right_component"), "right_component"), "COMP")
    if left_id == right_id:
        raise ValidationError("composition requires two distinct components")
    left = read_json(root / "compositions" / f"{left_id}.json")
    right = read_json(root / "compositions" / f"{right_id}.json")
    if left["target_identity"] != right["target_identity"]:
        raise ValidationError("component target identities differ")
    checks_raw = payload.get("precondition_checks")
    if not isinstance(checks_raw, list) or any(not isinstance(item, dict) for item in checks_raw):
        raise ValidationError("composition precondition_checks must be an array of objects")
    checks = []
    right_preconditions = _predicate_map(right, "preconditions")
    left_effects = _predicate_map(left, "effects")
    seen: set[str] = set()
    for item in checks_raw:
        prerequisite_id = _text(item.get("precondition_id"), "precondition_check.precondition_id")
        if prerequisite_id not in right_preconditions or prerequisite_id in seen:
            raise ValidationError(f"composition precondition check is unknown or duplicated: {prerequisite_id}")
        seen.add(prerequisite_id)
        supplied_by = str(item.get("supplied_by") or "")
        if supplied_by != "initial-state" and supplied_by not in left_effects:
            raise ValidationError(f"composition precondition {prerequisite_id} has no left effect or initial-state basis")
        refs = normalize_evidence_refs(root, item.get("evidence_refs", []), required=True)
        checks.append(
            {
                "precondition_id": prerequisite_id,
                "supplied_by": supplied_by,
                "passed": item.get("passed") is True,
                "observed": _text(item.get("observed"), "precondition_check.observed"),
                "evidence_refs": refs,
            }
        )
    missing = set(right_preconditions) - seen
    if missing:
        raise ValidationError(f"composition did not check right-component preconditions: {sorted(missing)}")
    if any(not item["passed"] for item in checks):
        raise ValidationError("composition cannot be promoted while a checked precondition is false")
    invalidated = sorted(set(left.get("invalidates", [])) & set(right_preconditions))
    if invalidated:
        raise ValidationError(f"left component explicitly invalidates right preconditions: {invalidated}")
    details = payload.get("topology_details")
    if not isinstance(details, dict):
        raise ValidationError("composition topology_details must be an object")
    normalized_details: dict[str, Any]
    if topology == "sequential":
        normalized_details = {
            "left_transaction": int(details.get("left_transaction", 0)),
            "right_transaction": int(details.get("right_transaction", 1)),
        }
        if normalized_details["left_transaction"] >= normalized_details["right_transaction"]:
            raise ValidationError("sequential composition requires left before right")
    elif topology == "nested":
        continuation_id = validate_id(_text(details.get("continuation_id"), "nested.continuation_id"), "CONT")
        continuation = read_json(root / "continuations" / f"{continuation_id}.json")
        if continuation.get("checkpoint", {}).get("kind") != "transaction-waypoint":
            raise ValidationError("nested composition requires a within-transaction continuation waypoint")
        normalized_details = {
            "continuation_id": continuation_id,
            "insertion": _text(details.get("insertion"), "nested.insertion"),
            "outer_prefix": _text(details.get("outer_prefix"), "nested.outer_prefix"),
            "outer_suffix": _text(details.get("outer_suffix"), "nested.outer_suffix"),
        }
    else:
        delay_kind = str(details.get("delay_kind") or "")
        if delay_kind not in {"seconds", "blocks", "epoch", "keeper"}:
            raise ValidationError("temporal composition requires seconds/blocks/epoch/keeper delay_kind")
        amount = details.get("amount")
        if not isinstance(amount, int) or amount < 0:
            raise ValidationError("temporal composition delay amount must be non-negative")
        normalized_details = {
            "delay_kind": delay_kind,
            "amount": amount,
            "transition": _text(details.get("transition"), "temporal.transition"),
        }
    run_id = validate_id(_text(payload.get("run_id"), "run_id"), "RUN")
    replay_id = validate_id(_text(payload.get("replay_id"), "replay_id"), "REPLAY")
    replay = read_json(root / "replays" / f"{replay_id}.json")
    if replay.get("run_id") != run_id or replay.get("passed") is not True:
        raise ValidationError("composition requires a passing replay of its exact execution run")
    refs = normalize_evidence_refs(root, payload.get("evidence_refs", []), required=True)
    if not any(item.get("type") == "run-receipt" and item.get("run_id") == run_id for item in refs):
        raise ValidationError("composition evidence requires its execution run receipt")
    if not any(item.get("type") == "replay" and item.get("replay_id") == replay_id for item in refs):
        raise ValidationError("composition evidence requires its clean replay")
    actor_program_id = payload.get("actor_program_id")
    if actor_program_id is not None:
        actor_program_id = validate_id(str(actor_program_id), "ACTORS")
        actor_program = read_json(root / "actors" / f"{actor_program_id}.json")
        if actor_program.get("status") != "executed":
            raise ValidationError("composition actor program has not been executed and replayed")
    composition_id = allocate_id(root, "COMPOSE")
    record = {
        "schema": schema_for(root),
        "kind": "executable-composition",
        "id": composition_id,
        "created_at": utc_now(),
        "topology": topology,
        "left_component": left_id,
        "right_component": right_id,
        "precondition_checks": checks,
        "topology_details": normalized_details,
        "run_id": run_id,
        "replay_id": replay_id,
        "actor_program_id": actor_program_id,
        "evidence_refs": refs,
        "status": "executed",
    }
    write_json_atomic(root / "compositions" / f"{composition_id}.json", record)
    event(root, "composition.executed", composition_id=composition_id, topology=topology, run_id=run_id)
    return record


def verify_composition(root: Path, composition_id: str) -> dict[str, Any]:
    composition_id = validate_id(composition_id, "COMPOSE")
    record = read_json(root / "compositions" / f"{composition_id}.json")
    errors = verify_evidence_refs(root, record.get("evidence_refs", []))
    for check in record.get("precondition_checks", []):
        errors.extend(verify_evidence_refs(root, check.get("evidence_refs", [])))
    for component_id in (record.get("left_component"), record.get("right_component")):
        path = root / "compositions" / f"{component_id}.json"
        if not path.is_file():
            errors.append(f"component is missing: {component_id}")
    replay = root / "replays" / f"{record.get('replay_id')}.json"
    if not replay.is_file() or read_json(replay).get("passed") is not True:
        errors.append("composition replay is missing or no longer passing")
    return {"composition_id": composition_id, "valid": not errors, "errors": errors, "record": record}
