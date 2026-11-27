from __future__ import annotations

import hashlib
import http.server
import json
import os
import socket
import socketserver
import threading
import urllib.request
from pathlib import Path
from typing import Any

from .atomic import canonical_bytes, read_json, write_json_atomic
from .errors import ValidationError
from .records import event, require_v4_campaign, schema_for, utc_now

READ_ONLY_METHODS = {
    "eth_chainId", "net_version", "web3_clientVersion", "eth_blockNumber",
    "eth_getBlockByNumber", "eth_getBlockByHash", "eth_getCode", "eth_getStorageAt",
    "eth_getBalance", "eth_getTransactionCount", "eth_getProof", "eth_call",
    "eth_estimateGas", "eth_getLogs", "eth_getTransactionByHash", "eth_getTransactionReceipt",
    "eth_getBlockReceipts", "eth_getTransactionByBlockHashAndIndex",
    "eth_getTransactionByBlockNumberAndIndex", "eth_getBlockTransactionCountByHash",
    "eth_getBlockTransactionCountByNumber", "eth_feeHistory", "eth_gasPrice",
    "eth_maxPriorityFeePerGas", "eth_syncing", "net_listening", "net_peerCount",
    "debug_traceCall", "debug_traceTransaction", "trace_call", "trace_replayTransaction",
    "trace_transaction",
}
BLOCK_LAST = {"eth_getCode", "eth_getStorageAt", "eth_getBalance", "eth_getTransactionCount", "eth_getProof", "eth_call", "eth_estimateGas", "debug_traceCall", "trace_call"}
BLOCK_FIRST = {"eth_getBlockReceipts", "eth_getBlockTransactionCountByNumber", "eth_getTransactionByBlockNumberAndIndex"}
BLOCK_SECOND = {"eth_feeHistory"}
TX_HASH_METHODS = {
    "eth_getTransactionByHash", "eth_getTransactionReceipt", "debug_traceTransaction",
    "trace_replayTransaction", "trace_transaction",
}
BLOCK_HASH_FIRST_METHODS = {
    "eth_getBlockByHash", "eth_getTransactionByBlockHashAndIndex",
    "eth_getBlockTransactionCountByHash",
}
DYNAMIC_BLOCK_TAGS = {"latest", "pending", "safe", "finalized"}


