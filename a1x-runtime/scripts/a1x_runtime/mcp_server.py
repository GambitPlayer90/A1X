from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable

from .adapters import capability_matrix
from .campaign import show_campaign
from .evidence_bundles import load_bundle, verify_bundle
from .explorer import retrieve_verified_contract
from .operations import recommend_next
from .records import verify_event_chain
from .rsa import build_compatibility_graph


def _root(arguments: dict[str, Any]) -> Path:
    return Path(str(arguments["root"])).expanduser().resolve()


TOOLS: dict[str, tuple[str, dict[str, Any], Callable[[dict[str, Any]], Any]]] = {
    "campaign_show": ("Inspect an A1X campaign", {"root": {"type": "string"}}, lambda a: show_campaign(_root(a))),
    "event_chain_verify": ("Verify the authoritative hash-chained event log", {"root": {"type": "string"}}, lambda a: verify_event_chain(_root(a))),
    "capability_show": ("Inspect target backend capabilities", {"root": {"type": "string"}}, lambda a: capability_matrix(_root(a))),
    "evidence_show": ("Read one typed EvidenceBundle", {"root": {"type": "string"}, "evidence_id": {"type": "string"}}, lambda a: load_bundle(_root(a), str(a["evidence_id"]))),
    "evidence_verify": ("Verify one typed EvidenceBundle", {"root": {"type": "string"}, "evidence_id": {"type": "string"}}, lambda a: verify_bundle(_root(a), str(a["evidence_id"]))),
    "route_next": (
        "Route the next experiment by its unresolved blocker",
        {"root": {"type": "string"}, "blocker": {"type": "string"}, "available_backends": {"type": "array", "items": {"type": "string"}}},
        lambda a: recommend_next(_root(a), blocker=str(a["blocker"]), available_backends=list(a["available_backends"])),
    ),
    "rsa_graph": (
        "Create a semantic compatibility graph over immutable evidence",
        {"root": {"type": "string"}, "evidence_ids": {"type": "array", "items": {"type": "string"}}, "campaign_epoch": {"type": "integer"}, "idempotency_key": {"type": "string"}},
        lambda a: build_compatibility_graph(_root(a), list(a["evidence_ids"]), campaign_epoch=int(a["campaign_epoch"]), idempotency_key=str(a["idempotency_key"])),
    ),
    "explorer_retrieve": (
        "Retrieve Etherscan V2 verified metadata host-side and preserve it as immutable recon evidence without exposing the API key",
        {
            "root": {"type": "string"}, "address": {"type": "string"},
            "campaign_epoch": {"type": "integer"},
            "idempotency_key": {"type": "string"},
        },
        lambda a: retrieve_verified_contract(
            _root(a), address=str(a["address"]), api_env="ETHERSCAN_API_KEY",
            campaign_epoch=int(a["campaign_epoch"]), idempotency_key=str(a["idempotency_key"]),
        ),
    ),
}


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": description, "inputSchema": {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}}
        for name, (description, properties, _) in TOOLS.items()
    ]


def _response(identifier: Any, *, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"jsonrpc": "2.0", "id": identifier}
    value["error" if error else "result"] = error if error else result
    return value


def dispatch(request: dict[str, Any]) -> dict[str, Any] | None:
    identifier = request.get("id")
    method = request.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _response(identifier, result={"protocolVersion": "2025-06-18", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "a1x-campaign", "version": "4.4.0"}})
    if method == "tools/list":
        return _response(identifier, result={"tools": _tool_definitions()})
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        if name not in TOOLS:
            return _response(identifier, error={"code": -32601, "message": f"unknown tool: {name}"})
        try:
            value = TOOLS[name][2](params.get("arguments", {}))
            return _response(identifier, result={"content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}], "structuredContent": value})
        except Exception as exc:
            return _response(identifier, result={"isError": True, "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}]})
    return _response(identifier, error={"code": -32601, "message": f"unknown method: {method}"})


def serve_stdio() -> None:
    """Stateless MCP facade; campaign authority remains in the event-sourced runtime."""
    for line in sys.stdin:
        try:
            request = json.loads(line)
            response = dispatch(request)
        except Exception as exc:
            response = _response(None, error={"code": -32700, "message": f"parse error: {type(exc).__name__}"})
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()
