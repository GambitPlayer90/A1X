from __future__ import annotations

import os
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .atomic import digest_json, exclusive_lock, read_json, write_json_atomic
from .errors import ValidationError
from .hashing import path_digest
from .records import (
    LEGACY_RUNTIME_SCHEMA,
    RUNTIME_SCHEMA,
    allocate_id,
    event,
    initialize_event_chain,
    require_campaign,
    schema_for,
    update_research_counter,
    utc_now,
)
from .sandbox import bubblewrap_preflight


COUNTERS = {
    "hypotheses_investigated": 0,
    "candidate_executions": 0,
    "compilation_harness_repairs": 0,
    "fuzzer_campaigns": 0,
    "solver_campaigns": 0,
    "validated_root_causes": 0,
}

CAMPAIGN_DIRECTORIES = (
    "obligations",
    "hypotheses",
    "runs",
    "forks",
    "candidates",
    "replays",
    "reviews",
    "scale",
    "frontier",
    "impact",
    "orchestration",
    "evidence",
    "recon",
    "capabilities",
    "operations",
    "prestate",
    "rsa",
    "migrations",
    "continuations",
    "trace-facts",
    "surfaces",
    "compositions",
    "actors",
    "oracles",
    "harnesses",
    "solver-jobs",
)


def _git_value(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def git_identity(source: Path) -> dict[str, Any]:
    top_level = _git_value(source, "rev-parse", "--show-toplevel")
    if not top_level or Path(top_level).resolve() != source.resolve():
        return {
            "is_git": False,
            "commit": None,
            "dirty": None,
            "remote": None,
            "enclosing_git_root": top_level,
            "reason": "source is not the root of a standalone Git worktree" if top_level else "no Git worktree",
        }
    commit = _git_value(source, "rev-parse", "HEAD")
    if not commit:
        return {"is_git": False, "commit": None, "dirty": None, "remote": None, "enclosing_git_root": None, "reason": "no commit"}
    dirty = bool(_git_value(source, "status", "--porcelain", "--untracked-files=no"))
    remote = _git_value(source, "remote", "get-url", "origin")
    return {"is_git": True, "commit": commit, "dirty": dirty, "remote": remote, "enclosing_git_root": top_level, "reason": None}


def init_campaign(
    root: Path,
    *,
    label: str,
    source: Path,
    target: str,
    chain_id: int | None,
    block_number: int | None,
    rpc_env: str | None,
    authorization: str,
    budgets: dict[str, int],
) -> dict[str, Any]:
    root = root.resolve()
    source = source.resolve()
    if not label.strip() or not target.strip() or not authorization.strip():
        raise ValidationError("campaign label, target, and authorization must be non-empty")
    if chain_id is not None and chain_id <= 0:
        raise ValidationError("chain id must be positive")
    if block_number is not None and block_number < 0:
        raise ValidationError("block number cannot be negative")
    invalid_budgets = {key: value for key, value in budgets.items() if not isinstance(value, int) or value <= 0}
    if invalid_budgets:
        raise ValidationError(f"campaign budgets must be positive integers: {invalid_budgets}")
    if root.exists() and any(root.iterdir()):
        raise ValidationError(f"campaign directory is not empty: {root}")
    if not source.is_dir():
        raise ValidationError(f"source directory does not exist: {source}")
    if rpc_env and (not rpc_env.isidentifier() or rpc_env.upper() != rpc_env):
        raise ValidationError("RPC environment variable must be an uppercase identifier")
    root.mkdir(parents=True, exist_ok=True)
    for category in CAMPAIGN_DIRECTORIES:
        (root / category).mkdir()
    (root / "evidence" / "objects" / "sha256").mkdir(parents=True)
    (root / "evidence" / "bundles").mkdir()
    now = utc_now()
    identity = git_identity(source)
    campaign = {
        "schema": RUNTIME_SCHEMA,
        "kind": "campaign",
        "runtime_version": "4.4.0",
        "epoch": 1,
        "label": label,
        "target": target,
        "authorization": authorization,
        "created_at": now,
        "updated_at": now,
        "source": {
            "path": str(source),
            "git": identity,
            "initial_digest": path_digest(source),
        },
        "chain": {
            "chain_id": chain_id,
            "block_number": block_number,
            "rpc_env": rpc_env,
        },
        "budgets": budgets,
        "research_counters": dict(COUNTERS),
    }
    write_json_atomic(root / "campaign.json", campaign)
    write_json_atomic(root / "counters.json", {})
    from .features import default_feature_record

    write_json_atomic(root / "orchestration" / "features.json", default_feature_record())
    event(root, "campaign.initialized", label=label, source=str(source))
    return campaign


def show_campaign(root: Path) -> dict[str, Any]:
    campaign = require_campaign(root)
    counts: dict[str, int] = {}
    for category in CAMPAIGN_DIRECTORIES:
        identifiers: set[str] = set()
        if (root / category).exists():
            identifiers.update(path.stem for path in (root / category).glob("*.json"))
            identifiers.update(path.name for path in (root / category).glob("*-*") if path.is_dir())
        counts[category] = len(identifiers)
    return {"campaign": campaign, "artifact_counts": counts}


def migrate_campaign(root: Path) -> dict[str, Any]:
    """Explicitly migrate v3 metadata while preserving legacy records and log bytes."""
    campaign = require_campaign(root)
    if campaign["schema"] == RUNTIME_SCHEMA:
        if campaign.get("runtime_version") == "4.4.0":
            return {"migrated": False, "reason": "already-current", "campaign": campaign}
        migration_id = allocate_id(root, "MIGRATION")
        now = utc_now()
        before_hash = digest_json(campaign)
        with exclusive_lock(root):
            current = read_json(root / "campaign.json")
            for category in CAMPAIGN_DIRECTORIES:
                (root / category).mkdir(parents=True, exist_ok=True)
            from .features import default_feature_record

            features = root / "orchestration" / "features.json"
            if not features.exists():
                write_json_atomic(features, default_feature_record())
            current.update({"runtime_version": "4.4.0", "updated_at": now})
            write_json_atomic(root / "campaign.json", current)
            migration = {
                "schema": RUNTIME_SCHEMA,
                "kind": "campaign-migration",
                "id": migration_id,
                "created_at": now,
                "from_schema": RUNTIME_SCHEMA,
                "to_schema": RUNTIME_SCHEMA,
                "from_runtime_version": campaign.get("runtime_version"),
                "to_runtime_version": "4.4.0",
                "source_campaign_sha256": before_hash,
                "policy": "existing records remain byte-for-byte unchanged; v4.4 records are additive",
            }
            write_json_atomic(root / "migrations" / f"{migration_id}.json", migration)
        event(root, "campaign.upgraded", migration_id=migration_id, from_runtime_version=campaign.get("runtime_version"))
        return {"migrated": True, "migration": migration, "campaign": require_campaign(root)}
    if campaign["schema"] != LEGACY_RUNTIME_SCHEMA:
        raise ValidationError(f"unsupported source schema: {campaign['schema']}")

    initialize_event_chain(root)
    migration_id = allocate_id(root, "MIGRATION")
    before_hash = digest_json(campaign)
    now = utc_now()
    with exclusive_lock(root):
        current = read_json(root / "campaign.json")
        if current.get("schema") != LEGACY_RUNTIME_SCHEMA:
            raise ValidationError("campaign changed while migration was being prepared")
        for category in CAMPAIGN_DIRECTORIES:
            (root / category).mkdir(parents=True, exist_ok=True)
        (root / "evidence" / "objects" / "sha256").mkdir(parents=True, exist_ok=True)
        (root / "evidence" / "bundles").mkdir(parents=True, exist_ok=True)
        current.update({"schema": RUNTIME_SCHEMA, "runtime_version": "4.4.0", "epoch": 1, "updated_at": now})
        write_json_atomic(root / "campaign.json", current)
        migration = {
            "schema": RUNTIME_SCHEMA,
            "kind": "campaign-migration",
            "id": migration_id,
            "created_at": now,
            "from_schema": LEGACY_RUNTIME_SCHEMA,
            "to_schema": RUNTIME_SCHEMA,
            "source_campaign_sha256": before_hash,
            "legacy_event_log_sha256": read_json(root / "event-state.json").get("legacy_log_sha256"),
            "policy": "legacy records remain byte-for-byte unchanged",
        }
        write_json_atomic(root / "migrations" / f"{migration_id}.json", migration)
        from .features import default_feature_record

        write_json_atomic(root / "orchestration" / "features.json", default_feature_record())
    event(root, "campaign.migrated", migration_id=migration_id, from_schema=LEGACY_RUNTIME_SCHEMA)
    return {"migrated": True, "migration": migration, "campaign": require_campaign(root)}


def add_obligation(root: Path, *, title: str, statement: str, boundary: str, units: str, oracle: str) -> dict[str, Any]:
    require_campaign(root)
    if any(not value.strip() for value in (title, statement, boundary, units, oracle)):
        raise ValidationError("obligation fields must be non-empty")
    record_id = allocate_id(root, "OBL")
    record = {
        "schema": schema_for(root),
        "kind": "obligation",
        "id": record_id,
        "created_at": utc_now(),
        "title": title,
        "statement": statement,
        "boundary": boundary,
        "units": units,
        "security_oracle": oracle,
        "status": "open",
    }
    write_json_atomic(root / "obligations" / f"{record_id}.json", record)
    event(root, "obligation.created", obligation_id=record_id)
    return record


def add_hypothesis(
    root: Path,
    *,
    obligation_id: str,
    mechanism: str,
    sequence: str,
    support_prediction: str,
    refute_prediction: str,
    next_action: str,
) -> dict[str, Any]:
    require_campaign(root)
    if any(not value.strip() for value in (mechanism, sequence, support_prediction, refute_prediction, next_action)):
        raise ValidationError("hypothesis fields must be non-empty")
    obligation = root / "obligations" / f"{obligation_id}.json"
    if not obligation.exists():
        raise ValidationError(f"unknown obligation: {obligation_id}")
    record_id = allocate_id(root, "HYP")
    record = {
        "schema": schema_for(root),
        "kind": "hypothesis",
        "id": record_id,
        "created_at": utc_now(),
        "updated_at": utc_now(),
        "obligation_id": obligation_id,
        "mechanism": mechanism,
        "sequence": sequence,
        "support_prediction": support_prediction,
        "refute_prediction": refute_prediction,
        "next_action": next_action,
        "status": "open",
        "runs": [],
    }
    write_json_atomic(root / "hypotheses" / f"{record_id}.json", record)
    update_research_counter(root, "hypotheses_investigated")
    event(root, "hypothesis.created", hypothesis_id=record_id, obligation_id=obligation_id)
    return record


def doctor() -> dict[str, Any]:
    tools = ["python3", "git", "forge", "cast", "anvil", "echidna", "medusa", "codex", "halmos", "slither", "wake", "aderyn", "ityfuzz", "bwrap"]
    version_args = {
        "python3": ["--version"],
        "git": ["--version"],
        "forge": ["--version"],
        "cast": ["--version"],
        "anvil": ["--version"],
        "echidna": ["--version"],
        "medusa": ["--version"],
        "codex": ["--version"],
        "halmos": ["--version"],
        "slither": ["--version"],
        "wake": ["--version"],
        "aderyn": ["--version"],
        "ityfuzz": ["--version"],
        "bwrap": ["--version"],
    }
    def inspect_tool(tool: str) -> tuple[str, dict[str, Any]]:
        executable = shutil.which(tool)
        item: dict[str, Any] = {"available": bool(executable), "path": executable, "version": None}
        if executable:
            try:
                result = subprocess.run(
                    [executable, *version_args[tool]], capture_output=True, text=True, timeout=5, env={"PATH": os.environ.get("PATH", "")}
                )
                output = (result.stdout or result.stderr).strip().splitlines()
                item["version"] = output[0][:500] if output else None
                item["version_exit_code"] = result.returncode
            except (OSError, subprocess.SubprocessError) as exc:
                item["version_error"] = type(exc).__name__
        return tool, item

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="a1x-doctor") as pool:
        found = dict(pool.map(inspect_tool, tools))
    # GHC-based Echidna can lose a version probe race when several analyzers
    # initialize together. Retry it alone before capability gating.
    if found["echidna"].get("available") and not found["echidna"].get("version"):
        executable = found["echidna"]["path"]
        try:
            result = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=10, env={"PATH": os.environ.get("PATH", "")})
            output = (result.stdout or result.stderr).strip().splitlines()
            if output:
                found["echidna"].update({"version": output[0][:500], "version_exit_code": result.returncode})
                found["echidna"].pop("version_error", None)
        except (OSError, subprocess.SubprocessError):
            pass
    core = ["python3", "git", "forge", "cast", "anvil", "codex"]
    sandbox_preflight = bubblewrap_preflight(refresh=True)
    if "bwrap" in found:
        found["bwrap"]["sandbox_preflight"] = sandbox_preflight
    echidna_version = found["echidna"].get("version") or ""
    version_match = re.search(r"\b(\d+)\.(\d+)(?:\.(\d+))?", echidna_version)
    echidna_tuple = tuple(int(item or 0) for item in version_match.groups()) if version_match else (0, 0, 0)
    core_ready = all(found[name]["available"] for name in core)
    capabilities = {
        "foundry_replay": all(found[name]["available"] for name in ("forge", "cast", "anvil")),
        "wake_semantic_fuzz": found["wake"]["available"],
        "echidna_fuzz": found["echidna"]["available"],
        "echidna_live_campaign": found["echidna"]["available"] and echidna_tuple >= (2, 4, 0),
        "medusa_fuzz": found["medusa"]["available"],
        "ityfuzz_deployed_state": found["ityfuzz"]["available"],
        "symbolic": found["halmos"]["available"],
        "static_analysis": found["wake"]["available"] or found["slither"]["available"],
        "isolated_lanes": sandbox_preflight["usable"],
    }
    return {
        "runtime_version": "4.4.0",
        "platform": os.uname().sysname,
        "tools": found,
        "core_ready": core_ready,
        "required_ready": core_ready,
        "capabilities": capabilities,
        "codex_lane_sandbox_ready": sandbox_preflight["usable"],
        "notes": [
            "Only the Foundry/Codex core gates general readiness; specialist backends are capability-gated.",
            "Echidna live campaign control requires version 2.4 or newer.",
            "No environment-variable values were read or emitted by doctor.",
            "A false codex_lane_sandbox_ready value blocks real population lanes as an explicit environment limitation.",
        ],
    }


def save_doctor(root: Path) -> dict[str, Any]:
    require_campaign(root)
    result = doctor()
    result["captured_at"] = utc_now()
    write_json_atomic(root / "doctor.json", result)
    event(root, "doctor.captured", required_ready=result["required_ready"])
    return result
