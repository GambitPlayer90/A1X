from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


WITNESS_KINDS = {"reachable-prefix", "prerequisite-resolved", "settlement", "impact", "stronger-oracle"}
INFORMATION_KINDS = {"feasible-region", "revert-region", "ordering", "dependency", "assumption-refuted", "state-equivalence"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"research progress {field} must be non-empty")
    return result


def _decimal(value: Any, field: str) -> str:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"research progress {field} must be an exact decimal") from exc
    if not parsed.is_finite():
        raise ValidationError(f"research progress {field} must be finite")
    return format(parsed, "f")


def _constraints(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise ValidationError("information progress constraints must be an array of objects")
    output = []
    seen: set[str] = set()
    for item in raw:
        name = _text(item.get("variable"), "constraint.variable")
        if name in seen:
            raise ValidationError(f"duplicate information-progress variable: {name}")
        seen.add(name)
        lower = _decimal(item.get("lower"), f"constraint {name} lower")
        upper = _decimal(item.get("upper"), f"constraint {name} upper")
        if Decimal(lower) > Decimal(upper):
            raise ValidationError(f"constraint lower exceeds upper for {name}")
        excluded = sorted({_decimal(value, f"constraint {name} excluded") for value in item.get("excluded", [])}, key=Decimal)
        output.append({"variable": name, "lower": lower, "upper": upper, "excluded": excluded, "unit": _text(item.get("unit"), f"constraint {name} unit")})
    return sorted(output, key=lambda item: item["variable"])


def _constraint_advances(parent: list[dict[str, Any]], child: list[dict[str, Any]]) -> bool:
    prior = {item["variable"]: item for item in parent}
    current = {item["variable"]: item for item in child}
    if not prior or set(prior) != set(current):
        return bool(child) and not prior
    advanced = False
    for name, old in prior.items():
        new = current[name]
        if new["unit"] != old["unit"]:
            raise ValidationError(f"constraint unit changed for {name}")
        if Decimal(new["lower"]) < Decimal(old["lower"]) or Decimal(new["upper"]) > Decimal(old["upper"]):
            raise ValidationError(f"information progress widened the feasible interval for {name}")
        if not set(old["excluded"]) <= set(new["excluded"]):
            raise ValidationError(f"information progress removed excluded points for {name}")
        advanced |= (
            Decimal(new["lower"]) > Decimal(old["lower"])
            or Decimal(new["upper"]) < Decimal(old["upper"])
            or set(new["excluded"]) > set(old["excluded"])
        )
    return advanced


def record_progress(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "semantic_progress"):
        raise ValidationError("structured semantic progress is disabled by runtime feature policy")
    if not isinstance(payload, dict):
        raise ValidationError("research progress payload must be an object")
    category = str(payload.get("category") or "")
    kind = str(payload.get("kind") or "")
    if category == "witness" and kind not in WITNESS_KINDS:
        raise ValidationError(f"unsupported witness-progress kind: {kind}")
    if category == "information" and kind not in INFORMATION_KINDS:
        raise ValidationError(f"unsupported information-progress kind: {kind}")
    if category not in {"witness", "information"}:
        raise ValidationError("research progress category must be witness or information")
    parent_id = payload.get("parent_id")
    parent = None
    if parent_id:
        parent_id = validate_id(str(parent_id), "PROGRESS")
        parent = read_json(root / "orchestration" / f"{parent_id}.json")
        if parent.get("lineage_id") != str(payload.get("lineage_id")):
            raise ValidationError("research progress parent belongs to another lineage")
        if parent.get("category") != category:
            raise ValidationError("research progress cannot change category across a parent edge")
    refs = normalize_evidence_refs(root, payload.get("evidence_refs", []), required=True)
    details: dict[str, Any]
    if category == "witness":
        phase_index = payload.get("contiguous_phase_index")
        if not isinstance(phase_index, int) or phase_index < 0:
            raise ValidationError("witness progress requires a non-negative contiguous_phase_index")
        if parent and phase_index <= int(parent["details"]["contiguous_phase_index"]):
            raise ValidationError("witness progress must extend the contiguous verified prefix")
        if not any(item.get("type") in {"run-receipt", "replay"} for item in refs):
            raise ValidationError("witness progress requires execution or replay evidence")
        details = {
            "contiguous_phase_index": phase_index,
            "predicate": _text(payload.get("predicate"), "predicate"),
            "observed": _text(payload.get("observed"), "observed"),
            "prerequisite_id": str(payload.get("prerequisite_id") or "").strip() or None,
        }
    else:
        constraints = _constraints(payload.get("constraints", []))
        finding = _text(payload.get("finding"), "finding")
        if parent:
            prior_constraints = parent.get("details", {}).get("constraints", [])
            advanced = _constraint_advances(prior_constraints, constraints)
            if not advanced and finding == parent.get("details", {}).get("finding"):
                raise ValidationError("information progress neither narrowed executed constraints nor added a new finding")
        details = {
            "constraints": constraints,
            "finding": finding,
            "assumptions": sorted({_text(item, "assumption") for item in payload.get("assumptions", [])}),
        }
    progress_id = allocate_id(root, "PROGRESS")
    record = {
        "schema": schema_for(root),
        "kind": "research-progress",
        "id": progress_id,
        "created_at": utc_now(),
        "lineage_id": _text(payload.get("lineage_id"), "lineage_id"),
        "category": category,
        "progress_kind": kind,
        "parent_id": parent_id,
        "details": details,
        "evidence_refs": refs,
    }
    write_json_atomic(root / "orchestration" / f"{progress_id}.json", record)
    event(root, "research.progress-recorded", progress_id=progress_id, lineage_id=record["lineage_id"], category=category)
    return record


def verify_progress(root: Path, progress_id: str) -> dict[str, Any]:
    progress_id = validate_id(progress_id, "PROGRESS")
    record = read_json(root / "orchestration" / f"{progress_id}.json")
    errors = verify_evidence_refs(root, record.get("evidence_refs", []))
    parent_id = record.get("parent_id")
    if parent_id and not (root / "orchestration" / f"{parent_id}.json").is_file():
        errors.append(f"research progress parent is missing: {parent_id}")
    return {"progress_id": progress_id, "valid": not errors, "errors": errors, "record": record}
