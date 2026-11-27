from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .rpc_broker import LOCAL_METHODS, uds_call


def _response(identifier: Any, *, result: Any = None, error: dict[str, Any] | None = None) -> dict[str, Any]:
    value = {"jsonrpc": "2.0", "id": identifier}
    value["error" if error else "result"] = error if error else result
    return value


def _tool_definitions() -> list[dict[str, Any]]:
    return [
        {
            "name": "rpc",
            "description": (
                "Call one allowlisted JSON-RPC method on this lane's disposable, pinned, "
                "credential-free Anvil fork. This never targets a live chain. Use it for "
                "eth_call, state reads, snapshots/reverts, impersonation, local transactions, "
                "mining controls, and traces. Upstream-retargeting and node-metadata methods "
                "are blocked by the host broker."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "method": {"type": "string", "enum": sorted(LOCAL_METHODS)},
                    "params": {"type": "array"},
                },
                "required": ["method", "params"],
                "additionalProperties": False,
            },
        },
        {
            "name": "identity",
            "description": "Read the chain ID, current pinned block number, and block hash from this lane's local fork.",
            "inputSchema": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    ]


def dispatch(request: dict[str, Any], socket_path: Path) -> dict[str, Any] | None:
    identifier = request.get("id")
    method = request.get("method")
    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _response(
            identifier,
            result={
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "a1x-lane-fork", "version": "4.4.0"},
            },
        )
    if method == "tools/list":
        return _response(identifier, result={"tools": _tool_definitions()})
    if method == "tools/call":
        params = request.get("params", {})
        name = params.get("name")
        arguments = params.get("arguments", {})
        try:
            if name == "rpc":
                rpc_method = arguments.get("method")
                rpc_params = arguments.get("params")
                if not isinstance(rpc_method, str) or rpc_method not in LOCAL_METHODS:
                    raise ValueError("RPC method is not allowlisted for the lane fork")
                if not isinstance(rpc_params, list):
                    raise ValueError("RPC params must be an array")
                value = uds_call(socket_path, rpc_method, rpc_params)
            elif name == "identity":
                chain_id = uds_call(socket_path, "eth_chainId", [])
                block_number = uds_call(socket_path, "eth_blockNumber", [])
                block = uds_call(socket_path, "eth_getBlockByNumber", [block_number, False])
                value = {
                    "chain_id": chain_id,
                    "block_number": block_number,
                    "block_hash": block.get("hash") if isinstance(block, dict) else None,
                    "local_disposable_fork": True,
                    "upstream_credential_exposed": False,
                }
            else:
                return _response(identifier, error={"code": -32601, "message": f"unknown tool: {name}"})
            wrapped = {"result": value}
            return _response(
                identifier,
                result={
                    "content": [{"type": "text", "text": json.dumps(wrapped, sort_keys=True)}],
                    "structuredContent": wrapped,
                },
            )
        except Exception as exc:
            return _response(
                identifier,
                result={
                    "isError": True,
                    "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}],
                },
            )
    return _response(identifier, error={"code": -32601, "message": f"unknown method: {method}"})


def serve_stdio(socket_path: Path) -> None:
    for line in sys.stdin:
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                raise ValueError("request must be an object")
            response = dispatch(request, socket_path)
        except Exception as exc:
            response = _response(None, error={"code": -32700, "message": f"parse error: {type(exc).__name__}"})
        if response is not None:
            sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
            sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="a1x-lane-fork-mcp")
    parser.add_argument("--socket", required=True, type=Path)
    args = parser.parse_args(argv)
    socket_path = args.socket.expanduser().resolve()
    if not socket_path.exists():
        parser.error("lane fork socket does not exist")
    serve_stdio(socket_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
