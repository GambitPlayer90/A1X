from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


CATEGORIES = {"state-writer", "valuable-consumer", "callback", "actor-capability", "lifecycle", "numeric-boundary"}
STATUSES = {"represented", "missing", "unknown", "not-applicable"}
TASK_STATUSES = {"open", "executed", "refuted", "blocked"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"harness coverage {field} must be non-empty")
    return result


def create_harness_model(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "harness_expansion"):
        raise ValidationError("harness expansion is disabled by runtime feature policy")
    raw_items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list) or not raw_items or any(not isinstance(item, dict) for item in raw_items):
        raise ValidationError("harness model requires a non-empty items array")
    surface_id = payload.get("surface_id")
    if surface_id:
        surface_id = validate_id(str(surface_id), "SURFACE")
        if not (root / "surfaces" / f"{surface_id}.json").is_file():
            raise ValidationError(f"unknown fork surface: {surface_id}")
    items = []
    seen: set[str] = set()
    tasks = []
    for raw in raw_items:
        item_id = _text(raw.get("id"), "item.id")
        category = str(raw.get("category") or "")
        status = str(raw.get("status") or "")
        if item_id in seen or category not in CATEGORIES or status not in STATUSES:
            raise ValidationError(f"duplicate item or unsupported category/status: {item_id}/{category}/{status}")
        seen.add(item_id)
        handler = str(raw.get("handler") or "").strip() or None
        action = str(raw.get("action") or "").strip() or None
        next_probe = str(raw.get("next_probe") or "").strip() or None
        if status == "represented" and not (handler and action):
            raise ValidationError(f"represented harness item {item_id} requires a handler and action")
        if status in {"missing", "unknown"} and not next_probe:
            raise ValidationError(f"unresolved harness item {item_id} requires a bounded next_probe")
        refs = normalize_evidence_refs(root, raw.get("evidence_refs", []), required=status != "unknown")
        item = {
            "id": item_id,
            "category": category,
            "protocol_surface": _text(raw.get("protocol_surface"), "item.protocol_surface"),
            "security_relevance": _text(raw.get("security_relevance"), "item.security_relevance"),
            "status": status,
            "handler": handler,
            "action": action,
            "next_probe": next_probe,
            "evidence_refs": refs,
        }
        items.append(item)
        if status in {"missing", "unknown"}:
            tasks.append(item_id)
    missing_categories = CATEGORIES - {item["category"] for item in items}
    if missing_categories:
        raise ValidationError("harness model must explicitly cover every category, including unknown/not-applicable: " + ", ".join(sorted(missing_categories)))
    model_id = allocate_id(root, "HARNESS")
    record = {
        "schema": schema_for(root),
        "kind": "harness-surface-model",
        "id": model_id,
        "created_at": utc_now(),
        "name": _text(payload.get("name"), "name"),
        "surface_id": surface_id,
        "items": sorted(items, key=lambda item: (item["category"], item["id"])),
        "telemetry": [],
        "expansion_tasks": [],
        "completeness": "bounded to the declared protocol surface; unresolved discovery assumptions remain explicit",
    }
    write_json_atomic(root / "harnesses" / f"{model_id}.json", record)
    for item_id in tasks:
        create_expansion_task(
            root,
            harness_id=model_id,
            item_id=item_id,
            reason="protocol surface is not represented by an executable harness action",
            experiment=next(item["next_probe"] for item in items if item["id"] == item_id) or "resolve unknown",
            maximum_executions=256,
        )
    event(root, "harness.model-created", harness_id=model_id, items=len(items), unresolved=len(tasks))
    return read_json(root / "harnesses" / f"{model_id}.json")


def create_expansion_task(
    root: Path,
    *,
    harness_id: str,
    item_id: str,
    reason: str,
    experiment: str,
    maximum_executions: int,
) -> dict[str, Any]:
    harness_id = validate_id(harness_id, "HARNESS")
    if maximum_executions <= 0:
        raise ValidationError("harness expansion maximum_executions must be positive")
    path = root / "harnesses" / f"{harness_id}.json"
    harness = read_json(path)
    if item_id not in {item["id"] for item in harness.get("items", [])}:
        raise ValidationError(f"unknown harness surface item: {item_id}")
    for task_id in harness.get("expansion_tasks", []):
        existing = read_json(root / "harnesses" / f"{task_id}.json")
        if existing.get("item_id") == item_id and existing.get("status") == "open":
            return existing
    task_id = allocate_id(root, "HTASK")
    task = {
        "schema": schema_for(root),
        "kind": "harness-expansion-task",
        "id": task_id,
        "created_at": utc_now(),
        "harness_id": harness_id,
        "item_id": item_id,
        "reason": _text(reason, "task.reason"),
        "experiment": _text(experiment, "task.experiment"),
        "maximum_executions": maximum_executions,
        "status": "open",
        "run_id": None,
        "replay_id": None,
        "evidence_refs": [],
        "resolution": None,
    }
    write_json_atomic(root / "harnesses" / f"{task_id}.json", task)
    harness.setdefault("expansion_tasks", []).append(task_id)
    write_json_atomic(path, harness)
    event(root, "harness.expansion-created", harness_id=harness_id, task_id=task_id, item_id=item_id)
    return task


