from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence_bundles import verify_bundle
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now

REQUIRED_COSTS = {"wall_seconds", "cpu_core_seconds", "peak_memory_bytes", "llm_input_tokens", "llm_output_tokens", "rpc_requests", "evm_executions"}
OUTCOMES = {"validated-root-cause", "replayable-witness", "near-miss", "refuted", "false-positive", "timeout", "environment-failure"}


def record_trial(root: Path, *, incident: str, configuration: str, outcome: str, costs: dict[str, Any], evidence_id: str | None, notes: str) -> dict[str, Any]:
    require_v4_campaign(root)
    if set(costs) != REQUIRED_COSTS or any(not isinstance(value, (int, float)) or value < 0 for value in costs.values()):
        raise ValidationError(f"evaluation costs must contain non-negative {sorted(REQUIRED_COSTS)}")
    if outcome not in OUTCOMES:
        raise ValidationError("invalid evaluation outcome")
    if outcome in {"validated-root-cause", "replayable-witness"} and not evidence_id:
        raise ValidationError(f"evaluation outcome {outcome} requires linked evidence")
    if evidence_id:
        checked = verify_bundle(root, evidence_id)
        if not checked.get("valid"):
            raise ValidationError(f"evaluation evidence failed verification: {evidence_id}")
    trial_id = allocate_id(root, "TRIAL")
    record = {
        "schema": schema_for(root), "kind": "evaluation-trial", "id": trial_id, "created_at": utc_now(),
        "incident": incident, "configuration": configuration,
        "claimed_outcome": outcome, "verified_outcome": None,
        "costs": costs, "evidence_id": evidence_id,
        "adjudication_evidence_id": None, "notes": notes,
    }
    write_json_atomic(root / "orchestration" / f"{trial_id}.json", record)
    event(root, "evaluation.recorded", trial_id=trial_id, incident=incident, configuration=configuration, outcome=outcome)
    return record


def adjudicate_trial(root: Path, *, trial_id: str, outcome: str, evidence_id: str, notes: str) -> dict[str, Any]:
    require_v4_campaign(root)
    if outcome not in OUTCOMES:
        raise ValidationError("invalid verified evaluation outcome")
    path = root / "orchestration" / f"{trial_id}.json"
    if not path.is_file():
        raise ValidationError(f"unknown evaluation trial: {trial_id}")
    record = read_json(path)
    if record.get("verified_outcome") is not None:
        raise ValidationError(f"evaluation trial is already adjudicated: {trial_id}")
    checked = verify_bundle(root, evidence_id)
    if not checked.get("valid"):
        raise ValidationError(f"adjudication evidence failed verification: {evidence_id}")
    record["verified_outcome"] = outcome
    record["adjudication_evidence_id"] = evidence_id
    record["adjudication_notes"] = notes
    write_json_atomic(path, record)
    event(root, "evaluation.adjudicated", trial_id=trial_id, outcome=outcome, evidence_id=evidence_id)
    return record


def evaluation_summary(root: Path) -> dict[str, Any]:
    require_v4_campaign(root)
    trials = [read_json(path) for path in sorted((root / "orchestration").glob("TRIAL-*.json"))]
    configurations: dict[str, dict[str, Any]] = {}
    for trial in trials:
        item = configurations.setdefault(trial["configuration"], {"trials": 0, "validated_root_causes": 0, "replayable_witnesses": 0, "false_positives": 0, "costs": {key: 0 for key in REQUIRED_COSTS}})
        item["trials"] += 1
        verified = trial.get("verified_outcome")
        item["validated_root_causes"] += verified == "validated-root-cause"
        item["replayable_witnesses"] += verified in {"validated-root-cause", "replayable-witness"}
        item["false_positives"] += verified == "false-positive"
        for key, value in trial["costs"].items():
            item["costs"][key] += value
    return {"trials": len(trials), "configurations": configurations, "warning": "Compare configurations only under declared equal-cost budgets; coverage is diagnostic, not validated discovery."}
