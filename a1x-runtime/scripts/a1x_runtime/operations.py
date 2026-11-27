from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import digest_json, read_json, write_json_atomic
from .errors import StateTransitionError, ValidationError
from .evidence_bundles import load_bundle
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now

TRANSITIONS = {
    "proposed": {"planned", "cancelled"},
    "planned": {"running", "cancelled"},
    "running": {"observed", "failed"},
    "observed": {"resolved", "planned"},
    "failed": {"planned", "resolved"},
    "resolved": set(), "cancelled": set(),
}


def propose_operation(
    root: Path, *, hypothesis_id: str | None, blocker: str, question: str, backend: str,
    expected_information: str, idempotency_key: str, prerequisites: list[str], budget: dict[str, Any],
) -> dict[str, Any]:
    require_v4_campaign(root)
    if not all(item.strip() for item in (blocker, question, backend, expected_information, idempotency_key)):
        raise ValidationError("operation fields must be non-empty")
    request_hash = digest_json({"hypothesis_id": hypothesis_id, "blocker": blocker, "question": question, "backend": backend, "expected_information": expected_information, "prerequisites": prerequisites, "resource_budget": budget})
    for path in (root / "operations").glob("OP-*.json"):
        existing = read_json(path)
        if existing.get("idempotency_key") == idempotency_key:
            if existing.get("request_sha256") != request_hash:
                raise ValidationError("idempotency key was already used for a different operation request")
            return existing

    from .adapters import ADAPTERS

    if backend in ADAPTERS:
        capability_path = root / "capabilities" / "capabilities.json"
        if not capability_path.is_file():
            raise ValidationError("run `a1x capability probe` before routing to a concrete backend")
        capabilities = read_json(capability_path)
        backend_probe = capabilities.get("backends", {}).get(backend, {})
        if backend_probe.get("ready") is not True:
            reason = backend_probe.get("diagnostic", "target probe did not pass")
            raise ValidationError(f"backend {backend} is not ready for this target: {reason}")
    operation_id = allocate_id(root, "OP")
    now = utc_now()
    record = {
        "schema": schema_for(root), "kind": "campaign-operation", "id": operation_id,
        "campaign_epoch": int(require_v4_campaign(root).get("epoch", 0)), "created_at": now, "updated_at": now,
        "status": "proposed", "hypothesis_id": hypothesis_id, "blocker": blocker, "question": question,
        "backend": backend, "expected_information": expected_information, "idempotency_key": idempotency_key,
        "request_sha256": request_hash,
        "prerequisites": prerequisites, "resource_budget": budget, "evidence_ids": [], "history": [],
    }
    write_json_atomic(root / "operations" / f"{operation_id}.json", record)
    event(root, "operation.proposed", operation_id=operation_id, backend=backend, blocker=blocker)
    return record


def transition_operation(root: Path, operation_id: str, *, status: str, evidence_ids: list[str] | None = None, reason: str) -> dict[str, Any]:
    require_v4_campaign(root)
    path = root / "operations" / f"{operation_id}.json"
    record = read_json(path)
    current = record["status"]
    if status not in TRANSITIONS.get(current, set()):
        raise StateTransitionError(f"invalid operation transition: {current} -> {status}")
    for evidence_id in evidence_ids or []:
        load_bundle(root, evidence_id)
    now = utc_now()
    record["history"].append({"from": current, "to": status, "at": now, "reason": reason})
    record["status"] = status
    record["updated_at"] = now
    if evidence_ids:
        record["evidence_ids"] = sorted(set(record["evidence_ids"] + evidence_ids))
    write_json_atomic(path, record)
    event(root, "operation.transitioned", operation_id=operation_id, from_status=current, to_status=status, evidence_ids=evidence_ids or [], reason=reason)
    return record


def recommend_next(root: Path, *, blocker: str, available_backends: list[str]) -> dict[str, Any]:
    require_v4_campaign(root)
    capability_path = root / "capabilities" / "capabilities.json"
    if not capability_path.is_file():
        raise ValidationError("run `a1x capability probe` before routing experiments")
    probed = read_json(capability_path).get("backends", {})
    available_backends = [name for name in available_backends if probed.get(name, {}).get("ready") is True]
    routes = {
        "no-mechanism": ["wake", "foundry", "echidna"],
        "reachability": ["foundry", "wake", "echidna", "ityfuzz"],
        "numeric-condition": ["halmos", "echidna", "wake", "foundry"],
        "coverage-gap": ["echidna", "medusa", "wake", "foundry"],
        "impact-extension": ["foundry", "wake", "echidna"],
        "unverified-bytecode": ["ityfuzz", "foundry"],
        "composition": ["foundry", "wake"],
    }
    ordered = [name for name in routes.get(blocker, ["foundry"]) if name in available_backends]
    return {"blocker": blocker, "recommended": ordered[0] if ordered else None, "fallbacks": ordered[1:], "policy": "route by the unresolved causal edge, not by a fixed tool order"}
