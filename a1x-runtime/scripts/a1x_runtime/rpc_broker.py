from __future__ import annotations

import http.server
import json
import socket
import socketserver
import threading
import urllib.request
from pathlib import Path
from typing import Any, Protocol

from .atomic import canonical_bytes, write_json_atomic
from .errors import ValidationError

MAX_BODY_BYTES = 16 * 1024 * 1024
MAX_BATCH = 100

# A lane may mutate only its disposable local Anvil. Reset and node metadata are
# deliberately excluded: reset accepts an arbitrary fork URL and nodeInfo has
# historically disclosed upstream configuration.
LOCAL_METHODS = {
    "web3_clientVersion", "net_version", "net_listening", "net_peerCount",
    "eth_accounts", "eth_blockNumber", "eth_chainId", "eth_call", "eth_coinbase",
    "eth_estimateGas", "eth_feeHistory", "eth_gasPrice", "eth_getBalance",
    "eth_getBlockByHash", "eth_getBlockByNumber", "eth_getBlockReceipts",
    "eth_getCode", "eth_getFilterChanges", "eth_getFilterLogs", "eth_getLogs",
    "eth_getProof", "eth_getStorageAt", "eth_getTransactionByBlockHashAndIndex",
    "eth_getTransactionByBlockNumberAndIndex", "eth_getTransactionByHash",
    "eth_getTransactionCount", "eth_getTransactionReceipt", "eth_maxPriorityFeePerGas",
    "eth_newBlockFilter", "eth_newFilter", "eth_newPendingTransactionFilter",
    "eth_sendRawTransaction", "eth_sendTransaction", "eth_sign", "eth_signTransaction",
    "eth_subscribe", "eth_syncing", "eth_uninstallFilter", "eth_unsubscribe",
    "debug_traceCall", "debug_traceTransaction", "trace_call", "trace_replayTransaction",
    "trace_transaction", "evm_snapshot", "evm_revert", "evm_increaseTime",
    "evm_setNextBlockTimestamp", "evm_mine", "anvil_impersonateAccount",
    "anvil_stopImpersonatingAccount", "anvil_setBalance", "anvil_setCode",
    "anvil_setNonce", "anvil_setStorageAt", "anvil_setCoinbase", "anvil_mine",
    "anvil_setAutomine", "anvil_setIntervalMining", "anvil_setBlockTimestampInterval",
    "anvil_removeBlockTimestampInterval", "anvil_setNextBlockBaseFeePerGas",
    "anvil_setMinGasPrice", "anvil_setLoggingEnabled", "anvil_dropTransaction",
    "anvil_removePoolTransactions", "anvil_setChainId",
}
BLOCKED_LOCAL_METHODS = {"anvil_reset", "hardhat_reset", "anvil_nodeInfo", "anvil_metadata", "anvil_setRpcUrl"}


class Dispatcher(Protocol):
    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]: ...


def _error(payload: dict[str, Any], code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": payload.get("id"), "error": {"code": code, "message": message}}


def http_json(url: str, payload: dict[str, Any], *, timeout: int = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, data=canonical_bytes(payload), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read(MAX_BODY_BYTES + 1)
    if len(body) > MAX_BODY_BYTES:
        raise ValidationError("JSON-RPC response exceeds the broker limit")
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValidationError("JSON-RPC response is not an object")
    return value


class ForwardingState:
    def __init__(self, endpoint: str, accounting_path: Path | None = None) -> None:
        self.endpoint = endpoint
        self.accounting_path = accounting_path
        self.lock = threading.Lock()
        self.counts: dict[str, int] = {}
        self.rejected = 0

    def _record(self, method: str, rejected: bool = False) -> None:
        with self.lock:
            self.counts[method] = self.counts.get(method, 0) + 1
            self.rejected += int(rejected)
            if self.accounting_path is not None:
                write_json_atomic(self.accounting_path, {
                    "total": sum(self.counts.values()), "by_method": dict(sorted(self.counts.items())),
                    "rejected": self.rejected,
                })

    def dispatch(self, payload: dict[str, Any]) -> dict[str, Any]:
        method = payload.get("method")
        if not isinstance(method, str) or method not in LOCAL_METHODS or method in BLOCKED_LOCAL_METHODS:
            self._record(str(method), rejected=True)
            return _error(payload, -32601, "method is not available through the A1X lane fork")
        self._record(method)
        try:
            return http_json(self.endpoint, payload)
        except Exception as exc:
            return _error(payload, -32603, f"local fork forwarding failed: {type(exc).__name__}")


def dispatch_body(state: Dispatcher, body: bytes) -> bytes:
    if len(body) > MAX_BODY_BYTES:
        raise ValidationError("JSON-RPC request exceeds the broker limit")
    payload = json.loads(body)
    if isinstance(payload, list):
        if not payload or len(payload) > MAX_BATCH or not all(isinstance(item, dict) for item in payload):
            raise ValidationError("invalid or oversized JSON-RPC batch")
        result = [state.dispatch(item) for item in payload]
    elif isinstance(payload, dict):
        result = state.dispatch(payload)
    else:
        raise ValidationError("JSON-RPC payload must be an object or batch")
    return canonical_bytes(result)


class HTTPDispatcher(http.server.BaseHTTPRequestHandler):
    server_version = "A1XRPCBroker/4.2"

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValidationError("invalid JSON-RPC body length")
            body = dispatch_body(self.server.state, self.rfile.read(length))  # type: ignore[attr-defined]
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            self.send_error(400, "invalid broker request")

    def log_message(self, format: str, *args: Any) -> None:
        return


class UDSDispatcher(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            line = self.rfile.readline(MAX_BODY_BYTES + 2)
            body = dispatch_body(self.server.state, line.rstrip(b"\n"))  # type: ignore[attr-defined]
        except Exception as exc:
            body = canonical_bytes(_error({}, -32603, f"broker error: {type(exc).__name__}"))
        self.wfile.write(body)


class ThreadingUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def make_http_server(host: str, port: int, state: Dispatcher) -> http.server.ThreadingHTTPServer:
    server = http.server.ThreadingHTTPServer((host, port), HTTPDispatcher)
    server.state = state  # type: ignore[attr-defined]
    return server


def make_uds_server(path: Path, state: Dispatcher) -> ThreadingUnixServer:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    server = ThreadingUnixServer(str(path), UDSDispatcher)
    server.state = state  # type: ignore[attr-defined]
    path.chmod(0o660)
    return server


def uds_call(path: Path, method: str, params: list[Any] | None = None, *, identifier: int = 1) -> Any:
    request = canonical_bytes({"jsonrpc": "2.0", "id": identifier, "method": method, "params": params or []}) + b"\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(30)
        client.connect(str(path))
        client.sendall(request)
        chunks = []
        while True:
            chunk = client.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
    response = json.loads(b"".join(chunks))
    if "error" in response:
        raise ValidationError(str(response["error"].get("message", "JSON-RPC error")))
    return response.get("result")
