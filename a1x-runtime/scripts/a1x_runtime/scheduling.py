from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .features import enabled
from .records import event, require_v4_campaign, schema_for, utc_now


STATE_PATH = Path("orchestration/lineage-scheduling.json")


def _blank(root: Path) -> dict[str, Any]:
    return {
        "schema": schema_for(root),
        "kind": "lineage-scheduling-state",
        "updated_at": utc_now(),
        "last_generation": 0,
        "lineages": {},
    }


def scheduling_state(root: Path) -> dict[str, Any]:
    require_v4_campaign(root)
    path = root / STATE_PATH
    if not path.is_file():
        record = _blank(root)
        write_json_atomic(path, record)
        return record
    record = read_json(path)
    if record.get("kind") != "lineage-scheduling-state" or not isinstance(record.get("lineages"), dict):
        raise ValidationError("lineage scheduling state is malformed")
    return record


def _entry(state: dict[str, Any], lineage_id: str, generation: int) -> dict[str, Any]:
    lineages = state["lineages"]
    if lineage_id not in lineages:
        lineages[lineage_id] = {
            "first_seen_generation": generation,
            "last_seen_generation": generation,
            "last_selected_generation": None,
            "last_research_attempt_generation": None,
            "last_progress_generation": None,
            "waiting_generations": 0,
            "research_attempts": 0,
            "operational_failures": 0,
            "consecutive_no_gain_attempts": 0,
            "witness_advances": 0,
            "information_advances": 0,
        }
    entry = lineages[lineage_id]
    entry["last_seen_generation"] = max(int(entry.get("last_seen_generation", generation)), generation)
    return entry


def select_fair_lineages(
    root: Path,
    *,
    candidates: list[dict[str, Any]],
    slots: int,
    generation: int,
) -> list[str]:
    """Choose closure lineages by opportunity first and fitness second.

    Each candidate contains a lineage_id and a JSON-compatible priority list.
    A lineage that has never received a research attempt outranks one that has;
    otherwise waiting age prevents a permanently dominant high-fitness lead
    from starving another eligible lead.
    """
    if slots < 0 or generation <= 0:
        raise ValidationError("scheduling slots must be non-negative and generation positive")
    if any(not str(item.get("lineage_id", "")).strip() for item in candidates):
        raise ValidationError("every scheduling candidate requires a lineage_id")
    if not enabled(root, "attempt_aware_scheduling"):
        ranked = sorted(candidates, key=lambda item: tuple(item.get("priority", [])), reverse=True)
        return [str(item["lineage_id"]) for item in ranked[:slots]]

    state = scheduling_state(root)
    candidate_ids = {str(item["lineage_id"]) for item in candidates}
    for lineage_id in candidate_ids:
        _entry(state, lineage_id, generation)
    for lineage_id, entry in state["lineages"].items():
        if lineage_id in candidate_ids and entry.get("last_selected_generation") != generation:
            entry["waiting_generations"] = int(entry.get("waiting_generations", 0)) + 1

    def rank(item: dict[str, Any]) -> tuple[Any, ...]:
        lineage_id = str(item["lineage_id"])
        entry = state["lineages"][lineage_id]
        never_attempted = int(entry.get("research_attempts", 0) == 0)
        waiting = int(entry.get("waiting_generations", 0))
        recent_progress = int(entry.get("last_progress_generation") is not None)
        return never_attempted, waiting, recent_progress, tuple(item.get("priority", [])), lineage_id

    selected = [str(item["lineage_id"]) for item in sorted(candidates, key=rank, reverse=True)[:slots]]
    for lineage_id in selected:
        entry = state["lineages"][lineage_id]
        entry["last_selected_generation"] = generation
        entry["waiting_generations"] = 0
    state["last_generation"] = max(int(state.get("last_generation", 0)), generation)
    state["updated_at"] = utc_now()
    write_json_atomic(root / STATE_PATH, state)
    event(root, "scheduling.lineages-selected", generation=generation, selected=selected, eligible=sorted(candidate_ids))
    return selected


def record_lineage_attempts(
    root: Path,
    *,
    generation: int,
    outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Record attributable outcomes without treating tool failure as stagnation."""
    if generation <= 0 or any(not isinstance(item, dict) for item in outcomes):
        raise ValidationError("lineage attempt outcomes are invalid")
    state = scheduling_state(root)
    for outcome in outcomes:
        lineage_id = str(outcome.get("lineage_id") or "").strip()
        if not lineage_id:
            raise ValidationError("lineage attempt outcome requires lineage_id")
        entry = _entry(state, lineage_id, generation)
        if outcome.get("operational_failure") is True:
            entry["operational_failures"] = int(entry.get("operational_failures", 0)) + 1
            continue
        entry["research_attempts"] = int(entry.get("research_attempts", 0)) + 1
        entry["last_research_attempt_generation"] = generation
        witness = outcome.get("witness_progress") is True
        information = outcome.get("information_progress") is True
        semantic = outcome.get("semantic_progress") is True
        if witness:
            entry["witness_advances"] = int(entry.get("witness_advances", 0)) + 1
        if information:
            entry["information_advances"] = int(entry.get("information_advances", 0)) + 1
        if witness or information or semantic:
            entry["last_progress_generation"] = generation
            entry["consecutive_no_gain_attempts"] = 0
        else:
            entry["consecutive_no_gain_attempts"] = int(entry.get("consecutive_no_gain_attempts", 0)) + 1
    state["last_generation"] = max(int(state.get("last_generation", 0)), generation)
    state["updated_at"] = utc_now()
    write_json_atomic(root / STATE_PATH, state)
    event(root, "scheduling.attempts-recorded", generation=generation, outcomes=len(outcomes))
    return state


def resource_snapshot(root: Path) -> dict[str, Any]:
    """Aggregate observed compute and preserve unavailable dimensions as unknown."""
    require_v4_campaign(root)
    run_processes = []
    for path in sorted((root / "runs").glob("RUN-*/receipt.json")):
        process = read_json(path).get("process")
        if isinstance(process, dict):
            run_processes.append(process)
    lane_processes = []
    for path in sorted((root / "scale").glob("ROUND-*/lanes/LANE-*/lane-receipt.json")):
        process = read_json(path).get("process")
        if isinstance(process, dict):
            lane_processes.append(process)
    rpc_requests = 0
    for path in sorted((root / "forks").glob("FORK-*/rpc-accounting.json")):
        value = read_json(path)
        rpc_requests += int(value.get("total", 0))
    all_processes = [*run_processes, *lane_processes]
    snapshot = {
        "schema": schema_for(root),
        "kind": "research-resource-snapshot",
        "created_at": utc_now(),
        "observed": {
            "wall_process_seconds": sum(int(item.get("duration_ms", 0)) for item in all_processes) / 1000,
            "processes": len(all_processes),
            "target_runs": len(run_processes),
            "model_lanes": len(lane_processes),
            "process_output_bytes": sum(int(item.get("stdout_bytes", 0)) + int(item.get("stderr_bytes", 0)) for item in all_processes),
            "rpc_requests": rpc_requests,
            "solver_jobs": len(list((root / "solver-jobs").glob("SOLVER-*.json"))),
            "trace_analyses": len(list((root / "trace-facts").glob("TRACE-*.json"))),
        },
        "unknown": [
            "llm_input_tokens when the Codex CLI receipt does not expose usage",
            "llm_output_tokens when the Codex CLI receipt does not expose usage",
            "peak memory for child processes without platform accounting",
            "EVM executions not emitted by the selected backend",
        ],
    }
    write_json_atomic(root / "orchestration" / "resource-snapshot.json", snapshot)
    return snapshot
