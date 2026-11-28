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


def _address_word(value: Any) -> str | None:
    word = _hex_word(value)
    if word is None:
        return None
    return f"0x{int(word, 16) & ((1 << 160) - 1):040x}"


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
    context: dict[str, Any] = {}
    for _ in range(4):
        if not isinstance(value, dict):
            break
        for key in ("root_address", "address", "to", "contractAddress", "from", "transactionHash"):
            if key in value and key not in context:
                context[key] = value[key]
        if isinstance(value.get("structLogs"), list):
            trace = dict(value)
            trace["_a1x_context"] = context
            return trace
        if isinstance(value.get("trace"), dict):
            value = value["trace"]
            continue
        if isinstance(value.get("result"), dict):
            value = value["result"]
            continue
        break
    if isinstance(value, dict) and ("pre" in value or "post" in value):
        trace = dict(value)
        trace["_a1x_context"] = context
        return trace
    raise ValidationError("unsupported trace document; expected structLogs or prestate diff")


def _explicit_address(log: dict[str, Any]) -> str | None:
    for key in ("storageOwner", "storage_owner", "contract", "address"):
        if key in log:
            address = _address_word(log.get(key))
            if address is not None:
                return address
    return None


def _call_target(op: str, stack: list[str]) -> str | None:
    if op in {"CALL", "CALLCODE", "DELEGATECALL", "STATICCALL"} and len(stack) >= 2:
        return _address_word(stack[-2])
    return None


def _frame_path(value: tuple[int, ...]) -> list[int]:
    return list(value)


