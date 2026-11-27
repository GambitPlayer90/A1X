from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


ACTOR_ROLES = {"attacker", "victim", "keeper", "liquidator", "solver", "governance", "protocol", "other"}
STEP_BOUNDARIES = {"transaction", "callback", "time", "block", "epoch", "keeper-action"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"actor program {field} must be non-empty")
    return result


def create_actor_program(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "actor_programs"):
        raise ValidationError("actor programs are disabled by runtime feature policy")
    actors_raw = payload.get("actors") if isinstance(payload, dict) else None
    steps_raw = payload.get("steps") if isinstance(payload, dict) else None
    if not isinstance(actors_raw, list) or not actors_raw or any(not isinstance(item, dict) for item in actors_raw):
        raise ValidationError("actor program requires a non-empty actors array")
    actors = []
    actor_ids: set[str] = set()
    for raw in actors_raw:
        actor_id = _text(raw.get("id"), "actor.id")
        role = str(raw.get("role") or "")
        if actor_id in actor_ids or role not in ACTOR_ROLES:
            raise ValidationError(f"duplicate actor or unsupported role: {actor_id}/{role}")
        actor_ids.add(actor_id)
        capabilities = [str(item).strip() for item in raw.get("capabilities", []) if str(item).strip()]
        if not capabilities:
            raise ValidationError(f"actor {actor_id} requires explicit capabilities")
        actors.append(
            {
                "id": actor_id,
                "role": role,
                "address": str(raw.get("address") or "").strip() or None,
                "capabilities": capabilities,
                "honest_policy": str(raw.get("honest_policy") or "").strip() or None,
                "authority_basis": _text(raw.get("authority_basis"), "actor.authority_basis"),
            }
        )
    if not isinstance(steps_raw, list) or not steps_raw or any(not isinstance(item, dict) for item in steps_raw):
        raise ValidationError("actor program requires a non-empty steps array")
    steps = []
    for index, raw in enumerate(steps_raw):
        if raw.get("index") != index:
            raise ValidationError("actor program step indices must be contiguous and zero-based")
        actor = _text(raw.get("actor"), "step.actor")
        boundary = str(raw.get("boundary") or "")
        if actor not in actor_ids or boundary not in STEP_BOUNDARIES:
            raise ValidationError(f"actor program step {index} has unknown actor or boundary")
        steps.append(
            {
                "index": index,
                "actor": actor,
                "boundary": boundary,
                "action": _text(raw.get("action"), "step.action"),
                "target": _text(raw.get("target"), "step.target"),
                "preconditions": [str(item).strip() for item in raw.get("preconditions", []) if str(item).strip()],
                "expected_effects": [str(item).strip() for item in raw.get("expected_effects", []) if str(item).strip()],
            }
        )
    ordering = payload.get("ordering_assumptions")
    if not isinstance(ordering, list):
        raise ValidationError("actor program ordering_assumptions must be an array")
    ordering = [str(item).strip() for item in ordering if str(item).strip()]
    if any(item["boundary"] in {"time", "block", "epoch", "keeper-action"} for item in steps) and not ordering:
        raise ValidationError("temporal or externally ordered actor programs require explicit ordering assumptions")
    if len({item["actor"] for item in steps}) > 1 and len({item["role"] for item in actors}) < 2:
        raise ValidationError("multi-actor execution must distinguish actor roles")
    program_id = allocate_id(root, "ACTORS")
    record = {
        "schema": schema_for(root),
        "kind": "actor-program",
        "id": program_id,
        "created_at": utc_now(),
        "name": _text(payload.get("name"), "name"),
        "actors": actors,
        "steps": steps,
        "ordering_assumptions": ordering,
        "mempool_model": str(payload.get("mempool_model") or "none").strip(),
        "status": "planned",
        "execution_id": None,
    }
    write_json_atomic(root / "actors" / f"{program_id}.json", record)
    event(root, "actors.program-created", actor_program_id=program_id, actors=len(actors), steps=len(steps))
    return record


def record_actor_execution(
    root: Path,
    *,
    actor_program_id: str,
    run_id: str,
    replay_id: str,
    observed_steps: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    actor_program_id = validate_id(actor_program_id, "ACTORS")
    run_id = validate_id(run_id, "RUN")
    replay_id = validate_id(replay_id, "REPLAY")
    program_path = root / "actors" / f"{actor_program_id}.json"
    program = read_json(program_path)
    replay = read_json(root / "replays" / f"{replay_id}.json")
    if replay.get("run_id") != run_id or replay.get("passed") is not True:
        raise ValidationError("actor execution requires a passing replay of the exact run")
    if not isinstance(observed_steps, list) or len(observed_steps) != len(program["steps"]):
        raise ValidationError("actor execution must account for every planned step")
    normalized_steps = []
    for planned, observed in zip(program["steps"], observed_steps):
        if not isinstance(observed, dict) or observed.get("index") != planned["index"]:
            raise ValidationError("actor execution step order differs from the program")
        normalized_steps.append(
            {
                "index": planned["index"],
                "executed": observed.get("executed") is True,
                "observation": _text(observed.get("observation"), "execution.step.observation"),
            }
        )
    if any(not item["executed"] for item in normalized_steps):
        raise ValidationError("actor execution cannot complete while a planned step is unexecuted")
    refs = normalize_evidence_refs(root, evidence_refs, required=True)
    required_refs = {
        (item.get("type"), item.get("run_id"), item.get("replay_id"))
        for item in refs
    }
    if ("run-receipt", run_id, None) not in required_refs or ("replay", run_id, replay_id) not in required_refs:
        raise ValidationError("actor execution evidence requires its run receipt and replay")
    execution_id = allocate_id(root, "AEXEC")
    record = {
        "schema": schema_for(root),
        "kind": "actor-program-execution",
        "id": execution_id,
        "created_at": utc_now(),
        "actor_program_id": actor_program_id,
        "run_id": run_id,
        "replay_id": replay_id,
        "observed_steps": normalized_steps,
        "evidence_refs": refs,
        "status": "executed",
    }
    write_json_atomic(root / "actors" / f"{execution_id}.json", record)
    program["status"] = "executed"
    program["execution_id"] = execution_id
    write_json_atomic(program_path, program)
    event(root, "actors.program-executed", actor_program_id=actor_program_id, execution_id=execution_id)
    return record


def verify_actor_execution(root: Path, execution_id: str) -> dict[str, Any]:
    execution_id = validate_id(execution_id, "AEXEC")
    record = read_json(root / "actors" / f"{execution_id}.json")
    errors = verify_evidence_refs(root, record.get("evidence_refs", []))
    if not (root / "actors" / f"{record.get('actor_program_id')}.json").is_file():
        errors.append("actor program definition is missing")
    return {"execution_id": execution_id, "valid": not errors, "errors": errors, "record": record}
