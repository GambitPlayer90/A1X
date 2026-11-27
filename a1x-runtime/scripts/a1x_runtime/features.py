from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .records import event, require_v4_campaign, schema_for, utc_now


FEATURES = (
    "executable_continuity",
    "reachability_closure",
    "trace_facts",
    "fork_surface_graph",
    "prerequisite_graph",
    "three_mode_rsa",
    "actor_programs",
    "solver_adapters",
    "harness_expansion",
    "semantic_progress",
    "attempt_aware_scheduling",
    "automatic_frontier_sweep",
)


def default_feature_record() -> dict[str, Any]:
    return {
        "schema": "a1x.runtime/v2",
        "kind": "runtime-feature-flags",
        "runtime_version": "4.4.0",
        "updated_at": utc_now(),
        "features": {name: True for name in FEATURES},
        "policy": "flags isolate regressions and ablations; the v4.4 release enables every completed subsystem",
    }


def feature_record(root: Path) -> dict[str, Any]:
    require_v4_campaign(root)
    path = root / "orchestration" / "features.json"
    if not path.is_file():
        record = default_feature_record()
        record["schema"] = schema_for(root)
        write_json_atomic(path, record)
        return record
    record = read_json(path)
    values = record.get("features")
    if not isinstance(values, dict) or set(values) != set(FEATURES):
        raise ValidationError("runtime feature record does not contain the complete v4.4 feature set")
    if any(not isinstance(value, bool) for value in values.values()):
        raise ValidationError("runtime feature values must be boolean")
    return record


def set_feature(root: Path, *, name: str, enabled: bool) -> dict[str, Any]:
    if name not in FEATURES:
        raise ValidationError(f"unknown runtime feature: {name}")
    record = feature_record(root)
    record["features"][name] = enabled
    record["updated_at"] = utc_now()
    write_json_atomic(root / "orchestration" / "features.json", record)
    event(root, "runtime.feature-changed", feature=name, enabled=enabled)
    return record


def enabled(root: Path, name: str) -> bool:
    if name not in FEATURES:
        raise ValidationError(f"unknown runtime feature: {name}")
    return bool(feature_record(root)["features"][name])