def _upstream(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(url, data=canonical_bytes(payload), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def _bounded_block(value: Any, block_number: int, *, allow_hash: bool = False) -> Any:
    """Pin dynamic tags and reject explicit state beyond the campaign block."""
    if isinstance(value, dict):
        bounded = dict(value)
        if "blockNumber" in bounded:
            bounded["blockNumber"] = _bounded_block(bounded["blockNumber"], block_number)
        # EIP-1898 block hashes are checked against the upstream header in
        # `_ProxyState` before the requested method is forwarded.
        return bounded
    if value in DYNAMIC_BLOCK_TAGS:
        return hex(block_number)
    if value == "earliest":
        return value
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.startswith("0x"):
        if allow_hash and len(value) == 66:
            return value
        try:
            number = int(value, 16)
        except ValueError as exc:
            raise ValidationError("invalid block identifier") from exc
    else:
        raise ValidationError("unsupported block identifier in pinned prestate request")
    if number > block_number:
        raise ValidationError(f"request exceeds pinned block {block_number}")
    return hex(number)


def _pin_request(payload: dict[str, Any], block_number: int) -> dict[str, Any]:
    method = payload.get("method")
    if method not in READ_ONLY_METHODS:
        raise ValidationError(f"prestate method is not read-only: {method}")
    body = dict(payload)
    params = list(body.get("params", []))
    pinned = hex(block_number)
    if method == "eth_blockNumber":
        return {**body, "_a1x_static_result": pinned}
    if method == "eth_getBlockByNumber" and params:
        params[0] = _bounded_block(params[0], block_number)
    elif method in BLOCK_FIRST and params:
        params[0] = _bounded_block(params[0], block_number, allow_hash=method == "eth_getBlockReceipts")
    elif method in BLOCK_SECOND and len(params) > 1:
        params[1] = _bounded_block(params[1], block_number)
    elif method == "eth_getLogs" and params and isinstance(params[0], dict):
        query = dict(params[0])
        if "blockHash" not in query:
            query["fromBlock"] = _bounded_block(query.get("fromBlock", pinned), block_number)
            query["toBlock"] = _bounded_block(query.get("toBlock", pinned), block_number)
        params[0] = query
    elif method in BLOCK_LAST:
        if method in {"eth_call", "eth_estimateGas"} and len(params) == 1:
            params.append(pinned)
        elif params:
            params[-1] = _bounded_block(params[-1], block_number, allow_hash=True)
    body["params"] = params
    return body


class _ProxyState:
    def __init__(self, *, upstream_url: str, block_number: int, cache_dir: Path) -> None:
        self.upstream_url = upstream_url
        self.block_number = block_number
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def _require_block_at_or_before_pin(self, block_hash: str) -> None:
        response = _upstream(
            self.upstream_url,
            {"jsonrpc": "2.0", "id": "a1x-bound", "method": "eth_getBlockByHash", "params": [block_hash, False]},
        )
        block = response.get("result")
        if not isinstance(block, dict) or block.get("number") is None:
            raise ValidationError("block hash is unavailable at the pinned prestate boundary")
        try:
            number = int(str(block["number"]), 16)
        except (TypeError, ValueError) as exc:
            raise ValidationError("block hash resolved to an invalid block number") from exc
        if number > self.block_number:
            raise ValidationError(f"block hash resolves beyond pinned block {self.block_number}")

    def _validate_reference_bounds(self, payload: dict[str, Any]) -> None:
        method = str(payload.get("method", ""))
        params = payload.get("params", [])
        if not isinstance(params, list):
            raise ValidationError("JSON-RPC params must be an array")
        if method in TX_HASH_METHODS and params:
            response = _upstream(
                self.upstream_url,
                {"jsonrpc": "2.0", "id": "a1x-bound", "method": "eth_getTransactionByHash", "params": [params[0]]},
            )
            transaction = response.get("result")
            if transaction is None:
                return
            if not isinstance(transaction, dict) or transaction.get("blockNumber") is None:
                raise ValidationError("pending transaction is outside the pinned prestate boundary")
            try:
                number = int(str(transaction["blockNumber"]), 16)
            except (TypeError, ValueError) as exc:
                raise ValidationError("transaction resolved to an invalid block number") from exc
            if number > self.block_number:
                raise ValidationError(f"transaction resolves beyond pinned block {self.block_number}")

        block_hashes: list[str] = []
        if method in BLOCK_HASH_FIRST_METHODS and params and isinstance(params[0], str):
            block_hashes.append(params[0])
        if method == "eth_getBlockReceipts" and params and isinstance(params[0], str) and len(params[0]) == 66:
            block_hashes.append(params[0])
        if method == "eth_getLogs" and params and isinstance(params[0], dict) and params[0].get("blockHash"):
            block_hashes.append(str(params[0]["blockHash"]))
        if method in BLOCK_LAST and params and isinstance(params[-1], dict) and params[-1].get("blockHash"):
            block_hashes.append(str(params[-1]["blockHash"]))
        for block_hash in set(block_hashes):
            self._require_block_at_or_before_pin(block_hash)

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            pinned = _pin_request(payload, self.block_number)
            self._validate_reference_bounds(pinned)
        except ValidationError as exc:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": -32601, "message": str(exc)}}
        static = pinned.pop("_a1x_static_result", None)
        if static is not None:
            return {"jsonrpc": "2.0", "id": payload.get("id"), "result": static}
        key_body = dict(pinned)
        key_body["id"] = None
        key = hashlib.sha256(canonical_bytes(key_body)).hexdigest()
        path = self.cache_dir / f"{key}.json"
        with self.lock:
            if path.is_file():
                cached = read_json(path)
                cached["id"] = payload.get("id")
                return cached
        response = _upstream(self.upstream_url, pinned)
        cached = dict(response)
        cached["id"] = None
        with self.lock:
            if not path.exists():
                write_json_atomic(path, cached, mode=0o444)
        response["id"] = payload.get("id")
        return response


class _UDSHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(16 * 1024 * 1024)
        try:
            payload = json.loads(line)
            if isinstance(payload, list):
                if len(payload) > 100:
                    raise ValidationError("JSON-RPC batch exceeds 100 requests")
                response = [self.server.state.dispatch(item) for item in payload]  # type: ignore[attr-defined]
            elif isinstance(payload, dict):
                response = self.server.state.dispatch(payload)  # type: ignore[attr-defined]
            else:
                raise ValidationError("JSON-RPC payload must be an object or batch")
        except Exception as exc:
            response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": f"proxy error: {type(exc).__name__}"}}
        self.wfile.write(canonical_bytes(response))


class _ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def serve_proxy(root: Path, *, socket_path: Path, rpc_env: str | None = None) -> None:
    campaign = require_v4_campaign(root)
    env_name = rpc_env or campaign["chain"].get("rpc_env")
    block = campaign["chain"].get("block_number")
    if not env_name or not os.environ.get(env_name):
        raise ValidationError("prestate proxy requires the configured upstream RPC environment variable")
    if not isinstance(block, int):
        raise ValidationError("prestate proxy requires a pinned campaign block")
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    socket_path.unlink(missing_ok=True)
    upstream_url = os.environ[env_name]
    chain_response = _upstream(upstream_url, {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []})
    try:
        observed_chain = int(chain_response["result"], 16)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValidationError("upstream RPC did not return a valid chain ID") from exc
    expected_chain = campaign["chain"].get("chain_id")
    if expected_chain is not None and observed_chain != expected_chain:
        raise ValidationError(f"upstream chain mismatch: expected {expected_chain}, observed {observed_chain}")
    block_response = _upstream(upstream_url, {"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByNumber", "params": [hex(block), False]})
    block_record = block_response.get("result")
    if not isinstance(block_record, dict) or not block_record.get("hash"):
        raise ValidationError("pinned upstream block is unavailable")
    block_hash = str(block_record["hash"])
    state = _ProxyState(upstream_url=upstream_url, block_number=block, cache_dir=root / "prestate" / "cache")
    server = _ThreadingUnixServer(str(socket_path), _UDSHandler)
    server.state = state  # type: ignore[attr-defined]
    os.chmod(socket_path, 0o660)
    manifest = {
        "schema": schema_for(root), "kind": "prestate-service", "created_at": utc_now(),
        "socket": str(socket_path), "block_number": block, "block_hash": block_hash, "chain_id": observed_chain,
        "upstream_secret_exposed": False, "allowed_methods": sorted(READ_ONLY_METHODS),
    }
    write_json_atomic(root / "prestate" / "service.json", manifest)
    event(root, "prestate.started", block_number=block, socket=str(socket_path))
    try:
        server.serve_forever()
    finally:
        server.server_close()
        socket_path.unlink(missing_ok=True)


class _HTTPBridge(http.server.BaseHTTPRequestHandler):
    server_version = "A1XPrestateBridge/4"

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = self.rfile.read(length)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.connect(str(self.server.socket_path))  # type: ignore[attr-defined]
                client.sendall(payload + b"\n")
                chunks = []
                while True:
                    chunk = client.recv(65536)
                    if not chunk:
                        break
                    chunks.append(chunk)
            body = b"".join(chunks)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_error(502, "prestate bridge failure")

    def log_message(self, format: str, *args: Any) -> None:
        return


def serve_http_bridge(socket_path: Path, *, host: str = "127.0.0.1", port: int = 8545) -> None:
    server = http.server.ThreadingHTTPServer((host, port), _HTTPBridge)
    server.socket_path = socket_path  # type: ignore[attr-defined]
    server.serve_forever()