def _call_frames(
    logs: list[dict[str, Any]],
    *,
    top_failed: bool,
    root_address: str | None,
) -> tuple[dict[int, dict[str, Any]], list[dict[str, Any]], dict[int, tuple[int, ...]]]:
    """Reconstruct call ancestry so state facts retain storage and revert ownership."""
    if not logs:
        return {}, [], {}
    first_depth = int(logs[0].get("depth", 0))
    frames: dict[tuple[int, ...], dict[str, Any]] = {}
    active: dict[int, tuple[int, ...]] = {}
    index_frames: dict[int, dict[str, Any]] = {}
    child_by_call: dict[int, tuple[int, ...]] = {}
    child_counts: defaultdict[tuple[int, ...], int] = defaultdict(int)
    last_at_depth: dict[int, tuple[int, dict[str, Any]]] = {}

    def create_frame(
        *,
        depth: int,
        parent_path: tuple[int, ...] | None,
        call_index: int | None,
        call_op: str,
        target: str | None,
        explicit: str | None,
    ) -> dict[str, Any]:
        if parent_path is None:
            path = (sum(1 for item in frames if len(item) == 1),)
            storage_owner = explicit or root_address
            executing_address = explicit or root_address
            storage_context = f"address:{storage_owner}" if storage_owner else "frame:" + ".".join(map(str, path))
        else:
            child = child_counts[parent_path]
            child_counts[parent_path] += 1
            path = (*parent_path, child)
            parent = frames[parent_path]
            executing_address = explicit or target
            if call_op in {"DELEGATECALL", "CALLCODE"}:
                storage_owner = parent.get("storage_owner")
                storage_context = str(parent["storage_context"])
            else:
                storage_owner = explicit or target
                storage_context = f"address:{storage_owner}" if storage_owner else "frame:" + ".".join(map(str, path))
        frame = {
            "path": path,
            "depth": depth,
            "parent_path": parent_path,
            "call_index": call_index,
            "call_op": call_op,
            "executing_address": executing_address,
            "storage_owner": storage_owner,
            "storage_context": storage_context,
            "direct_revert": False,
            "reverted": False,
            "start_index": None,
            "end_index": None,
        }
        frames[path] = frame
        active[depth] = path
        if call_index is not None:
            child_by_call[call_index] = path
        return frame

    create_frame(
        depth=first_depth,
        parent_path=None,
        call_index=None,
        call_op="ROOT",
        target=root_address,
        explicit=_explicit_address(logs[0]),
    )
    for index, log in enumerate(logs):
        depth = int(log.get("depth", first_depth))
        for stale_depth in sorted((item for item in active if item > depth), reverse=True):
            active.pop(stale_depth, None)
        explicit = _explicit_address(log)
        frame = frames.get(active.get(depth, ()))
        if frame is None:
            parent_depth = max((item for item in active if item < depth), default=None)
            parent_path = active.get(parent_depth) if parent_depth is not None else None
            call_index = None
            call_op = "UNKNOWN"
            target = None
            if parent_depth is not None and parent_depth in last_at_depth:
                candidate_index, candidate = last_at_depth[parent_depth]
                candidate_op = str(candidate.get("op", "")).upper()
                if candidate_op in CALL_OPS:
                    call_index = candidate_index
                    call_op = candidate_op
                    target = _call_target(candidate_op, _stack(candidate))
            frame = create_frame(
                depth=depth,
                parent_path=parent_path,
                call_index=call_index,
                call_op=call_op,
                target=target,
                explicit=explicit,
            )
        elif explicit is not None and frame.get("executing_address") not in {None, explicit}:
            # Enriched/compressed traces can identify sibling frames without
            # retaining the intervening parent opcode. Keep them separate.
            parent_depth = max((item for item in active if item < depth), default=None)
            parent_path = active.get(parent_depth) if parent_depth is not None else None
            frame = create_frame(
                depth=depth,
                parent_path=parent_path,
                call_index=None,
                call_op="ENRICHED",
                target=explicit,
                explicit=explicit,
            )
        elif explicit is not None and frame.get("executing_address") is None:
            frame["executing_address"] = explicit
            if frame.get("call_op") not in {"DELEGATECALL", "CALLCODE"}:
                frame["storage_owner"] = explicit
                frame["storage_context"] = f"address:{explicit}"
        if frame["start_index"] is None:
            frame["start_index"] = index
        frame["end_index"] = index
        op = str(log.get("op", "")).upper()
        if op in {"REVERT", "INVALID"} or bool(log.get("error")):
            frame["direct_revert"] = True
        index_frames[index] = frame
        last_at_depth[depth] = (index, log)
    if top_failed:
        for path, frame in frames.items():
            if len(path) == 1:
                frame["direct_revert"] = True
    for path in sorted(frames, key=len):
        frame = frames[path]
        parent = frames.get(frame.get("parent_path"))
        frame["reverted"] = bool(frame["direct_revert"] or (parent and parent["reverted"]))
    public_frames = [
        {
            "path": _frame_path(frame["path"]),
            "depth": frame["depth"],
            "parent_path": _frame_path(frame["parent_path"]) if frame["parent_path"] is not None else None,
            "call_index": frame["call_index"],
            "call_op": frame["call_op"],
            "executing_address": frame["executing_address"],
            "storage_owner": frame["storage_owner"],
            "storage_context": frame["storage_context"],
            "storage_context_resolved": frame["storage_owner"] is not None,
            "direct_revert": frame["direct_revert"],
            "reverted": frame["reverted"],
            "start_index": frame["start_index"],
            "end_index": frame["end_index"],
        }
        for _, frame in sorted(frames.items())
    ]
    return index_frames, public_frames, child_by_call


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
            "frames": [],
            "calls": [],
            "loads": [],
            "writes": [],
            "overwrites": [],
            "transient_windows": [],
            "revert_boundaries": [],
            "halts": [],
            "state_diff": _state_diff(trace),
            "residuals": _residuals(declared_metrics or []),
            "limitations": ["prestate diff contains final state changes only; it cannot expose overwritten or transient writes"],
        }
    normalized_logs = [item for item in logs if isinstance(item, dict)]
    top_failed = bool(trace.get("failed"))
    context = trace.get("_a1x_context") if isinstance(trace.get("_a1x_context"), dict) else {}
    root_address = next(
        (
            address
            for key in ("root_address", "to", "address", "contractAddress")
            if (address := _address_word(context.get(key))) is not None
        ),
        None,
    )
    index_frames, frames, child_by_call = _call_frames(
        normalized_logs,
        top_failed=top_failed,
        root_address=root_address,
    )
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
        frame = index_frames.get(index, {})
        base = {
            "index": index,
            "pc": pc,
            "depth": depth,
            "op": op,
            "frame_path": _frame_path(frame.get("path", ())),
            "executing_address": frame.get("executing_address"),
            "storage_owner": frame.get("storage_owner"),
            "storage_context": frame.get("storage_context"),
            "storage_context_resolved": frame.get("storage_owner") is not None,
        }
        if op in STORE_OPS:
            slot = _hex_word(stack[-1]) if len(stack) >= 1 else None
            value = _hex_word(stack[-2]) if len(stack) >= 2 else None
            writes.append(
                {
                    **base,
                    "storage": STORE_OPS[op],
                    "slot": slot,
                    "value": value,
                    "reverted": bool(frame.get("reverted")),
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
            target = _call_target(op, stack)
            value = _hex_word(stack[-3]) if op in {"CALL", "CALLCODE"} and len(stack) >= 3 else None
            child_path = child_by_call.get(index)
            calls.append(
                {
                    **base,
                    "target": target,
                    "value": value,
                    "child_frame_path": _frame_path(child_path) if child_path is not None else None,
                }
            )
        if op in HALT_OPS:
            halt = {**base, "error": log.get("error"), "stack_tail": [_hex_word(item) for item in stack[-4:]]}
            halts.append(halt)
            if op in {"REVERT", "INVALID"}:
                reverts.append(halt)
    grouped: dict[tuple[str, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for write in writes:
        grouped[(write["storage"], str(write["storage_context"]), write["slot"])].append(write)
    overwrites = []
    transient_windows = []
    for (storage, storage_context, slot), values in sorted(grouped.items(), key=lambda item: str(item[0])):
        distinct = []
        for value in values:
            if value["value"] not in distinct:
                distinct.append(value["value"])
        if len(values) > 1:
            overwrites.append(
                {
                    "storage": storage,
                    "storage_context": storage_context,
                    "storage_owner": values[0]["storage_owner"],
                    "storage_context_resolved": values[0]["storage_context_resolved"],
                    "frame_paths": [item["frame_path"] for item in values],
                    "slot": slot,
                    "values": distinct,
                    "write_indices": [item["index"] for item in values],
                    "restored_or_overwritten": len(distinct) > 1,
                    "any_reverted": any(item["reverted"] for item in values),
                }
            )
            first = values[0]["index"]
            last = values[-1]["index"]
            window_calls = [call for call in calls if first < call["index"] < last]
            if window_calls and len(distinct) > 1:
                transient_windows.append(
                    {
                        "storage": storage,
                        "storage_context": storage_context,
                        "storage_owner": values[0]["storage_owner"],
                        "storage_context_resolved": values[0]["storage_context_resolved"],
                        "frame_paths": [item["frame_path"] for item in values],
                        "slot": slot,
                        "open_write_index": first,
                        "close_write_index": last,
                        "temporary_values": distinct[:-1],
                        "closing_value": distinct[-1],
                        "external_calls": window_calls,
                        "classification": "candidate transient invariant window; protocol meaning and final restoration require an oracle",
                    }
                )
    return {
        "format": "struct-logs",
        "failed": top_failed,
        "gas": trace.get("gas"),
        "return_value": trace.get("returnValue"),
        "frames": frames,
        "calls": calls,
        "loads": loads,
        "writes": writes,
        "overwrites": overwrites,
        "transient_windows": transient_windows,
        "revert_boundaries": reverts,
        "halts": halts,
        "state_diff": [],
        "residuals": _residuals(declared_metrics or []),
        "limitations": [
            "struct logs expose executed opcodes, not protocol meaning",
            *(
                ["one or more storage owners remain unresolved; those writes are isolated by call frame and are not merged across unknown contexts"]
                if any(frame.get("storage_context_resolved") is not True for frame in frames)
                else []
            ),
            "CREATE/CREATE2 storage ownership requires an enriched address or a separately derived creation address",
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
