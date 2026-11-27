from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import digest_json, read_json, write_json_atomic
from .errors import IntegrityError, ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


EXECUTION_TOPOLOGIES = {
    "atomic",
    "nested-atomic",
    "multi-transaction",
    "temporal",
    "multi-actor",
}
CHECKPOINT_KINDS = {"transaction-checkpoint", "transaction-waypoint"}
CLOSURE_MODES = {"witness", "reachability"}
WRITER_KINDS = {"static", "dynamic", "external", "callback", "derived"}
WRITER_STATES = {"observed", "possible", "unknown", "contradicted"}
ATTEMPT_RESULTS = {"advanced", "narrowed", "resolved", "refuted", "blocked", "operational-failure"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"continuation {field} must be non-empty")
    return result


def _objects(value: Any, field: str, *, required: bool = True) -> list[dict[str, Any]]:
    if not isinstance(value, list) or (required and not value) or any(not isinstance(item, dict) for item in value):
        qualifier = "non-empty " if required else ""
        raise ValidationError(f"continuation {field} must be a {qualifier}array of objects")
    return [dict(item) for item in value]


def _run_record(root: Path, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    run_id = validate_id(run_id, "RUN")
    run_dir = root / "runs" / run_id
    plan = read_json(run_dir / "plan.json")
    receipt = read_json(run_dir / "receipt.json")
    if not receipt.get("mechanical_success"):
        raise ValidationError(f"continuation parent run did not complete mechanically: {run_id}")
    return plan, receipt


def _normalize_actors(raw: Any) -> list[dict[str, Any]]:
    actors = _objects(raw, "actors")
    normalized = []
    seen: set[str] = set()
    for actor in actors:
        actor_id = _text(actor.get("id"), "actor.id")
        if actor_id in seen:
            raise ValidationError(f"duplicate continuation actor id: {actor_id}")
        seen.add(actor_id)
        capabilities = actor.get("capabilities")
        if not isinstance(capabilities, list) or not capabilities or any(not str(item).strip() for item in capabilities):
            raise ValidationError(f"actor {actor_id} requires explicit capabilities")
        normalized.append(
            {
                "id": actor_id,
                "role": _text(actor.get("role"), "actor.role"),
                "address": str(actor.get("address") or "").strip() or None,
                "capabilities": [str(item).strip() for item in capabilities],
                "authority_basis": _text(actor.get("authority_basis"), "actor.authority_basis"),
            }
        )
    return normalized


def _normalize_transactions(raw: Any, actor_ids: set[str]) -> list[dict[str, Any]]:
    transactions = _objects(raw, "transactions")
    normalized = []
    for index, transaction in enumerate(transactions):
        declared = transaction.get("index")
        if declared != index:
            raise ValidationError("continuation transaction indices must be contiguous and zero-based")
        actor = _text(transaction.get("actor"), "transaction.actor")
        if actor not in actor_ids:
            raise ValidationError(f"transaction {index} references unknown actor: {actor}")
        boundary = str(transaction.get("boundary") or "transaction").strip()
        if boundary not in {"transaction", "callback", "time", "block", "external-action"}:
            raise ValidationError(f"unsupported transaction boundary: {boundary}")
        normalized.append(
            {
                "index": index,
                "actor": actor,
                "action": _text(transaction.get("action"), "transaction.action"),
                "boundary": boundary,
                "expected_effects": [str(item).strip() for item in transaction.get("expected_effects", []) if str(item).strip()],
                "obligations_created": [str(item).strip() for item in transaction.get("obligations_created", []) if str(item).strip()],
            }
        )
    return normalized


def _normalize_assertions(root: Path, raw: Any) -> list[dict[str, Any]]:
    assertions = _objects(raw, "assertions")
    normalized = []
    seen: set[str] = set()
    for assertion in assertions:
        assertion_id = _text(assertion.get("id"), "assertion.id")
        if assertion_id in seen:
            raise ValidationError(f"duplicate continuation assertion id: {assertion_id}")
        seen.add(assertion_id)
        refs = normalize_evidence_refs(root, assertion.get("evidence_refs", []), required=True)
        normalized.append(
            {
                "id": assertion_id,
                "predicate": _text(assertion.get("predicate"), "assertion.predicate"),
                "expected": _text(assertion.get("expected"), "assertion.expected"),
                "scope": _text(assertion.get("scope"), "assertion.scope"),
                "required": assertion.get("required") is not False,
                "evidence_refs": refs,
            }
        )
    return normalized


def _normalize_checkpoint(root: Path, raw: Any, parent_run: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("continuation checkpoint must be an object")
    kind = str(raw.get("kind") or "").strip()
    if kind not in CHECKPOINT_KINDS:
        raise ValidationError(f"unsupported continuation checkpoint kind: {kind}")
    transaction_index = raw.get("transaction_index")
    if not isinstance(transaction_index, int) or transaction_index < 0:
        raise ValidationError("continuation checkpoint transaction_index must be non-negative")
    waypoint = None
    if kind == "transaction-waypoint":
        value = raw.get("waypoint")
        if not isinstance(value, dict):
            raise ValidationError("a transaction waypoint requires waypoint metadata")
        frame_path = value.get("frame_path")
        if not isinstance(frame_path, list) or any(not isinstance(item, int) or item < 0 for item in frame_path):
            raise ValidationError("waypoint frame_path must contain non-negative call-frame indices")
        program_counter = value.get("program_counter")
        occurrence = value.get("occurrence")
        if not isinstance(program_counter, int) or program_counter < 0 or not isinstance(occurrence, int) or occurrence <= 0:
            raise ValidationError("waypoint program_counter/occurrence are invalid")
        refs = normalize_evidence_refs(root, value.get("evidence_refs", []), required=True)
        if not any(item.get("type") == "trace-artifact" and item.get("run_id") == parent_run for item in refs):
            raise ValidationError("a transaction waypoint requires a trace artifact from the parent top-level run")
        waypoint = {
            "frame_path": frame_path,
            "program_counter": program_counter,
            "occurrence": occurrence,
            "description": _text(value.get("description"), "waypoint.description"),
            "evidence_refs": refs,
        }
    elif raw.get("waypoint") not in (None, {}):
        raise ValidationError("a transaction checkpoint cannot carry within-transaction waypoint metadata")
    return {"kind": kind, "transaction_index": transaction_index, "waypoint": waypoint}


def _normalize_reachability(root: Path, raw: Any, *, artificial: bool) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("continuation reachability must be an object")
    paths = _objects(raw.get("writer_paths", []), "reachability.writer_paths", required=artificial)
    normalized = []
    for path in paths:
        kind = str(path.get("kind") or "").strip()
        status = str(path.get("status") or "").strip()
        if kind not in WRITER_KINDS or status not in WRITER_STATES:
            raise ValidationError(f"invalid reachability writer path kind/status: {kind}/{status}")
        refs = normalize_evidence_refs(
            root,
            path.get("evidence_refs", []),
            required=status in {"observed", "possible", "contradicted"},
        )
        probe = str(path.get("next_probe") or "").strip()
        if status == "unknown" and not probe:
            raise ValidationError("an unknown reachability writer path requires a bounded next_probe")
        non_privileged = path.get("non_privileged") is True
        normalized.append(
            {
                "kind": kind,
                "status": status,
                "actor": _text(path.get("actor"), "writer_path.actor"),
                "target": _text(path.get("target"), "writer_path.target"),
                "direction": _text(path.get("direction"), "writer_path.direction"),
                "non_privileged": non_privileged,
                "next_probe": probe,
                "evidence_refs": refs,
            }
        )
    plausible = not artificial or any(
        item["status"] in {"observed", "possible"}
        and item["non_privileged"]
        and item["evidence_refs"]
        for item in normalized
    )
    return {
        "artificial": artificial,
        "predicate": _text(raw.get("predicate"), "reachability.predicate"),
        "writer_paths": normalized,
        "plausible": plausible,
        "policy": "bounded reachability research requires an evidence-backed non-privileged writer in the needed direction; only execution establishes reachability",
    }


def create_continuation_contract(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "executable_continuity"):
        raise ValidationError("executable continuity is disabled by runtime feature policy")
    if not isinstance(payload, dict):
        raise ValidationError("continuation payload must be an object")
    parent_run = validate_id(_text(payload.get("parent_run"), "parent_run"), "RUN")
    _run_record(root, parent_run)
    closure_mode = str(payload.get("closure_mode") or "").strip()
    topology = str(payload.get("execution_topology") or "").strip()
    if closure_mode not in CLOSURE_MODES:
        raise ValidationError(f"unsupported continuation closure mode: {closure_mode}")
    if topology not in EXECUTION_TOPOLOGIES:
        raise ValidationError(f"unsupported continuation topology: {topology}")
    actors = _normalize_actors(payload.get("actors"))
    transactions = _normalize_transactions(payload.get("transactions"), {item["id"] for item in actors})
    checkpoint = _normalize_checkpoint(root, payload.get("checkpoint"), parent_run)
    if checkpoint["transaction_index"] >= len(transactions):
        raise ValidationError("continuation checkpoint references an unknown transaction")
    if topology == "nested-atomic" and checkpoint["kind"] != "transaction-waypoint":
        raise ValidationError("nested-atomic continuation requires a within-transaction waypoint")
    if topology == "temporal" and not any(item["boundary"] in {"time", "block"} for item in transactions):
        raise ValidationError("temporal continuation requires an explicit time or block boundary")
    if topology == "multi-actor" and len({item["actor"] for item in transactions}) < 2:
        raise ValidationError("multi-actor continuation requires at least two transaction actors")
    assertions = _normalize_assertions(root, payload.get("assertions"))
    assertion_ids = {item["id"] for item in assertions}
    preserve = payload.get("preserve_assertions")
    if not isinstance(preserve, list) or not preserve or any(str(item) not in assertion_ids for item in preserve):
        raise ValidationError("preserve_assertions must name one or more declared assertions")
    prerequisite = payload.get("selected_prerequisite")
    if not isinstance(prerequisite, dict):
        raise ValidationError("continuation selected_prerequisite must be an object")
    artificial = prerequisite.get("artificial") is True
    reachability = _normalize_reachability(root, payload.get("reachability"), artificial=artificial)
    if closure_mode == "reachability" and not artificial:
        raise ValidationError("reachability closure requires an explicitly artificial prerequisite")
    if closure_mode == "reachability" and not reachability["plausible"]:
        raise ValidationError("reachability closure lacks an evidence-backed non-privileged writer path")
    if closure_mode == "witness" and artificial:
        raise ValidationError("an artificial prerequisite must use reachability closure")
    continuation_id = allocate_id(root, "CONT")
    record = {
        "schema": schema_for(root),
        "kind": "continuation-contract",
        "id": continuation_id,
        "created_at": utc_now(),
        "lineage_id": _text(payload.get("lineage_id"), "lineage_id"),
        "parent_handoff": str(payload.get("parent_handoff") or "").strip() or None,
        "parent_run": parent_run,
        "closure_mode": closure_mode,
        "execution_topology": topology,
        "checkpoint": checkpoint,
        "actors": actors,
        "transactions": transactions,
        "assertions": assertions,
        "preserve_assertions": [str(item) for item in preserve],
        "selected_prerequisite": {
            "id": _text(prerequisite.get("id"), "selected_prerequisite.id"),
            "predicate": _text(prerequisite.get("predicate"), "selected_prerequisite.predicate"),
            "success_condition": _text(prerequisite.get("success_condition"), "selected_prerequisite.success_condition"),
            "artificial": artificial,
            "dependencies": [str(item).strip() for item in prerequisite.get("dependencies", []) if str(item).strip()],
        },
        "reachability": reachability,
        "status": "open",
        "attempts": [],
    }
    record["contract_sha256"] = digest_json({key: value for key, value in record.items() if key not in {"status", "attempts"}})
    write_json_atomic(root / "continuations" / f"{continuation_id}.json", record)
    event(root, "continuation.created", continuation_id=continuation_id, closure_mode=closure_mode, topology=topology)
    return record


def verify_continuation_contract(root: Path, continuation_id: str) -> dict[str, Any]:
    continuation_id = validate_id(continuation_id, "CONT")
    record = read_json(root / "continuations" / f"{continuation_id}.json")
    errors = []
    try:
        _run_record(root, str(record.get("parent_run")))
    except (IntegrityError, ValidationError, OSError, ValueError) as exc:
        errors.append(str(exc))
    for assertion in record.get("assertions", []):
        errors.extend(verify_evidence_refs(root, assertion.get("evidence_refs", [])))
    waypoint = (record.get("checkpoint") or {}).get("waypoint")
    if isinstance(waypoint, dict):
        errors.extend(verify_evidence_refs(root, waypoint.get("evidence_refs", [])))
    for writer in (record.get("reachability") or {}).get("writer_paths", []):
        errors.extend(verify_evidence_refs(root, writer.get("evidence_refs", [])))
    for attempt_id in record.get("attempts", []):
        attempt_path = root / "continuations" / f"{attempt_id}.json"
        if not attempt_path.is_file():
            errors.append(f"continuation attempt is missing: {attempt_id}")
            continue
        attempt = read_json(attempt_path)
        errors.extend(verify_evidence_refs(root, attempt.get("extension_evidence_refs", [])))
        for observation in attempt.get("assertions", []):
            errors.extend(verify_evidence_refs(root, observation.get("evidence_refs", [])))
    immutable = {key: value for key, value in record.items() if key not in {"status", "attempts", "contract_sha256"}}
    if digest_json(immutable) != record.get("contract_sha256"):
        errors.append("continuation immutable contract fields changed")
    return {"continuation_id": continuation_id, "valid": not errors, "errors": errors, "record": record}


def record_continuation_attempt(root: Path, continuation_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    checked = verify_continuation_contract(root, continuation_id)
    if not checked["valid"]:
        raise IntegrityError("continuation contract failed verification: " + "; ".join(checked["errors"]))
    record = checked["record"]
    replay_id = validate_id(_text(payload.get("replay_id"), "attempt.replay_id"), "REPLAY")
    replay = read_json(root / "replays" / f"{replay_id}.json")
    if replay.get("run_id") != record["parent_run"] or replay.get("passed") is not True:
        raise ValidationError("continuation attempt must replay the exact parent top-level run successfully")
    result = str(payload.get("result") or "").strip()
    if result not in ATTEMPT_RESULTS:
        raise ValidationError(f"invalid continuation attempt result: {result}")
    extension_run_id = payload.get("extension_run_id")
    extension_replay_id = payload.get("extension_replay_id")
    extension_refs = normalize_evidence_refs(root, payload.get("extension_evidence_refs", []), required=True)
    if result == "operational-failure":
        if extension_run_id is not None or extension_replay_id is not None:
            raise ValidationError("an operationally failed continuation cannot claim a completed extension replay")
    else:
        extension_run_id = validate_id(_text(extension_run_id, "attempt.extension_run_id"), "RUN")
        if extension_run_id == record["parent_run"]:
            raise ValidationError("continuation advancement requires a distinct extension run after parent replay")
        _run_record(root, extension_run_id)
        if not (root / "runs" / extension_run_id / "observation.json").is_file():
            raise ValidationError("continuation extension run must be semantically observed before advancement")
        extension_replay_id = validate_id(_text(extension_replay_id, "attempt.extension_replay_id"), "REPLAY")
        extension_replay = read_json(root / "replays" / f"{extension_replay_id}.json")
        if extension_replay.get("run_id") != extension_run_id or extension_replay.get("passed") is not True:
            raise ValidationError("continuation extension requires a passing replay of the distinct extension run")
        if not any(item.get("type") == "run-receipt" and item.get("run_id") == extension_run_id for item in extension_refs):
            raise ValidationError("continuation extension evidence lacks its run receipt")
        if not any(item.get("type") == "replay" and item.get("replay_id") == extension_replay_id for item in extension_refs):
            raise ValidationError("continuation extension evidence lacks its replay")
    observations = _objects(payload.get("assertions"), "attempt.assertions")
    by_id = {str(item.get("id")): item for item in observations}
    missing = [item for item in record["preserve_assertions"] if item not in by_id]
    failed = [item for item in record["preserve_assertions"] if by_id.get(item, {}).get("passed") is not True]
    if missing or failed:
        raise IntegrityError(f"continuation attempt did not preserve inherited assertions (missing={missing}, failed={failed})")
    normalized_observations = []
    for assertion_id, observation in by_id.items():
        if assertion_id not in {item["id"] for item in record["assertions"]}:
            raise ValidationError(f"continuation attempt references unknown assertion: {assertion_id}")
        normalized_observations.append(
            {
                "id": assertion_id,
                "passed": observation.get("passed") is True,
                "observed": _text(observation.get("observed"), "attempt.assertion.observed"),
                "evidence_refs": normalize_evidence_refs(root, observation.get("evidence_refs", []), required=True),
            }
        )
    attempt_id = allocate_id(root, "ATTEMPT")
    attempt = {
        "schema": schema_for(root),
        "kind": "continuation-attempt",
        "id": attempt_id,
        "created_at": utc_now(),
        "continuation_id": continuation_id,
        "parent_replay_id": replay_id,
        "extension_run_id": extension_run_id,
        "extension_replay_id": extension_replay_id,
        "extension_evidence_refs": extension_refs,
        "result": result,
        "assertions": sorted(normalized_observations, key=lambda item: item["id"]),
        "prerequisite_observation": _text(payload.get("prerequisite_observation"), "attempt.prerequisite_observation"),
        "next_action": _text(payload.get("next_action"), "attempt.next_action"),
        "operational_failure": result == "operational-failure",
    }
    write_json_atomic(root / "continuations" / f"{attempt_id}.json", attempt)
    record["attempts"].append(attempt_id)
    if result in {"resolved", "refuted"}:
        record["status"] = result
    elif result == "operational-failure":
        record["status"] = "open"
    else:
        record["status"] = result
    write_json_atomic(root / "continuations" / f"{continuation_id}.json", record)
    event(root, "continuation.attempted", continuation_id=continuation_id, attempt_id=attempt_id, result=result)
    return attempt
