from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic import (
    _write_json_atomic_raw,
    append_jsonl,
    canonical_bytes,
    digest_json,
    exclusive_lock,
    read_json,
    write_json_atomic,
)
from .errors import IntegrityError, ValidationError

LEGACY_RUNTIME_SCHEMA = "a1x.runtime/v1"
RUNTIME_SCHEMA = "a1x.runtime/v2"
SUPPORTED_RUNTIME_SCHEMAS = {LEGACY_RUNTIME_SCHEMA, RUNTIME_SCHEMA}
ID_RE = re.compile(r"^[A-Z]+-[0-9]{4,}$")
MATERIALIZATION_VERSION = 1
_NON_MATERIALIZED_JSON = {"event-state.json"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def require_campaign(root: Path) -> dict[str, Any]:
    root = root.resolve()
    campaign = read_json(root / "campaign.json")
    if campaign.get("schema") not in SUPPORTED_RUNTIME_SCHEMAS or campaign.get("kind") != "campaign":
        raise ValidationError(f"not a supported A1X campaign: {root}")
    if campaign.get("schema") == RUNTIME_SCHEMA and (root / "event-state.json").is_file():
        recover_event_state(root)
        campaign = read_json(root / "campaign.json")
    return campaign


def schema_for(root: Path) -> str:
    """Return the campaign record schema without silently migrating it."""
    return str(require_campaign(root)["schema"])


def require_v4_campaign(root: Path) -> dict[str, Any]:
    campaign = require_campaign(root)
    if campaign.get("schema") != RUNTIME_SCHEMA:
        raise ValidationError("this command requires A1X v4; run `a1x campaign migrate --root ...` explicitly")
    return campaign


def _sha256_file(path: Path) -> str | None:
    if not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def initialize_event_chain(root: Path) -> dict[str, Any]:
    """Anchor legacy JSONL history and initialize the v4 hash chain."""
    state_path = root / "event-state.json"
    with exclusive_lock(root):
        if state_path.exists():
            return read_json(state_path)
        legacy_anchor = _sha256_file(root / "events.jsonl")
        state = {
            "schema": RUNTIME_SCHEMA,
            "kind": "event-chain-state",
            "sequence": 0,
            "head_sha256": legacy_anchor,
            "legacy_log_sha256": legacy_anchor,
            "materialization_version": 0,
            "initialized_at": utc_now(),
        }
        _write_json_atomic_raw(state_path, state)
        return state


def _campaign_root_for(path: Path) -> Path | None:
    candidate = path.resolve()
    for parent in (candidate.parent, *candidate.parents):
        if (parent / "campaign.json").is_file():
            return parent
    return None


def _materialization_target(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise IntegrityError(f"event materialization escapes campaign root: {relative}") from exc
    if path.name in _NON_MATERIALIZED_JSON or path == root / "events.jsonl":
        raise IntegrityError(f"event materialization targets runtime journal state: {relative}")
    return path


def _authoritative_json_path(root: Path, path: Path) -> bool:
    relative = path.resolve().relative_to(root.resolve())
    parts = relative.parts
    if not parts or path.name in _NON_MATERIALIZED_JSON:
        return False
    if relative.as_posix() in {"campaign.json", "counters.json"}:
        return True
    if parts[:3] == ("evidence", "objects", "sha256"):
        return False
    if any(part in {".codex-home", "workspace", "target", ".a1x-quarantine", "cache"} for part in parts):
        return False
    # Fork/prestate child-process configuration and high-frequency RPC
    # accounting are reproducible operational telemetry, not campaign state.
    if parts[0] in {"forks", "prestate"} and len(parts) > 2:
        return False
    return parts[0] in {
        "obligations", "hypotheses", "runs", "forks", "candidates", "replays",
        "reviews", "scale", "frontier", "impact", "orchestration", "evidence",
        "recon", "capabilities", "operations", "prestate", "rsa", "migrations",
        "evaluation", "continuations", "trace-facts", "surfaces", "compositions",
        "actors", "oracles", "harnesses", "solver-jobs",
    }


def _append_event_locked(root: Path, state: dict[str, Any], kind: str, data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    sequence = int(state.get("sequence", 0)) + 1
    campaign = read_json(root / "campaign.json")
    body = {
        "schema": RUNTIME_SCHEMA,
        "kind": "campaign-event",
        "id": f"EVT-{sequence:08d}",
        "sequence": sequence,
        "epoch": int(campaign.get("epoch", 1)),
        "at": utc_now(),
        "event": kind,
        "previous_sha256": state.get("head_sha256"),
        **data,
    }
    event_hash = hashlib.sha256(canonical_bytes(body)).hexdigest()
    record = {**body, "event_sha256": event_hash}
    append_jsonl(root / "events.jsonl", record)
    updated = dict(state)
    updated.update({"sequence": sequence, "head_sha256": event_hash, "updated_at": record["at"]})
    return record, updated


def _baseline_materializations(root: Path) -> list[dict[str, Any]]:
    materializations: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.json")):
        relative_path = path.relative_to(root)
        if not _authoritative_json_path(root, path):
            continue
        try:
            value = read_json(path)
        except IntegrityError:
            continue
        materializations.append({
            "path": relative_path.as_posix(),
            "mode": path.stat().st_mode & 0o777,
            "record_sha256": digest_json(value),
            "value": value,
        })
    return materializations


def _ensure_materialization_baseline_locked(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    if int(state.get("materialization_version", 0)) >= MATERIALIZATION_VERSION:
        return state
    materializations = _baseline_materializations(root)
    _, updated = _append_event_locked(
        root,
        state,
        "state.baseline",
        {"materialization_version": MATERIALIZATION_VERSION, "materializations": materializations},
    )
    updated["materialization_version"] = MATERIALIZATION_VERSION
    _write_json_atomic_raw(root / "event-state.json", updated)
    return updated


def _apply_materializations(root: Path, event_record: dict[str, Any]) -> None:
    values = event_record.get("materializations")
    if values is None and event_record.get("materialization") is not None:
        values = [event_record["materialization"]]
    if values is None:
        return
    if not isinstance(values, list):
        raise IntegrityError(f"invalid materialization payload in {event_record.get('id')}")
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise IntegrityError(f"invalid materialization entry in {event_record.get('id')}")
        value = item.get("value")
        if digest_json(value) != item.get("record_sha256"):
            raise IntegrityError(f"materialization digest mismatch in {event_record.get('id')}")
        mode = int(item.get("mode", 0o600))
        if mode < 0 or mode > 0o777:
            raise IntegrityError(f"invalid materialization mode in {event_record.get('id')}")
        _write_json_atomic_raw(_materialization_target(root, item["path"]), value, mode=mode)


def _pending_events_locked(root: Path, state: dict[str, Any]) -> list[dict[str, Any]]:
    pending: list[dict[str, Any]] = []
    expected_sequence = int(state.get("sequence", 0)) + 1
    previous = state.get("head_sha256")
    path = root / "events.jsonl"
    if not path.is_file():
        return pending
    # Normal operation has no recovery work.  Check the durable tail in O(1)
    # event reads before falling back to a full integrity walk.
    with path.open("rb") as tail_handle:
        tail_handle.seek(0, 2)
        position = tail_handle.tell()
        buffer = b""
        while position > 0:
            size = min(65536, position)
            position -= size
            tail_handle.seek(position)
            buffer = tail_handle.read(size) + buffer
            lines = buffer.rstrip(b"\n").splitlines()
            if len(lines) > 1 or position == 0:
                try:
                    tail = json.loads(lines[-1]) if lines else None
                except json.JSONDecodeError:
                    tail = None
                if (
                    isinstance(tail, dict)
                    and tail.get("schema") == RUNTIME_SCHEMA
                    and int(tail.get("sequence", -1)) == int(state.get("sequence", 0))
                    and tail.get("event_sha256") == state.get("head_sha256")
                ):
                    return pending
                break
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise IntegrityError(f"event log line {line_number} is incomplete or invalid: {exc}") from exc
            if item.get("schema") != RUNTIME_SCHEMA or item.get("kind") != "campaign-event":
                continue
            sequence = int(item.get("sequence", -1))
            if sequence < expected_sequence:
                continue
            if sequence != expected_sequence:
                raise IntegrityError(f"event recovery encountered sequence gap before {item.get('id')}")
            body = dict(item)
            claimed = body.pop("event_sha256", None)
            actual = hashlib.sha256(canonical_bytes(body)).hexdigest()
            if item.get("previous_sha256") != previous or claimed != actual:
                raise IntegrityError(f"event recovery integrity failure at {item.get('id')}")
            pending.append(item)
            expected_sequence += 1
            previous = claimed
    return pending


def recover_event_state(root: Path) -> dict[str, Any]:
    """Finish journaled materializations whose process stopped before commit.

    The event is appended and fsynced first.  Materialized JSON views follow,
    then the event-state head advances.  A stale head therefore identifies the
    exact events that must be replayed after interruption.
    """
    root = root.resolve()
    with exclusive_lock(root):
        state = read_json(root / "event-state.json")
        pending = _pending_events_locked(root, state)
        for item in pending:
            _apply_materializations(root, item)
            state.update({
                "sequence": int(item["sequence"]),
                "head_sha256": item["event_sha256"],
                "updated_at": utc_now(),
            })
        if pending:
            _write_json_atomic_raw(root / "event-state.json", state)
        state = _ensure_materialization_baseline_locked(root, state)
        return {"recovered_events": len(pending), "sequence": int(state.get("sequence", 0)), "head_sha256": state.get("head_sha256")}


def materialize_json_if_campaign(path: Path, value: Any, *, mode: int = 0o600) -> bool:
    """Journal an authoritative v4 JSON view before materializing it."""
    root = _campaign_root_for(path)
    if root is None or path.name in _NON_MATERIALIZED_JSON:
        return False
    try:
        campaign = read_json(root / "campaign.json")
    except IntegrityError:
        return False
    if campaign.get("schema") != RUNTIME_SCHEMA:
        return False
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    if relative == "event-state.json" or not _authoritative_json_path(root, path):
        return False
    with exclusive_lock(root):
        if not (root / "event-state.json").is_file():
            initialize_event_chain(root)
        state = read_json(root / "event-state.json")
        for item in _pending_events_locked(root, state):
            _apply_materializations(root, item)
            state.update({"sequence": int(item["sequence"]), "head_sha256": item["event_sha256"], "updated_at": utc_now()})
        state = _ensure_materialization_baseline_locked(root, state)
        materialization = {
            "path": relative,
            "mode": mode,
            "record_sha256": digest_json(value),
            "value": value,
        }
        _, updated = _append_event_locked(root, state, "state.materialized", {"materialization": materialization})
        _write_json_atomic_raw(path, value, mode=mode)
        _write_json_atomic_raw(root / "event-state.json", updated)
    return True


def event(root: Path, kind: str, **data: Any) -> dict[str, Any]:
    """Append a legacy event or a sequence-numbered, hash-linked v4 event."""
    campaign = require_campaign(root)
    if campaign.get("schema") == LEGACY_RUNTIME_SCHEMA:
        record = {"at": utc_now(), "event": kind, **data}
        with exclusive_lock(root):
            append_jsonl(root / "events.jsonl", record)
        return record

    state_path = root / "event-state.json"
    if not state_path.exists():
        initialize_event_chain(root)
    with exclusive_lock(root):
        state = read_json(state_path)
        pending = _pending_events_locked(root, state)
        for item in pending:
            _apply_materializations(root, item)
            state.update({"sequence": int(item["sequence"]), "head_sha256": item["event_sha256"], "updated_at": utc_now()})
        state = _ensure_materialization_baseline_locked(root, state)
        record, state = _append_event_locked(root, state, kind, data)
        _write_json_atomic_raw(state_path, state)
    return record


def verify_event_chain(root: Path) -> dict[str, Any]:
    require_campaign(root)
    state = read_json(root / "event-state.json")
    previous = state.get("legacy_log_sha256")
    count = 0
    errors: list[str] = []
    materialized: dict[str, dict[str, Any]] = {}
    path = root / "events.jsonl"
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                try:
                    item = json.loads(line)
                except json.JSONDecodeError as exc:
                    errors.append(f"line {line_number}: invalid JSON: {exc}")
                    continue
                if item.get("schema") != RUNTIME_SCHEMA or item.get("kind") != "campaign-event":
                    continue
                count += 1
                claimed = item.get("event_sha256")
                body = dict(item)
                body.pop("event_sha256", None)
                actual = hashlib.sha256(canonical_bytes(body)).hexdigest()
                if int(item.get("sequence", -1)) != count:
                    errors.append(f"line {line_number}: non-contiguous v4 sequence")
                if item.get("previous_sha256") != previous:
                    errors.append(f"line {line_number}: previous hash mismatch")
                if claimed != actual:
                    errors.append(f"line {line_number}: event hash mismatch")
                values = item.get("materializations")
                if values is None and item.get("materialization") is not None:
                    values = [item["materialization"]]
                if values is not None:
                    if not isinstance(values, list):
                        errors.append(f"line {line_number}: invalid materializations")
                    else:
                        for materialization in values:
                            if not isinstance(materialization, dict) or not isinstance(materialization.get("path"), str):
                                errors.append(f"line {line_number}: invalid materialization entry")
                                continue
                            if digest_json(materialization.get("value")) != materialization.get("record_sha256"):
                                errors.append(f"line {line_number}: materialization digest mismatch")
                                continue
                            materialized[materialization["path"]] = materialization
                previous = claimed
    if count != int(state.get("sequence", -1)):
        errors.append("event-state sequence does not match the log")
    if previous != state.get("head_sha256"):
        errors.append("event-state head does not match the log")
    for relative, materialization in materialized.items():
        try:
            target = _materialization_target(root, relative)
            if not target.is_file():
                errors.append(f"materialized view missing: {relative}")
            elif digest_json(read_json(target)) != materialization.get("record_sha256"):
                errors.append(f"materialized view differs from authoritative event: {relative}")
        except (IntegrityError, OSError, ValueError) as exc:
            errors.append(f"invalid materialized view {relative}: {exc}")
    return {"valid": not errors, "events": count, "head_sha256": previous, "errors": errors}


def allocate_id(root: Path, prefix: str) -> str:
    with exclusive_lock(root):
        path = root / "counters.json"
        counters = read_json(path) if path.exists() else {}
        number = int(counters.get(prefix, 0)) + 1
        counters[prefix] = number
        write_json_atomic(path, counters)
    return f"{prefix}-{number:04d}"


def validate_id(value: str, prefix: str | None = None) -> str:
    if not ID_RE.fullmatch(value):
        raise ValidationError(f"invalid record id: {value}")
    if prefix and not value.startswith(prefix + "-"):
        raise ValidationError(f"expected {prefix} id, got {value}")
    return value


def record_path(root: Path, category: str, record_id: str) -> Path:
    validate_id(record_id)
    return root / category / f"{record_id}.json"


def update_research_counter(root: Path, key: str, delta: int = 1) -> None:
    with exclusive_lock(root):
        campaign_path = root / "campaign.json"
        campaign = read_json(campaign_path)
        counters = campaign.setdefault("research_counters", {})
        counters[key] = int(counters.get(key, 0)) + delta
        campaign["updated_at"] = utc_now()
        write_json_atomic(campaign_path, campaign)