def record_harness_telemetry(
    root: Path,
    *,
    harness_id: str,
    run_id: str,
    replay_id: str,
    action_stats: list[dict[str, Any]],
    state_fingerprints: list[str],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    harness_id = validate_id(harness_id, "HARNESS")
    run_id = validate_id(run_id, "RUN")
    replay_id = validate_id(replay_id, "REPLAY")
    path = root / "harnesses" / f"{harness_id}.json"
    harness = read_json(path)
    replay = read_json(root / "replays" / f"{replay_id}.json")
    if replay.get("run_id") != run_id or replay.get("passed") is not True:
        raise ValidationError("harness telemetry requires a passing replay of the exact run")
    known = {item["id"] for item in harness["items"]}
    normalized = []
    for item in action_stats:
        if not isinstance(item, dict) or str(item.get("item_id")) not in known:
            raise ValidationError("harness telemetry references an unknown surface item")
        executions = item.get("executions")
        precondition_failures = item.get("precondition_failures")
        distinct_states = item.get("distinct_states")
        if any(not isinstance(value, int) or value < 0 for value in (executions, precondition_failures, distinct_states)):
            raise ValidationError("harness telemetry counters must be non-negative integers")
        if precondition_failures > executions:
            raise ValidationError("harness precondition failures exceed executions")
        normalized.append({"item_id": str(item["item_id"]), "executions": executions, "precondition_failures": precondition_failures, "distinct_states": distinct_states})
    refs = normalize_evidence_refs(root, evidence_refs, required=True)
    telemetry_id = allocate_id(root, "HTELEMETRY")
    record = {
        "schema": schema_for(root),
        "kind": "harness-telemetry",
        "id": telemetry_id,
        "created_at": utc_now(),
        "harness_id": harness_id,
        "run_id": run_id,
        "replay_id": replay_id,
        "action_stats": normalized,
        "state_fingerprints": sorted(set(str(item) for item in state_fingerprints if str(item).strip())),
        "evidence_refs": refs,
    }
    write_json_atomic(root / "harnesses" / f"{telemetry_id}.json", record)
    harness["telemetry"].append(telemetry_id)
    write_json_atomic(path, harness)
    for item in normalized:
        if item["executions"] > 0 and item["precondition_failures"] * 4 >= item["executions"] * 3:
            create_expansion_task(
                root,
                harness_id=harness_id,
                item_id=item["item_id"],
                reason="at least 75% of generated calls fail their preconditions",
                experiment="revise the generator toward a reachable prestate and replay the revised action",
                maximum_executions=max(32, item["executions"]),
            )
        elif item["executions"] >= 32 and item["distinct_states"] <= 1:
            create_expansion_task(
                root,
                harness_id=harness_id,
                item_id=item["item_id"],
                reason="repeated executions reach no additional state fingerprint",
                experiment="add a different preparation sequence and measure a new state fingerprint",
                maximum_executions=item["executions"],
            )
    event(root, "harness.telemetry-recorded", harness_id=harness_id, telemetry_id=telemetry_id)
    return record


def resolve_expansion_task(
    root: Path,
    *,
    task_id: str,
    status: str,
    resolution: str,
    run_id: str | None,
    replay_id: str | None,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    task_id = validate_id(task_id, "HTASK")
    if status not in TASK_STATUSES - {"open"}:
        raise ValidationError("harness expansion resolution must be executed, refuted, or blocked")
    path = root / "harnesses" / f"{task_id}.json"
    task = read_json(path)
    refs = normalize_evidence_refs(root, evidence_refs, required=True)
    if status in {"executed", "refuted"}:
        run_id = validate_id(str(run_id), "RUN")
        replay_id = validate_id(str(replay_id), "REPLAY")
        replay = read_json(root / "replays" / f"{replay_id}.json")
        if replay.get("run_id") != run_id or replay.get("passed") is not True:
            raise ValidationError("harness expansion requires a passing replay of the exact run")
        if not any(item.get("type") == "run-receipt" and item.get("run_id") == run_id for item in refs):
            raise ValidationError("harness expansion evidence lacks the execution run")
        if not any(item.get("type") == "replay" and item.get("replay_id") == replay_id for item in refs):
            raise ValidationError("harness expansion evidence lacks the clean replay")
    elif run_id or replay_id:
        raise ValidationError("blocked harness expansion cannot claim an execution/replay pair")
    task.update({"status": status, "resolution": _text(resolution, "task.resolution"), "run_id": run_id, "replay_id": replay_id, "evidence_refs": refs, "resolved_at": utc_now()})
    write_json_atomic(path, task)
    harness_path = root / "harnesses" / f"{task['harness_id']}.json"
    harness = read_json(harness_path)
    if status == "executed":
        for item in harness["items"]:
            if item["id"] == task["item_id"]:
                item["status"] = "represented"
                item["handler"] = item.get("handler") or "recorded expansion run"
                item["action"] = item.get("action") or task["experiment"]
                item["evidence_refs"] = refs
                item["next_probe"] = None
    write_json_atomic(harness_path, harness)
    event(root, "harness.expansion-resolved", task_id=task_id, status=status)
    return task


def verify_harness_model(root: Path, harness_id: str) -> dict[str, Any]:
    harness_id = validate_id(harness_id, "HARNESS")
    record = read_json(root / "harnesses" / f"{harness_id}.json")
    errors = []
    for item in record.get("items", []):
        errors.extend(verify_evidence_refs(root, item.get("evidence_refs", [])))
    for task_id in record.get("expansion_tasks", []):
        path = root / "harnesses" / f"{task_id}.json"
        if not path.is_file():
            errors.append(f"harness expansion task is missing: {task_id}")
            continue
        errors.extend(verify_evidence_refs(root, read_json(path).get("evidence_refs", [])))
    if set(CATEGORIES) - {item.get("category") for item in record.get("items", [])}:
        errors.append("harness model no longer covers every required category")
    return {"harness_id": harness_id, "valid": not errors, "errors": errors, "record": record}
