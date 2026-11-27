from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .atomic import read_json, seal, verify_seal, write_json_atomic
from .errors import IntegrityError, ValidationError
from .hashing import is_relative_to, path_digest
from .process import execute
from .records import allocate_id, event, require_campaign, schema_for, utc_now
from .runs import resolve_anchor, verify_inputs


REPLAY_SOURCE_DIR = "source"
REPLAY_CAMPAIGN_DIR = "campaign"


def _git_head(path: Path) -> str | None:
    try:
        top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True, timeout=10)
        if Path(top.stdout.strip()).resolve() != path.resolve():
            return None
        result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True, check=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _safe_git_env(home: Path) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }


def _copy_ignore(current: str, names: list[str], source: Path) -> set[str]:
    denied = {".git", "node_modules"}
    if Path(current).resolve() == source.resolve():
        denied.update({"out", "cache", ".a1x"})
    return set(names) & denied


def _validate_symlinks(root: Path) -> None:
    for candidate in root.rglob("*"):
        if candidate.is_symlink() and not is_relative_to(candidate.resolve(), root):
            raise ValidationError(f"replay source contains an escaping symlink: {candidate}")


def prepare_replay(root: Path, *, run_id: str, destination: Path) -> dict[str, Any]:
    campaign = require_campaign(root)
    source = Path(campaign["source"]["path"])
    destination = destination.resolve()
    if destination.exists():
        raise ValidationError(f"replay destination must not already exist: {destination}")
    if is_relative_to(destination, root.resolve()) or is_relative_to(destination, source.resolve()):
        raise ValidationError("replay destination must be outside the campaign and source trees")
    destination.mkdir(parents=True)
    replay_source = destination / REPLAY_SOURCE_DIR
    replay_campaign = destination / REPLAY_CAMPAIGN_DIR
    run_dir = root / "runs" / run_id
    verify_seal(run_dir / "plan.json", run_dir / "plan.sha256")
    plan = read_json(run_dir / "plan.json")
    commit = plan.get("source_commit")
    if commit and _git_head(source) != commit:
        # V2 could record an enclosing repository's commit for a source
        # subdirectory. Such a subdirectory is not itself cloneable; preserve
        # its exact declared inputs through the filtered-copy replay path.
        commit = None
    method = "filtered-copy"
    if commit:
        git = shutil.which("git")
        if not git:
            raise ValidationError("git is required to prepare a replay at a pinned commit")
        env = _safe_git_env(root / "replays" / ".git-home")
        clone = subprocess.run(
            [git, "-c", "core.hooksPath=/dev/null", "clone", "--no-local", "--no-checkout", "--quiet", str(source), str(replay_source)],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        if clone.returncode != 0:
            raise ValidationError(f"failed to clone replay source: {clone.stderr.strip()[:500]}")
        checkout = subprocess.run(
            [git, "-C", str(replay_source), "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false", "checkout", "--detach", "--quiet", commit],
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        if checkout.returncode != 0:
            raise ValidationError(f"failed to check out replay commit: {checkout.stderr.strip()[:500]}")
        method = "sanitized-clone"
    else:
        shutil.copytree(source, replay_source, ignore=lambda current, names: _copy_ignore(current, names, source), symlinks=True)
    replay_campaign.mkdir(mode=0o700)
    _validate_symlinks(replay_source)
    injected = []
    materialized = []
    for item in plan.get("inputs", []):
        original = resolve_anchor(root, campaign, item["anchor"], item["path"])
        prepared = resolve_anchor(
            root,
            campaign,
            item["anchor"],
            item["path"],
            replay_source=replay_source,
            replay_campaign=replay_campaign,
        )
        if prepared.exists() and path_digest(prepared) == item["digest"]:
            materialized.append({"anchor": item["anchor"], "path": item["path"], "copied": False, "digest": item["digest"]})
            continue
        prepared.parent.mkdir(parents=True, exist_ok=True)
        if original.is_dir():
            shutil.copytree(
                original,
                prepared,
                dirs_exist_ok=True,
                ignore=lambda current, names: _copy_ignore(current, names, original),
                symlinks=True,
            )
        else:
            shutil.copy2(original, prepared, follow_symlinks=False)
        if path_digest(prepared) != item["digest"]:
            raise IntegrityError(f"failed to reproduce declared replay input: {item['anchor']}:{item['path']}")
        if item["anchor"] == "source":
            injected.append(item["path"])
        materialized.append({"anchor": item["anchor"], "path": item["path"], "copied": True, "digest": item["digest"]})
    cwd = resolve_anchor(
        root,
        campaign,
        plan["cwd"]["anchor"],
        plan["cwd"]["path"],
        replay_source=replay_source,
        replay_campaign=replay_campaign,
    )
    if not cwd.exists():
        cwd.mkdir(parents=True)
    if not cwd.is_dir():
        raise IntegrityError("replay working directory is not a directory")
    _validate_symlinks(replay_campaign)
    preparation_id = allocate_id(root, "PREP")
    record = {
        "schema": schema_for(root),
        "kind": "replay-preparation",
        "id": preparation_id,
        "created_at": utc_now(),
        "run_id": run_id,
        "destination": str(destination),
        "method": method,
        "source_commit": commit,
        "source_root": str(replay_source),
        "campaign_root": str(replay_campaign),
        "injected_declared_inputs": injected,
        "materialized_declared_inputs": materialized,
        "warning": "Injected inputs are exact hashed inputs, not proof that target code was unmodified.",
    }
    write_json_atomic(root / "replays" / "preparations" / f"{preparation_id}.json", record)
    event(root, "replay.prepared", preparation_id=preparation_id, run_id=run_id, method=method)
    return record


def verify_replay(root: Path, *, run_id: str, workspace: Path) -> dict[str, Any]:
    campaign = require_campaign(root)
    workspace = workspace.resolve()
    if not workspace.is_dir():
        raise ValidationError(f"replay workspace does not exist: {workspace}")
    run_dir = root / "runs" / run_id
    verify_seal(run_dir / "plan.json", run_dir / "plan.sha256")
    verify_seal(run_dir / "receipt.json", run_dir / "receipt.sha256")
    plan = read_json(run_dir / "plan.json")
    original = read_json(run_dir / "receipt.json")
    expected_commit = plan.get("source_commit")
    source = Path(campaign["source"]["path"])
    if expected_commit and _git_head(source) != expected_commit:
        expected_commit = None
    replay_source = workspace / REPLAY_SOURCE_DIR
    replay_campaign = workspace / REPLAY_CAMPAIGN_DIR
    if not replay_source.is_dir():
        raise IntegrityError(f"replay workspace is missing source root: {REPLAY_SOURCE_DIR}")
    actual_commit = _git_head(replay_source)
    if expected_commit and actual_commit != expected_commit:
        raise IntegrityError(f"replay source commit mismatch: expected {expected_commit}, got {actual_commit}")
    if not replay_campaign.is_dir():
        raise IntegrityError(f"replay workspace is missing reserved campaign input root: {REPLAY_CAMPAIGN_DIR}")
    _validate_symlinks(replay_source)
    _validate_symlinks(replay_campaign)
    checks = verify_inputs(root, plan, replay_source=replay_source, replay_campaign=replay_campaign)
    replay_id = allocate_id(root, "REPLAY")
    replay_dir = root / "replays" / replay_id
    replay_dir.mkdir()
    cwd = resolve_anchor(
        root,
        campaign,
        plan["cwd"]["anchor"],
        plan["cwd"]["path"],
        replay_source=replay_source,
        replay_campaign=replay_campaign,
    )
    result = execute(
        plan["argv_template"],
        cwd=cwd,
        artifact_dir=replay_dir,
        timeout_seconds=int(plan["timeout_seconds"]),
        max_output_bytes=int(plan["max_output_bytes"]),
        pass_env=plan.get("pass_env", []),
        inherit_env=plan.get("inherit_env", []),
    )
    regex_match: bool | None = None
    if plan.get("success_regex"):
        output = (replay_dir / "stdout.log").read_text(encoding="utf-8", errors="replace")
        regex_match = bool(re.search(plan["success_regex"], output, flags=re.MULTILINE))
    exit_matches = result.exit_code == original["process"]["exit_code"] and result.timed_out == original["process"]["timed_out"]
    passed = bool(exit_matches and result.exit_code == 0 and not result.timed_out and regex_match is not False)
    record = {
        "schema": schema_for(root),
        "kind": "replay-verification",
        "id": replay_id,
        "created_at": utc_now(),
        "run_id": run_id,
        "workspace": str(workspace),
        "replay_campaign_root": str(replay_campaign),
        "source_commit": actual_commit,
        "input_checks": checks,
        "process": result.to_dict(),
        "original_exit_code": original["process"]["exit_code"],
        "exit_matches": exit_matches,
        "success_regex_matched": regex_match,
        "passed": passed,
        "scope": "mechanical replay only; semantic property and actor-model review remain required",
    }
    write_json_atomic(replay_dir / "verification.json", record)
    seal(replay_dir / "verification.json", replay_dir / "verification.sha256")
    write_json_atomic(root / "replays" / f"{replay_id}.json", record)
    event(root, "replay.verified", replay_id=replay_id, run_id=run_id, passed=passed)
    return record
