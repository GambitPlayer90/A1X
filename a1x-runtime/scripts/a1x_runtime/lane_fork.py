from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any

from .rpc_broker import MAX_BODY_BYTES, uds_call


class _Bridge(http.server.BaseHTTPRequestHandler):
    server_version = "A1XLaneForkBridge/4.2"

    def do_POST(self) -> None:  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 0 or length > MAX_BODY_BYTES:
                raise ValueError("invalid body length")
            payload = self.rfile.read(length)
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(30)
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
            self.send_error(502, "lane fork bridge failure")

    def log_message(self, format: str, *args: Any) -> None:
        return


def _socket(value: str | None) -> Path:
    path = Path(value or os.environ.get("A1X_FORK_SOCKET", "")).expanduser()
    # Older/interrupted lanes may still carry the absolute workspace path in
    # their environment. Linux AF_UNIX names are short; prefer the canonical
    # workspace-local link when it resolves to the same broker socket.
    local = Path(".a1x-fork.sock")
    if len(os.fsencode(str(path))) >= 100 and local.exists():
        try:
            if local.samefile(path):
                path = local
        except OSError:
            pass
    if not str(path) or not path.exists():
        raise SystemExit("A1X lane fork socket is unavailable")
    return path


def _exec(args: argparse.Namespace) -> int:
    path = _socket(args.socket)
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("a1x-lane-fork exec requires a command")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Bridge)
    server.socket_path = path  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, name="a1x-lane-bridge", daemon=True)
    thread.start()
    endpoint = f"http://127.0.0.1:{server.server_port}"
    child_env = dict(os.environ)
    child_env["A1X_FORK_URL"] = endpoint
    command = [endpoint if item == "@fork" else item for item in command]
    try:
        return subprocess.run(command, env=child_env, check=False).returncode
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _rpc(args: argparse.Namespace) -> int:
    params = json.loads(args.params)
    if not isinstance(params, list):
        raise SystemExit("RPC params must be a JSON array")
    value = uds_call(_socket(args.socket), args.method, params)
    print(json.dumps(value, sort_keys=True, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="a1x-lane-fork", description="Credential-free bridge to this lane's writable local Anvil fork")
    sub = parser.add_subparsers(dest="command_name", required=True)
    execute = sub.add_parser("exec")
    execute.add_argument("--socket")
    execute.add_argument("command", nargs=argparse.REMAINDER)
    execute.set_defaults(handler=_exec)
    rpc = sub.add_parser("rpc")
    rpc.add_argument("--socket")
    rpc.add_argument("method")
    rpc.add_argument("params", nargs="?", default="[]")
    rpc.set_defaults(handler=_rpc)
    args = parser.parse_args(argv)
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
