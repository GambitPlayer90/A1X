from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable
from typing import Any

from .errors import IntegrityError


PREREQUISITE_STATES = {"open", "narrowed", "blocked", "resolved", "refuted"}
OPEN_PREREQUISITE_STATES = {"open", "narrowed", "blocked"}
PHASE_STATES = {"not-applicable", "open", "blocked", "reached", "demonstrated", "refuted"}

# Profiles express dependency order, not a universal profit funnel.  The final
# phase is the terminal claim for that bug class; intermediate phases are
# independently evidence-bearing waypoints.
WITNESS_PROFILES: dict[str, tuple[str, ...]] = {
    "economic": ("prepare", "trigger", "persist", "settle", "realize", "impact"),
    "settlement": ("prepare", "trigger", "persist", "settle", "impact"),
    "authorization": ("prepare", "cross-authorization", "consume-authority", "impact"),
    "governance": ("prepare", "acquire-influence", "queue", "execute", "impact"),
    "upgrade": ("prepare", "obtain-upgrade-authority", "install-code", "invoke", "impact"),
    "liveness": ("prepare", "block", "persist", "bound-recovery", "impact"),
    "other": ("prepare", "trigger", "persist", "impact"),
}


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9_.$:/-]+", value.lower()))


def _stable_id(prefix: str, *parts: str, length: int = 20) -> str:
    material = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    return f"{prefix}-{hashlib.sha256(material).hexdigest()[:length]}"


def fresh_lineage_id(*parts: str) -> str:
    return _stable_id("LINEAGE", *parts)


def handoff_lineage_id(handoff: dict[str, Any]) -> str:
    verification = handoff.get("runtime_verification", {})
    assigned = str(verification.get("lineage_id", "")).strip()
    if assigned:
        return assigned
    anchored = str(verification.get("family_key", "")).strip()
    if anchored:
        return fresh_lineage_id("legacy-anchor", anchored)
    identity = handoff.get("causal_identity", {})
    return fresh_lineage_id(
        "legacy-handoff",
        _normalize(str(handoff.get("mechanism_family", "unknown"))),
        _normalize(str(identity.get("writer", ""))),
        _normalize(str(identity.get("property", ""))),
    )


def composition_lineage_id(left: dict[str, Any], right: dict[str, Any]) -> str:
    parents = sorted((handoff_lineage_id(left), handoff_lineage_id(right)))
    return fresh_lineage_id("composition", *parents)


def prerequisite_records(handoff: dict[str, Any]) -> list[dict[str, Any]]:
    records = handoff.get("prerequisites")
    if isinstance(records, list) and all(isinstance(item, dict) for item in records):
        return [dict(item) for item in records]
    lineage = handoff_lineage_id(handoff)
    return [
        {
            "id": _stable_id("PREREQ", lineage, _normalize(str(description))),
            "description": str(description).strip(),
            "kind": "other",
            "status": "open",
            "resolution_condition": str(description).strip(),
            "evidence_artifact": "",
        }
        for description in handoff.get("unresolved", [])
        if str(description).strip()
    ]


def canonicalize_prerequisites(
    raw: Any,
    *,
    lineage_id: str,
    parents: Iterable[dict[str, Any]],
    artifact_exists: Callable[[str], bool],
    legacy_unresolved: Iterable[Any] = (),
) -> list[dict[str, Any]]:
    parent_records: dict[str, dict[str, Any]] = {}
    for parent in parents:
        for item in prerequisite_records(parent):
            if str(item.get("id", "")).strip():
                parent_records[str(item["id"])] = dict(item)

    values = raw if isinstance(raw, list) else []
    if not values:
        values = [
            {
                "id": "",
                "description": str(description),
                "kind": "other",
                "status": "open",
                "resolution_condition": str(description),
                "evidence_artifact": "",
            }
            for description in legacy_unresolved
            if str(description).strip()
        ]

    canonical: dict[str, dict[str, Any]] = {}
    for value in values:
        if not isinstance(value, dict):
            raise IntegrityError("prerequisites must contain objects")
        description = str(value.get("description", "")).strip()
        status = str(value.get("status", "open")).strip()
        kind = str(value.get("kind", "other")).strip() or "other"
        condition = str(value.get("resolution_condition", "")).strip()
        evidence = str(value.get("evidence_artifact", "")).strip()
        if not description or not condition:
            raise IntegrityError("every prerequisite requires a description and resolution condition")
        if status not in PREREQUISITE_STATES:
            raise IntegrityError(f"invalid prerequisite status: {status}")
        supplied_id = str(value.get("id", "")).strip()
        prerequisite_id = supplied_id if supplied_id in parent_records else _stable_id(
            "PREREQ", lineage_id, _normalize(description)
        )
        if status in {"narrowed", "resolved", "refuted"}:
            if not evidence or not artifact_exists(evidence):
                raise IntegrityError(
                    f"prerequisite {prerequisite_id} status {status} requires an evidence artifact"
                )
        elif evidence and not artifact_exists(evidence):
            raise IntegrityError(f"prerequisite evidence artifact does not exist: {evidence}")
        canonical[prerequisite_id] = {
            "id": prerequisite_id,
            "description": description,
            "kind": kind,
            "status": status,
            "resolution_condition": condition,
            "evidence_artifact": evidence,
        }

    # A child cannot make an inherited blocker disappear by omission.  It must
    # explicitly close/refute it with evidence or preserve its previous state.
    for prerequisite_id, parent in parent_records.items():
        canonical.setdefault(prerequisite_id, parent)
    return sorted(canonical.values(), key=lambda item: item["id"])


