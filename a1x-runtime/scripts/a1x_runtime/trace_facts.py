from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence import normalize_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


STORE_OPS = {"SSTORE": "persistent", "TSTORE": "transient"}
LOAD_OPS = {"SLOAD": "persistent", "TLOAD": "transient"}
CALL_OPS = {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL", "CREATE", "CREATE2"}
HALT_OPS = {"RETURN", "STOP", "REVERT", "INVALID", "SELFDESTRUCT"}


def _hex_word(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    raw = value[2:] if value.startswith("0x") else value
    if not raw:
        return "0x0"
    try:
        return hex(int(raw, 16))
    except ValueError:
        return None


def _stack(log: dict[str, Any]) -> list[str]:
    value = log.get("stack")
    return value if isinstance(value, list) and all(isinstance(item, str) for item in value) else []


def _json_document(path: Path) -> Any:
    text = path.read_text(encoding="utf-8", errors="strict").strip()
    if not text:
        raise ValidationError("trace artifact is empty")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        values = []
        for line in text.splitlines():
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        if not values:
            raise ValidationError("trace artifact does not contain JSON")
        return values[-1]


def _unwrap_trace(document: Any) -> dict[str, Any]:
    value = document
    for _ in range(4):
        if not isinstance(value, dict):
            break
        if isinstance(value.get("structLogs"), list):
            return value
        if isinstance(value.get("trace"), dict):
            value = value["trace"]
            continue
        if isinstance(value.get("result"), dict):
            value = value["result"]
            continue
        break
    if isinstance(value, dict) and ("pre" in value or "post" in value):
        return value
    raise ValidationError("unsupported trace document; expected structLogs or prestate diff")


def _reverted_write(logs: list[dict[str, Any]], index: int, depth: int, top_failed: bool) -> bool:
    if top_failed and depth == 1:
        return True
    for later in logs[index + 1 :]:
        later_depth = int(later.get("depth", depth))
        if later_depth < depth:
            return False
        if later_depth == depth and str(later.get("op", "")).upper() in {"REVERT", "INVALID"}:
            return True
    return False


def _state_diff(document: dict[str, Any]) -> list[dict[str, Any]]:
    pre = document.get("pre") if isinstance(document.get("pre"), dict) else {}
    post = document.get("post") if isinstance(document.get("post"), dict) else {}
    addresses = sorted(set(pre) | set(post))
    changes = []
    for address in addresses:
        before = pre.get(address, {}) if isinstance(pre.get(address, {}), dict) else {}
        after = post.get(address, {}) if isinstance(post.get(address, {}), dict) else {}
        before_storage = before.get("storage", {}) if isinstance(before.get("storage", {}), dict) else {}
        after_storage = after.get("storage", {}) if isinstance(after.get("storage", {}), dict) else {}
        slots = []
        for slot in sorted(set(before_storage) | set(after_storage)):
            left = before_storage.get(slot, "0x0")
            right = after_storage.get(slot, "0x0")
            if left != right:
                slots.append({"slot": slot, "before": left, "after": right})
        entry = {
            "address": address.lower(),
            "balance_before": before.get("balance"),
            "balance_after": after.get("balance"),
            "nonce_before": before.get("nonce"),
            "nonce_after": after.get("nonce"),
            "code_changed": before.get("code") != after.get("code"),
            "storage": slots,
        }
        if slots or any(entry[key] is not None and entry[key] != entry[key.replace("after", "before")] for key in ("balance_after", "nonce_after")) or entry["code_changed"]:
            changes.append(entry)
    return changes


def _residuals(metrics: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for metric in metrics:
        if not isinstance(metric, dict):
            raise ValidationError("declared trace metrics must contain objects")
        name = str(metric.get("name") or "").strip()
        unit = str(metric.get("unit") or "").strip()
        role = str(metric.get("role") or "observation").strip()
        if not name or not unit:
            raise ValidationError("declared trace metric requires name and unit")
        try:
            before = int(str(metric.get("before")), 0)
            after = int(str(metric.get("after")), 0)
        except (TypeError, ValueError) as exc:
            raise ValidationError(f"trace metric {name} requires exact integer before/after values") from exc
        delta = after - before
        output.append(
            {
                "name": name,
                "before": str(before),
                "after": str(after),
                "delta": str(delta),
                "unit": unit,
                "role": role,
                "micro_residual": abs(delta) == 1,
                "interpretation": "unclassified; a protocol oracle must decide whether this delta violates a property",
            }
        )
    return output


def extract_trace_facts(document: Any, *, declared_metrics: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    trace = _unwrap_trace(document)
    logs = trace.get("structLogs")
    if not isinstance(logs, list):
        return {
            "format": "prestate-diff",
            "failed": None,
            "calls": [],
            "loads": [],
            "writes": [],
            "overwrites": [],
            "revert_boundaries": [],
            "halts": [],
            "state_diff": _state_diff(trace),
            "residuals": _residuals(declared_metrics or []),
            "limitations": ["prestate diff contains final state changes only; it cannot expose overwritten or transient writes"],
        }
    normalized_logs = [item for item in logs if isinstance(item, dict)]
    top_failed = bool(trace.get("failed"))
    calls = []
    loads = []
    writes = []
    reverts = []
    halts = []
    for index, log in enumerate(normalized_logs):
        op = str(log.get("op", "")).upper()
        stack = _stack(log)
        depth = int(log.get("depth", 0))
        pc = int(log.get("pc", 0))
        base = {"index": index, "pc": pc, "depth": depth, "op": op}
        if op in STORE_OPS:
            slot = _hex_word(stack[-1]) if len(stack) >= 1 else None
            value = _hex_word(stack[-2]) if len(stack) >= 2 else None
            writes.append(
                {
                    **base,
                    "storage": STORE_OPS[op],
                    "slot": slot,
                    "value": value,
                    "reverted": _reverted_write(normalized_logs, index, depth, top_failed),
                    "transaction_scoped": op == "TSTORE",
                }
            )
        elif op in LOAD_OPS:
            loads.append(
                {
                    **base,
                    "storage": LOAD_OPS[op],
                    "slot": _hex_word(stack[-1]) if stack else None,
                    "transaction_scoped": op == "TLOAD",
                }
            )
        if op in CALL_OPS:
            target = _hex_word(stack[-2]) if op in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"} and len(stack) >= 2 else None
            value = _hex_word(stack[-3]) if op in {"CALL", "CALLCODE"} and len(stack) >= 3 else None
            calls.append({**base, "target": target, "value": value})
        if op in HALT_OPS:
            halt = {**base, "error": log.get("error")}
            halts.append(halt)
            if op in {"REVERT", "INVALID"}:
                reverts.append(halt)
    grouped: dict[tuple[str, int, str | None], list[dict[str, Any]]] = defaultdict(list)
    for write in writes:
        grouped[(write["storage"], write["depth"], write["slot"])].append(write)
    overwrites = []
    for (storage, depth, slot), values in sorted(grouped.items(), key=lambda item: str(item[0])):
        distinct = []
        for value in values:
            if value["value"] not in distinct:
                distinct.append(value["value"])
        if len(values) > 1:
            overwrites.append(
                {
                    "storage": storage,
                    "depth": depth,
                    "slot": slot,
                    "values": distinct,
                    "write_indices": [item["index"] for item in values],
                    "restored_or_overwritten": len(distinct) > 1,
                    "any_reverted": any(item["reverted"] for item in values),
                }
            )
    return {
        "format": "struct-logs",
        "failed": top_failed,
        "gas": trace.get("gas"),
        "return_value": trace.get("returnValue"),
        "calls": calls,
        "loads": loads,
        "writes": writes,
        "overwrites": overwrites,
        "revert_boundaries": reverts,
        "halts": halts,
        "state_diff": [],
        "residuals": _residuals(declared_metrics or []),
        "limitations": [
            "struct logs expose executed opcodes, not protocol meaning",
            "storage ownership across CALL/DELEGATECALL requires call-frame address enrichment",
            "revert stack operands are diagnostic and are not automatically a sound path constraint",
        ],
    }


def analyze_run_trace(
    root: Path,
    *,
    run_id: str,
    path: str,
    declared_metrics: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "trace_facts"):
        raise ValidationError("trace fact extraction is disabled by runtime feature policy")
    run_id = validate_id(run_id, "RUN")
    artifact_ref = normalize_evidence_refs(
        root,
        [{"type": "trace-artifact", "run_id": run_id, "path": path}],
        required=True,
    )[0]
    artifact = root / "runs" / run_id / artifact_ref["path"]
    facts = extract_trace_facts(_json_document(artifact), declared_metrics=declared_metrics)
    fact_id = allocate_id(root, "TRACE")
    record = {
        "schema": schema_for(root),
        "kind": "trace-facts",
        "id": fact_id,
        "created_at": utc_now(),
        "run_id": run_id,
        "source": artifact_ref,
        "facts": facts,
        "semantic_policy": "facts are execution observations; a protocol oracle must establish security meaning",
    }
    write_json_atomic(root / "trace-facts" / f"{fact_id}.json", record)
    event(
        root,
        "trace.analyzed",
        trace_id=fact_id,
        run_id=run_id,
        writes=len(facts["writes"]),
        reverts=len(facts["revert_boundaries"]),
    )
    return record
