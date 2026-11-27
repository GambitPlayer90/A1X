from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evaluation import REQUIRED_COSTS
from .features import PROFILES
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


FROZEN_V43_COMMIT = "2b27e884a4a64c32b6c817f49d030d15011203bb"
REQUIRED_CONFIGURATIONS = {"v4.3.0-frozen", "v4.4.0-integrity", "v4.4.0-full"}


def _budget(value: Any) -> dict[str, int | float]:
    if not isinstance(value, dict) or set(value) != REQUIRED_COSTS:
        raise ValidationError(f"benchmark budget must contain exactly {sorted(REQUIRED_COSTS)}")
    if any(not isinstance(item, (int, float)) or item <= 0 for item in value.values()):
        raise ValidationError("benchmark resource limits must be positive numbers")
    return {key: value[key] for key in sorted(value)}


def create_benchmark_suite(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not isinstance(payload, dict):
        raise ValidationError("benchmark suite payload must be an object")
    incidents = payload.get("incidents")
    if not isinstance(incidents, list) or not incidents or any(not str(item).strip() for item in incidents):
        raise ValidationError("benchmark suite requires one or more named incidents")
    holds = payload.get("controlled_variables")
    if not isinstance(holds, dict):
        raise ValidationError("benchmark suite controlled_variables must be an object")
    required_holds = {"model", "target_information", "tools", "chain_block", "attacker_model"}
    if required_holds - set(holds) or any(not str(holds[key]).strip() for key in required_holds):
        raise ValidationError("benchmark suite must hold model, target_information, tools, chain_block, and attacker_model explicit")
    budget = _budget(payload.get("resource_budget"))
    configurations = [
        {
            "name": "v4.3.0-frozen",
            "source_commit": FROZEN_V43_COMMIT,
            "features": dict(PROFILES["v4.3.0-frozen"]),
            "classification": "frozen baseline",
        },
        {
            "name": "v4.4.0-integrity",
            "source_commit": str(payload.get("v4_commit") or "working-tree"),
            "features": dict(PROFILES["v4.4.0-integrity"]),
            "classification": "correctness and continuity fixes",
        },
        {
            "name": "v4.4.0-full",
            "source_commit": str(payload.get("v4_commit") or "working-tree"),
            "features": dict(PROFILES["v4.4.0-full"]),
            "classification": "complete policy",
        },
    ]
    suite_id = allocate_id(root, "BENCH")
    record = {
        "schema": schema_for(root),
        "kind": "equal-budget-benchmark-suite",
        "id": suite_id,
        "created_at": utc_now(),
        "name": str(payload.get("name") or "").strip(),
        "incidents": sorted(set(str(item).strip() for item in incidents)),
        "controlled_variables": {key: str(value) for key, value in sorted(holds.items())},
        "resource_budget": budget,
        "configurations": configurations,
        "trial_ids": [],
        "held_out_required": payload.get("held_out_required") is not False,
        "policy": "configuration changes are isolated by feature profile; claims compare independently adjudicated outcomes under the same declared envelope",
    }
    if not record["name"]:
        raise ValidationError("benchmark suite name must be non-empty")
    write_json_atomic(root / "orchestration" / f"{suite_id}.json", record)
    event(root, "benchmark.suite-created", benchmark_id=suite_id, incidents=len(record["incidents"]))
    return record


def attach_benchmark_trial(root: Path, *, benchmark_id: str, trial_id: str) -> dict[str, Any]:
    benchmark_id = validate_id(benchmark_id, "BENCH")
    trial_id = validate_id(trial_id, "TRIAL")
    path = root / "orchestration" / f"{benchmark_id}.json"
    suite = read_json(path)
    trial = read_json(root / "orchestration" / f"{trial_id}.json")
    if trial.get("incident") not in suite["incidents"]:
        raise ValidationError("evaluation trial incident is outside the benchmark suite")
    if trial.get("configuration") not in REQUIRED_CONFIGURATIONS:
        raise ValidationError("evaluation trial configuration is outside the benchmark suite")
    for key, value in trial.get("costs", {}).items():
        if value > suite["resource_budget"][key]:
            raise ValidationError(f"evaluation trial exceeded the equal-budget envelope for {key}")
    if trial_id not in suite["trial_ids"]:
        suite["trial_ids"].append(trial_id)
        write_json_atomic(path, suite)
    event(root, "benchmark.trial-attached", benchmark_id=benchmark_id, trial_id=trial_id)
    return suite


def compare_benchmark(root: Path, benchmark_id: str) -> dict[str, Any]:
    benchmark_id = validate_id(benchmark_id, "BENCH")
    suite = read_json(root / "orchestration" / f"{benchmark_id}.json")
    matrix: dict[str, dict[str, dict[str, Any]]] = {incident: {} for incident in suite["incidents"]}
    errors = []
    for trial_id in suite.get("trial_ids", []):
        trial = read_json(root / "orchestration" / f"{trial_id}.json")
        incident = str(trial.get("incident"))
        configuration = str(trial.get("configuration"))
        if configuration in matrix.get(incident, {}):
            errors.append(f"duplicate trial for {incident}/{configuration}")
        matrix.setdefault(incident, {})[configuration] = trial
        if trial.get("verified_outcome") is None:
            errors.append(f"trial is not independently adjudicated: {trial_id}")
    for incident in suite["incidents"]:
        missing = REQUIRED_CONFIGURATIONS - set(matrix[incident])
        if missing:
            errors.append(f"incident {incident} lacks configurations: {sorted(missing)}")
    metrics: dict[str, dict[str, Any]] = {}
    for configuration in sorted(REQUIRED_CONFIGURATIONS):
        trials = [matrix[incident][configuration] for incident in suite["incidents"] if configuration in matrix[incident]]
        metrics[configuration] = {
            "trials": len(trials),
            "validated_root_causes": sum(item.get("verified_outcome") == "validated-root-cause" for item in trials),
            "replayable_witnesses": sum(item.get("verified_outcome") in {"validated-root-cause", "replayable-witness"} for item in trials),
            "near_misses": sum(item.get("verified_outcome") == "near-miss" for item in trials),
            "false_positives": sum(item.get("verified_outcome") == "false-positive" for item in trials),
            "consumed": {key: sum(item["costs"][key] for item in trials) for key in sorted(REQUIRED_COSTS)},
        }
    result = {
        "schema": schema_for(root),
        "kind": "equal-budget-benchmark-comparison",
        "benchmark_id": benchmark_id,
        "created_at": utc_now(),
        "valid": not errors,
        "errors": errors,
        "resource_budget_per_trial": suite["resource_budget"],
        "metrics": metrics,
        "warning": "a benchmark measures the supplied incidents and adjudicator; it is not a proof of general vulnerability-discovery performance",
    }
    write_json_atomic(root / "orchestration" / f"{benchmark_id}-comparison.json", result)
    event(root, "benchmark.compared", benchmark_id=benchmark_id, valid=result["valid"])
    return result