def _infer_bug_class(handoff: dict[str, Any]) -> str:
    text = _normalize(
        " ".join(
            str(handoff.get(key, ""))
            for key in ("mechanism", "mechanism_family", "tested_obligation", "impact_stage")
        )
    )
    if any(token in text for token in ("rounding", "account", "balance", "swap", "rate", "profit", "asset")):
        return "economic"
    if any(token in text for token in ("authorization", "permission", "role", "access")):
        return "authorization"
    if "governance" in text or "vote" in text:
        return "governance"
    if "upgrade" in text or "implementation" in text:
        return "upgrade"
    if any(token in text for token in ("liveness", "denial", "dos", "blocked")):
        return "liveness"
    if "settle" in text or "claim" in text:
        return "settlement"
    return "other"


def canonicalize_witness(
    raw: Any,
    *,
    handoff: dict[str, Any],
    artifact_exists: Callable[[str], bool],
) -> dict[str, Any]:
    execution = handoff.get("execution", {})
    if not isinstance(raw, dict):
        bug_class = _infer_bug_class(handoff)
        command_artifact = str(execution.get("command_artifact", ""))
        trigger_status = "demonstrated" if execution.get("property_violated") is True else (
            "reached" if execution.get("ran") else "open"
        )
        phases = []
        for phase_id in WITNESS_PROFILES[bug_class]:
            status = trigger_status if phase_id in {"trigger", "cross-authorization", "block"} else "open"
            phases.append(
                {
                    "id": phase_id,
                    "status": status,
                    "property": str(execution.get("property", "")) if status != "open" else "",
                    "evidence_artifact": command_artifact if status != "open" else "",
                }
            )
        return {
            "bug_class": bug_class,
            "source_faithful": False,
            "setup_taint": "unknown",
            "phases": phases,
            "signals": [],
        }

    bug_class = str(raw.get("bug_class", "")).strip()
    if bug_class not in WITNESS_PROFILES:
        raise IntegrityError(f"invalid witness bug_class: {bug_class}")
    source_faithful = raw.get("source_faithful")
    setup_taint = str(raw.get("setup_taint", "")).strip()
    if not isinstance(source_faithful, bool):
        raise IntegrityError("witness.source_faithful must be boolean")
    if setup_taint not in {"none", "setup-only", "attack-path", "unknown"}:
        raise IntegrityError(f"invalid witness setup_taint: {setup_taint}")
    if source_faithful and execution.get("ran") is not True:
        raise IntegrityError("a source-faithful witness requires concrete execution")
    if source_faithful and setup_taint == "attack-path":
        raise IntegrityError("attack-path state mutation cannot be marked source-faithful")

    supplied_phases = raw.get("phases")
    if not isinstance(supplied_phases, list):
        raise IntegrityError("witness.phases must be an array")
    by_id: dict[str, dict[str, Any]] = {}
    allowed = set(WITNESS_PROFILES[bug_class])
    for value in supplied_phases:
        if not isinstance(value, dict):
            raise IntegrityError("witness phases must contain objects")
        phase_id = str(value.get("id", "")).strip()
        status = str(value.get("status", "")).strip()
        property_statement = str(value.get("property", "")).strip()
        evidence = str(value.get("evidence_artifact", "")).strip()
        if phase_id not in allowed:
            raise IntegrityError(f"phase {phase_id} is not part of the {bug_class} profile")
        if status not in PHASE_STATES:
            raise IntegrityError(f"invalid phase status: {status}")
        if status in {"reached", "demonstrated", "refuted"}:
            if not property_statement or not evidence or not artifact_exists(evidence):
                raise IntegrityError(f"phase {phase_id} status {status} requires property and evidence")
        elif evidence and not artifact_exists(evidence):
            raise IntegrityError(f"phase evidence artifact does not exist: {evidence}")
        by_id[phase_id] = {
            "id": phase_id,
            "status": status,
            "property": property_statement,
            "evidence_artifact": evidence,
        }

    phases = []
    prior_satisfied = True
    for phase_id in WITNESS_PROFILES[bug_class]:
        phase = by_id.get(
            phase_id,
            {"id": phase_id, "status": "open", "property": "", "evidence_artifact": ""},
        )
        if phase["status"] == "demonstrated" and not prior_satisfied:
            raise IntegrityError(f"phase {phase_id} cannot be demonstrated before its profile predecessor")
        if phase["status"] not in {"reached", "demonstrated", "not-applicable"}:
            prior_satisfied = False
        phases.append(phase)

    signals_raw = raw.get("signals", [])
    if not isinstance(signals_raw, list):
        raise IntegrityError("witness.signals must be an array")
    signals = []
    for value in signals_raw:
        if not isinstance(value, dict):
            raise IntegrityError("witness signals must contain objects")
        kind = str(value.get("kind", "")).strip()
        amount = str(value.get("value", "")).strip()
        unit = str(value.get("unit", "")).strip()
        evidence = str(value.get("evidence_artifact", "")).strip()
        if not kind or not amount or not unit or not evidence or not artifact_exists(evidence):
            raise IntegrityError("every witness signal requires kind, value, unit, and evidence artifact")
        signals.append({"kind": kind, "value": amount, "unit": unit, "evidence_artifact": evidence})

    return {
        "bug_class": bug_class,
        "source_faithful": source_faithful,
        "setup_taint": setup_taint,
        "phases": phases,
        "signals": signals,
    }


