from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from .atomic import _write_json_atomic_raw, digest_json, exclusive_lock, read_json, write_text_atomic
from .errors import IntegrityError, ValidationError
from .records import require_campaign, utc_now


LEDGER_SCHEMA = "a1x.ledger/v1"
KINDS = {"SCOPE", "OBL", "INV", "EXP", "FACT", "TASK", "SYN"}
PREFIXES = {kind: kind for kind in KINDS}
STATUSES = {
    "open", "active", "blocked", "closed", "validated", "refuted",
    "out-of-scope", "not-applicable",
}
PRIORITIES = {"low", "medium", "high", "critical"}
INVESTIGATION_STAGES = {"lead", "hypothesis", "candidate", "validated", "refuted", "closed"}


def _paths(root: Path) -> tuple[Path, Path, Path]:
    directory = root / "v5"
    return directory / "ledger.json", directory / "ledger.tsv", directory / "brief.md"


def _text(value: Any, field: str, *, required: bool = True) -> str:
    result = str(value or "").strip()
    if required and not result:
        raise ValidationError(f"ledger {field} must be non-empty")
    return result


def _record_sort_key(record: dict[str, Any]) -> tuple[str, int]:
    identifier = str(record["id"])
    prefix, _, number = identifier.partition("-")
    return prefix, int(number or 0)


def _public_state(state: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in state.items() if key != "ledger_sha256"}


def _state_digest(state: dict[str, Any]) -> str:
    return digest_json(_public_state(state))


def _validate_ref_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(f"ledger {field} must be an array")
    result = []
    for item in value:
        text = _text(item, field)
        if text not in result:
            result.append(text)
    return result