def witness_progress(handoff: dict[str, Any]) -> tuple[int, int, int]:
    """Return contiguous-prefix progress plus total demonstrated/reached observations."""
    witness = handoff.get("witness", {})
    phases = witness.get("phases", []) if isinstance(witness, dict) else []
    highest = -1
    demonstrated = 0
    reached = 0
    prefix_open = False
    for index, phase in enumerate(phases):
        status = phase.get("status") if isinstance(phase, dict) else None
        satisfied = status in {"reached", "demonstrated", "not-applicable"}
        if satisfied and not prefix_open:
            highest = index
        elif not satisfied:
            prefix_open = True
        if status == "demonstrated":
            demonstrated += 1
        if status in {"reached", "demonstrated"}:
            reached += 1
    return highest, demonstrated, reached


def witness_terminal(handoff: dict[str, Any]) -> bool:
    witness = handoff.get("witness", {})
    phases = witness.get("phases", []) if isinstance(witness, dict) else []
    return bool(phases and phases[-1].get("status") == "demonstrated")


def has_property_signal(handoff: dict[str, Any]) -> bool:
    witness = handoff.get("witness", {})
    signals = witness.get("signals", []) if isinstance(witness, dict) else []
    return handoff.get("execution", {}).get("property_violated") is True or bool(signals)


def open_prerequisite_ids(handoff: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in prerequisite_records(handoff)
        if item.get("status") in OPEN_PREREQUISITE_STATES
    }


def closed_prerequisite_ids(handoff: dict[str, Any]) -> set[str]:
    return {
        str(item.get("id"))
        for item in prerequisite_records(handoff)
        if item.get("status") in {"resolved", "refuted"}
    }


def needs_witness_closure(handoff: dict[str, Any]) -> bool:
    witness = handoff.get("witness", {})
    return bool(
        handoff.get("status") in {"candidate", "near-miss", "blocked"}
        and handoff.get("execution", {}).get("ran") is True
        and isinstance(witness, dict)
        and witness.get("source_faithful") is True
        and witness.get("setup_taint") in {"none", "setup-only"}
        and (has_property_signal(handoff) or witness_progress(handoff)[2] > 0)
        and open_prerequisite_ids(handoff)
        and not witness_terminal(handoff)
    )


def needs_reachability_closure(handoff: dict[str, Any]) -> bool:
    """Protect a reproducible conditional mechanism while replacing artificial setup."""
    witness = handoff.get("witness", {})
    open_records = [
        item
        for item in prerequisite_records(handoff)
        if item.get("status") in OPEN_PREREQUISITE_STATES
    ]
    exact_state_blocker = any(
        item.get("kind") in {"state", "numeric", "settlement", "timing", "deployment"}
        and str(item.get("resolution_condition", "")).strip()
        for item in open_records
    )
    conditional_setup = isinstance(witness, dict) and (
        witness.get("source_faithful") is False
        or witness.get("setup_taint") in {"attack-path", "unknown"}
    )
    return bool(
        handoff.get("status") in {"candidate", "near-miss", "blocked"}
        and handoff.get("execution", {}).get("ran") is True
        and conditional_setup
        and has_property_signal(handoff)
        and exact_state_blocker
        and handoff.get("evidence")
        and not witness_terminal(handoff)
    )


def closure_mode(handoff: dict[str, Any]) -> str | None:
    if needs_witness_closure(handoff):
        return "witness"
    if needs_reachability_closure(handoff):
        return "reachability"
    return None