def validate_ledger(state: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("schema") != LEDGER_SCHEMA:
        raise ValidationError("unsupported or malformed A1X ledger")
    if not isinstance(state.get("revision"), int) or state["revision"] < 0:
        raise ValidationError("ledger revision must be a non-negative integer")
    records = state.get("records")
    next_ids = state.get("next_ids")
    legacy_map = state.get("legacy_map")
    if not isinstance(records, dict) or not isinstance(next_ids, dict) or not isinstance(legacy_map, dict):
        raise ValidationError("ledger records and next_ids must be objects")
    if set(next_ids) != KINDS or any(not isinstance(value, int) or value < 1 for value in next_ids.values()):
        raise ValidationError("ledger next_ids is incomplete or invalid")
    seen_sources: set[str] = set()
    for identifier, record in records.items():
        if not isinstance(record, dict) or record.get("id") != identifier:
            raise ValidationError(f"ledger record key/id mismatch: {identifier}")
        kind = str(record.get("kind", ""))
        if kind not in KINDS or not identifier.startswith(PREFIXES[kind] + "-"):
            raise ValidationError(f"ledger record has invalid kind/id: {identifier}/{kind}")
        if record.get("status") not in STATUSES or record.get("priority") not in PRIORITIES:
            raise ValidationError(f"ledger record has invalid status/priority: {identifier}")
        if not isinstance(record.get("revision"), int) or record["revision"] < 1:
            raise ValidationError(f"ledger record revision is invalid: {identifier}")
        _text(record.get("title"), f"{identifier}.title")
        _text(record.get("statement"), f"{identifier}.statement")
        parents = _validate_ref_list(record.get("parents"), f"{identifier}.parents")
        scope = _validate_ref_list(record.get("scope"), f"{identifier}.scope")
        _validate_ref_list(record.get("evidence"), f"{identifier}.evidence")
        _validate_ref_list(record.get("artifacts"), f"{identifier}.artifacts")
        if identifier in parents:
            raise ValidationError(f"ledger record cannot parent itself: {identifier}")
        for parent in parents:
            if parent not in records:
                raise ValidationError(f"ledger record {identifier} has unknown parent {parent}")
        for scope_id in scope:
            if scope_id not in records or records[scope_id].get("kind") != "SCOPE":
                raise ValidationError(f"ledger record {identifier} has invalid scope reference {scope_id}")
        data = record.get("data", {})
        if not isinstance(data, dict) or not isinstance(record.get("transitions", []), list):
            raise ValidationError(f"ledger record {identifier} data/transitions are malformed")
        if "cost" in data and (not isinstance(data["cost"], str) or data["cost"] not in {"low", "medium", "high"}):
            raise ValidationError(f"ledger record {identifier} has invalid data.cost")
        if kind == "SCOPE" and "impacts" in data:
            impacts = data["impacts"]
            if not isinstance(impacts, list) or any(not isinstance(item, str) or not item.strip() for item in impacts):
                raise ValidationError(f"scope {identifier} data.impacts must be an array of exact non-empty impact strings")
            if len({item.strip() for item in impacts}) != len(impacts):
                raise ValidationError(f"scope {identifier} data.impacts must not contain duplicates")
        if "runtime_refs" in data:
            _validate_ref_list(data["runtime_refs"], f"{identifier}.data.runtime_refs")
        if kind == "INV" and record.get("stage") not in INVESTIGATION_STAGES:
            raise ValidationError(f"investigation {identifier} has invalid stage")
        if kind == "TASK":
            if not _text(data.get("question"), f"{identifier}.data.question", required=False):
                raise ValidationError(f"task {identifier} requires one bounded decision question")
        if kind == "SYN":
            if not _text(data.get("revised_attempt"), f"{identifier}.data.revised_attempt", required=False):
                raise ValidationError(f"synthesis {identifier} requires a revised testable attempt")
            if not _text(data.get("next_discriminator"), f"{identifier}.data.next_discriminator", required=False):
                raise ValidationError(f"synthesis {identifier} requires a next discriminator")
        source = record.get("legacy_source")
        if source:
            source = str(source)
            if source in seen_sources:
                raise ValidationError(f"duplicate legacy source in ledger: {source}")
            seen_sources.add(source)
    for source, identifier in legacy_map.items():
        if not str(source).strip() or identifier not in records:
            raise ValidationError(f"ledger legacy map has invalid entry: {source!r} -> {identifier!r}")
    for kind in KINDS:
        allocated = [int(identifier.rsplit("-", 1)[1]) for identifier in records if identifier.startswith(PREFIXES[kind] + "-")]
        if allocated and next_ids[kind] <= max(allocated):
            raise ValidationError(f"ledger next_ids would reuse an existing {kind} identifier")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(identifier: str) -> None:
        if identifier in visiting:
            raise ValidationError(f"ledger parent cycle includes {identifier}")
        if identifier in visited:
            return
        visiting.add(identifier)
        for parent in records[identifier].get("parents", []):
            visit(parent)
        visiting.remove(identifier)
        visited.add(identifier)

    for identifier in records:
        visit(identifier)
    recorded_digest = state.get("ledger_sha256")
    if recorded_digest is not None and recorded_digest != _state_digest(state):
        raise IntegrityError("ledger digest mismatch")
    return state


def _render_tsv(state: dict[str, Any]) -> str:
    output = io.StringIO(newline="")
    output.write(f"# ledger_sha256\t{state['ledger_sha256']}\n")
    writer = csv.writer(output, delimiter="\t", lineterminator="\n")
    writer.writerow(["id", "kind", "status", "stage", "priority", "title", "parents", "scope", "next_action", "updated_at"])
    for record in sorted(state["records"].values(), key=_record_sort_key):
        writer.writerow([
            record["id"], record["kind"], record["status"], record.get("stage", ""),
            record["priority"], record["title"], ",".join(record["parents"]),
            ",".join(record["scope"]), record.get("next_action", ""), record["updated_at"],
        ])
    return output.getvalue()


def _render_brief(state: dict[str, Any]) -> str:
    records = sorted(state["records"].values(), key=_record_sort_key)
    active = [item for item in records if item["status"] in {"open", "active", "blocked"}]
    lines = [
        "# A1X hunt brief",
        "",
        f"Ledger revision: {state['revision']}",
        f"Ledger SHA-256: `{state['ledger_sha256']}`",
        "",
        "## Scope and impacts",
        "",
    ]
    scopes = [item for item in records if item["kind"] == "SCOPE"]
    lines.extend([f"- {item['id']} [{item['status']}]: {item['statement']}" for item in scopes] or ["- No scope records yet."])
    lines.extend(["", "## Open investigations and tasks", ""])
    focus = [item for item in active if item["kind"] in {"INV", "TASK", "EXP"}]
    for item in focus:
        suffix = f" Next: {item['next_action']}" if item.get("next_action") else ""
        lines.append(f"- {item['id']} [{item['priority']}/{item['status']}]: {item['statement']}{suffix}")
    if not focus:
        lines.append("- None.")
    lines.extend(["", "## Grounded facts and scoped refutations", ""])
    facts = [item for item in records if item["kind"] == "FACT" or item["status"] == "refuted"]
    lines.extend([f"- {item['id']} [{item['status']}]: {item['statement']}" for item in facts[-20:]] or ["- None."])
    lines.extend(["", "## Latest experiments and syntheses", ""])
    latest = [item for item in records if item["kind"] in {"EXP", "SYN"}][-12:]
    lines.extend([f"- {item['id']} [{item['status']}]: {item['statement']}" for item in latest] or ["- None."])
    return "\n".join(lines) + "\n"


def _write_state(root: Path, state: dict[str, Any]) -> dict[str, Any]:
    ledger_path, tsv_path, brief_path = _paths(root)
    state["updated_at"] = utc_now()
    state["ledger_sha256"] = _state_digest(state)
    validate_ledger(state)
    _write_json_atomic_raw(ledger_path, state)
    write_text_atomic(tsv_path, _render_tsv(state), mode=0o644)
    write_text_atomic(brief_path, _render_brief(state), mode=0o644)
    return state


def _write_views(root: Path, state: dict[str, Any]) -> None:
    """Regenerate derived views without mutating canonical ledger state."""
    _, tsv_path, brief_path = _paths(root)
    write_text_atomic(tsv_path, _render_tsv(state), mode=0o644)
    write_text_atomic(brief_path, _render_brief(state), mode=0o644)


def initialize_ledger(root: Path) -> dict[str, Any]:
    campaign = require_campaign(root)
    ledger_path, _, _ = _paths(root)
    with exclusive_lock(root):
        if ledger_path.is_file():
            return validate_ledger(read_json(ledger_path))
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        now = utc_now()
        state = {
            "schema": LEDGER_SCHEMA,
            "revision": 0,
            "campaign": {
                "label": campaign.get("label"),
                "target": campaign.get("target"),
                "chain": campaign.get("chain"),
                "source": campaign.get("source", {}).get("path"),
            },
            "created_at": now,
            "updated_at": now,
            "next_ids": {kind: 1 for kind in sorted(KINDS)},
            "records": {},
            "legacy_map": {},
        }
        return _write_state(root, state)


def load_ledger(root: Path) -> dict[str, Any]:
    ledger_path, _, _ = _paths(root)
    if not ledger_path.is_file():
        return initialize_ledger(root)
    return validate_ledger(read_json(ledger_path))


def _next_id(state: dict[str, Any], kind: str) -> str:
    value = int(state["next_ids"][kind])
    state["next_ids"][kind] = value + 1
    return f"{PREFIXES[kind]}-{value:04d}"


def add_record(
    root: Path,
    *,
    kind: str,
    title: str,
    statement: str,
    status: str = "open",
    priority: str = "medium",
    stage: str | None = None,
    parents: list[str] | None = None,
    scope: list[str] | None = None,
    evidence: list[str] | None = None,
    artifacts: list[str] | None = None,
    next_action: str = "",
    owner: str = "primary",
    data: dict[str, Any] | None = None,
    legacy_source: str | None = None,
) -> dict[str, Any]:
    kind = kind.upper()
    if kind not in KINDS or status not in STATUSES or priority not in PRIORITIES:
        raise ValidationError("unsupported ledger kind, status, or priority")
    if kind == "INV":
        stage = stage or "lead"
        if stage not in INVESTIGATION_STAGES:
            raise ValidationError("unsupported investigation stage")
    elif stage:
        raise ValidationError("only investigations have a stage")
    with exclusive_lock(root):
        state = load_ledger(root)
        if legacy_source and legacy_source in state["legacy_map"]:
            return state["records"][state["legacy_map"][legacy_source]]
        identifier = _next_id(state, kind)
        now = utc_now()
        record = {
            "id": identifier,
            "revision": 1,
            "kind": kind,
            "status": status,
            "stage": stage,
            "priority": priority,
            "title": _text(title, "title"),
            "statement": _text(statement, "statement"),
            "parents": list(parents or []),
            "scope": list(scope or []),
            "evidence": list(evidence or []),
            "artifacts": list(artifacts or []),
            "next_action": _text(next_action, "next_action", required=False),
            "owner": _text(owner, "owner"),
            "data": dict(data or {}),
            "transitions": [],
            "created_at": now,
            "updated_at": now,
            "legacy_source": legacy_source,
        }
        state["records"][identifier] = record
        if legacy_source:
            state["legacy_map"][legacy_source] = identifier
        state["revision"] += 1
        _write_state(root, state)
        return record


def update_record(
    root: Path,
    identifier: str,
    *,
    expected_revision: int,
    changes: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    allowed = {"status", "stage", "priority", "title", "statement", "parents", "scope", "evidence", "artifacts", "next_action", "owner", "data"}
    unknown = set(changes) - allowed
    if unknown:
        raise ValidationError("unsupported ledger update fields: " + ", ".join(sorted(unknown)))
    with exclusive_lock(root):
        state = load_ledger(root)
        if identifier not in state["records"]:
            raise ValidationError(f"unknown ledger record: {identifier}")
        record = state["records"][identifier]
        if int(record["revision"]) != expected_revision:
            raise IntegrityError(f"stale ledger revision for {identifier}: expected {expected_revision}, current {record['revision']}")
        before = {key: record.get(key) for key in changes}
        if "status" in changes and changes["status"] not in STATUSES:
            raise ValidationError("unsupported ledger status")
        if "priority" in changes and changes["priority"] not in PRIORITIES:
            raise ValidationError("unsupported ledger priority")
        if "stage" in changes:
            if record["kind"] != "INV" or changes["stage"] not in INVESTIGATION_STAGES:
                raise ValidationError("invalid investigation stage transition")
        record.update(changes)
        record["revision"] += 1
        record["updated_at"] = utc_now()
        record["transitions"].append({
            "at": record["updated_at"],
            "reason": _text(reason, "transition reason"),
            "before": before,
            "after": {key: record.get(key) for key in changes},
        })
        state["revision"] += 1
        _write_state(root, state)
        return record


def query_ledger(
    root: Path,
    *,
    kind: str | None = None,
    status: str | None = None,
    priority: str | None = None,
    scope_id: str | None = None,
) -> list[dict[str, Any]]:
    state = load_ledger(root)
    result = list(state["records"].values())
    if kind:
        result = [item for item in result if item["kind"] == kind.upper()]
    if status:
        result = [item for item in result if item["status"] == status]
    if priority:
        result = [item for item in result if item["priority"] == priority]
    if scope_id:
        result = [item for item in result if scope_id in item["scope"] or item["id"] == scope_id]
    return sorted(result, key=_record_sort_key)


def show_record(root: Path, identifier: str) -> dict[str, Any]:
    state = load_ledger(root)
    try:
        return state["records"][identifier]
    except KeyError as exc:
        raise ValidationError(f"unknown ledger record: {identifier}") from exc


def require_scope_impact(root: Path, scope_id: str, exact_impact: str) -> dict[str, Any]:
    """Resolve one exact eligible impact under one active program scope."""
    scope = show_record(root, _text(scope_id, "scope id"))
    if scope.get("kind") != "SCOPE" or scope.get("status") != "active":
        raise ValidationError("candidate scope must reference an active SCOPE ledger record")
    impact = _text(exact_impact, "eligible impact")
    impacts = scope.get("data", {}).get("impacts", [])
    if impact not in impacts:
        raise ValidationError(
            f"eligible impact must exactly match one data.impacts entry in {scope_id}"
        )
    return scope


def link_runtime_ref(
    root: Path,
    identifier: str,
    runtime_ref: str,
    *,
    expected_kind: str,
    reason: str,
    stage: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Atomically cross-link a typed runtime artifact to its canonical ledger record."""
    with exclusive_lock(root):
        state = load_ledger(root)
        if identifier not in state["records"]:
            raise ValidationError(f"unknown ledger record: {identifier}")
        record = state["records"][identifier]
        if record.get("kind") != expected_kind:
            raise ValidationError(f"{identifier} must be a {expected_kind} ledger record")
        if stage is not None and (expected_kind != "INV" or stage not in INVESTIGATION_STAGES):
            raise ValidationError("runtime linkage requested an invalid investigation stage")
        if status is not None and status not in STATUSES:
            raise ValidationError("runtime linkage requested an invalid status")
        data = dict(record.get("data", {}))
        refs = list(data.get("runtime_refs", []))
        normalized_ref = _text(runtime_ref, "runtime reference")
        if normalized_ref in refs and (stage is None or record.get("stage") == stage) and (status is None or record.get("status") == status):
            return record
        before = {
            "runtime_refs": refs,
            "stage": record.get("stage"),
            "status": record.get("status"),
        }
        if normalized_ref not in refs:
            refs.append(normalized_ref)
        data["runtime_refs"] = refs
        record["data"] = data
        if stage is not None:
            record["stage"] = stage
        if status is not None:
            record["status"] = status
        record["revision"] += 1
        record["updated_at"] = utc_now()
        record["transitions"].append({
            "at": record["updated_at"],
            "reason": _text(reason, "runtime linkage reason"),
            "before": before,
            "after": {
                "runtime_refs": refs,
                "stage": record.get("stage"),
                "status": record.get("status"),
            },
        })
        state["revision"] += 1
        _write_state(root, state)
        return record


def verify_ledger(root: Path, *, repair_views: bool = False) -> dict[str, Any]:
    state = load_ledger(root)
    _, tsv_path, brief_path = _paths(root)
    expected_tsv = _render_tsv(state)
    expected_brief = _render_brief(state)
    views_current = tsv_path.is_file() and brief_path.is_file() and tsv_path.read_text(encoding="utf-8") == expected_tsv and brief_path.read_text(encoding="utf-8") == expected_brief
    if repair_views and not views_current:
        with exclusive_lock(root):
            # Reload after acquiring the campaign lock. A writer may have
            # committed a newer canonical ledger while views were compared.
            ledger_path, tsv_path, brief_path = _paths(root)
            state = validate_ledger(read_json(ledger_path))
            _write_views(root, state)
            expected_tsv = _render_tsv(state)
            expected_brief = _render_brief(state)
            views_current = (
                tsv_path.read_text(encoding="utf-8") == expected_tsv
                and brief_path.read_text(encoding="utf-8") == expected_brief
            )
    return {
        "valid": True,
        "revision": state["revision"],
        "records": len(state["records"]),
        "ledger_sha256": state["ledger_sha256"],
        "views_current": views_current,
    }


def brief(root: Path) -> dict[str, Any]:
    state = load_ledger(root)
    return {
        "ledger_sha256": state["ledger_sha256"],
        "revision": state["revision"],
        "scope": query_ledger(root, kind="SCOPE"),
        "open": [item for item in query_ledger(root) if item["status"] in {"open", "active", "blocked"}],
        "brief_path": str(_paths(root)[2]),
    }


def _link_legacy_candidate(root: Path, *, source: str, candidate: dict[str, Any]) -> str | None:
    hypothesis_id = str(candidate.get("hypothesis_id") or "").strip()
    hypothesis_source = f"hypotheses/{hypothesis_id}.json"
    with exclusive_lock(root):
        state = load_ledger(root)
        if source in state["legacy_map"]:
            return state["legacy_map"][source]
        investigation_id = state["legacy_map"].get(hypothesis_source)
        if not investigation_id:
            return None
        record = state["records"][investigation_id]
        legacy_candidates = list(record["data"].get("legacy_candidates", []))
        legacy_candidates.append(candidate)
        record["data"]["legacy_candidates"] = legacy_candidates
        record["stage"] = "validated" if candidate.get("status") == "validated" else "candidate"
        record["status"] = "validated" if candidate.get("status") == "validated" else "active"
        record["revision"] += 1
        record["updated_at"] = utc_now()
        record["transitions"].append({
            "at": record["updated_at"],
            "reason": f"imported legacy candidate {source}",
            "before": {"stage": "hypothesis"},
            "after": {"stage": record["stage"], "status": record["status"]},
        })
        state["legacy_map"][source] = investigation_id
        state["revision"] += 1
        _write_state(root, state)
        return investigation_id


def migrate_v4(root: Path, *, apply: bool) -> dict[str, Any]:
    """Create an additive V5 sidecar. Never mutate legacy campaign records."""
    campaign = require_campaign(root)
    sources: list[tuple[str, str, str, str, dict[str, Any]]] = []
    sources.append((
        "campaign.json", "SCOPE", f"Program scope for {campaign.get('target')}",
        str(campaign.get("authorization") or "Authorized target boundary"),
        {"target": campaign.get("target"), "chain": campaign.get("chain"), "source": campaign.get("source")},
    ))
    for path in sorted((root / "obligations").glob("*.json")):
        item = read_json(path)
        sources.append((path.relative_to(root).as_posix(), "OBL", str(item.get("title") or item.get("id") or path.stem), str(item.get("statement") or item.get("property") or "Imported obligation"), item))
    for path in sorted((root / "hypotheses").glob("*.json")):
        item = read_json(path)
        sources.append((path.relative_to(root).as_posix(), "INV", str(item.get("title") or item.get("id") or path.stem), str(item.get("mechanism") or item.get("statement") or "Imported investigation"), item))
    for path in sorted((root / "frontier").glob("*.json")):
        item = read_json(path)
        sources.append((path.relative_to(root).as_posix(), "TASK", str(item.get("frontier_kind") or item.get("id") or path.stem), str(item.get("statement") or "Imported unresolved question"), {"question": item.get("statement") or "Imported unresolved question", "legacy": item}))
    candidates = [(path.relative_to(root).as_posix(), read_json(path)) for path in sorted((root / "candidates").glob("*.json"))]
    ledger_path, _, _ = _paths(root)
    existing = load_ledger(root) if ledger_path.is_file() else None
    known = set((existing or {}).get("legacy_map", {}))
    pending = [source for source in sources if source[0] not in known]
    pending_candidates = [source for source in candidates if source[0] not in known]
    if not apply:
        return {"apply": False, "pending": len(pending) + len(pending_candidates), "sources": [item[0] for item in pending] + [item[0] for item in pending_candidates]}
    initialize_ledger(root)
    imported = []
    for source, kind, title, statement, data in pending:
        record = add_record(
            root,
            kind=kind,
            title=title,
            statement=statement,
            status="open",
            priority="high" if kind == "SCOPE" else "medium",
            stage="hypothesis" if kind == "INV" else None,
            next_action=str(data.get("next_action") or "Review imported V4 state and choose the next discriminator"),
            data=data if kind != "TASK" else data,
            legacy_source=source,
        )
        imported.append(record["id"])
    for source, candidate in pending_candidates:
        linked = _link_legacy_candidate(root, source=source, candidate=candidate)
        if linked:
            imported.append(linked)
        else:
            record = add_record(
                root,
                kind="INV",
                title=str(candidate.get("id") or Path(source).stem),
                statement=str(candidate.get("root_cause") or candidate.get("property") or "Imported legacy candidate"),
                status="validated" if candidate.get("status") == "validated" else "active",
                priority="high",
                stage="validated" if candidate.get("status") == "validated" else "candidate",
                next_action="Review imported candidate evidence, impact, and applicability",
                data={"legacy_candidate": candidate},
                legacy_source=source,
            )
            imported.append(record["id"])
    return {"apply": True, "imported": imported, "pending_after": 0, "ledger": verify_ledger(root)}
