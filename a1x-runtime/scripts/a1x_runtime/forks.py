from __future__ import annotations

import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import IntegrityError, ValidationError
from .records import allocate_id, event, require_campaign, schema_for, utc_now
from .rpc import hex_int, rpc_call

_LOCAL_SUPERVISORS: dict[int, subprocess.Popen[bytes]] = {}


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _proc_start_ticks(pid: int) -> int | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().split()
        return int(fields[21])
    except (FileNotFoundError, IndexError, ValueError, PermissionError):
        return None


def _alive(pid: int, start_ticks: int) -> bool:
    return _proc_start_ticks(pid) == start_ticks


def _kill_and_reap(process: subprocess.Popen[bytes], sig: signal.Signals) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    _LOCAL_SUPERVISORS.pop(process.pid, None)


def _load_fork(root: Path, fork_id: str) -> tuple[Path, dict[str, Any]]:
    path = root / "forks" / f"{fork_id}.json"
    state = read_json(path)
    if state.get("kind") != "fork":
        raise IntegrityError(f"invalid fork record: {fork_id}")
    return path, state


def start_fork(
    root: Path,
    *,
    rpc_env: str | None,
    chain_id: int | None,
    block_number: int | None,
    port: int,
    startup_timeout: int,
    max_output_bytes: int,
    lane_id: str | None = None,
    round_id: str | None = None,
) -> dict[str, Any]:
    campaign = require_campaign(root)
    chain = campaign["chain"]
    rpc_env = rpc_env if rpc_env is not None else chain.get("rpc_env")
    chain_id = chain_id if chain_id is not None else chain.get("chain_id")
    block_number = block_number if block_number is not None else chain.get("block_number")
    if not rpc_env or not chain_id or block_number is None:
        raise ValidationError("fork start requires rpc env name, chain id, and pinned block")
    if chain_id <= 0 or block_number < 0:
        raise ValidationError("fork chain id must be positive and block cannot be negative")
    if port < 0 or port > 65535:
        raise ValidationError("fork port must be 0 or between 1 and 65535")
    if startup_timeout <= 0 or max_output_bytes <= 0:
        raise ValidationError("fork startup timeout and output limit must be positive")
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", rpc_env):
        raise ValidationError("RPC environment variable must be an uppercase identifier")
    if rpc_env not in os.environ or not os.environ[rpc_env]:
        raise ValidationError(f"RPC environment variable is unset: {rpc_env}")
    anvil = shutil.which("anvil")
    if not anvil:
        raise ValidationError("anvil executable not found")
    fork_id = allocate_id(root, "FORK")
    fork_dir = root / "forks" / fork_id
    fork_dir.mkdir()
    selected_port = port or _free_port()
    proxy_port = _free_port()
    while proxy_port == selected_port:
        proxy_port = _free_port()
    socket_path = fork_dir / "anvil.sock"
    config = {
        "rpc_env": rpc_env,
        "chain_id": chain_id,
        "block_number": block_number,
        "port": selected_port,
        "proxy_port": proxy_port,
        "socket_path": str(socket_path),
        "cache_dir": str(root / "prestate" / "cache"),
        "anvil_bin": anvil,
        "max_output_bytes": max_output_bytes,
    }
    config_path = fork_dir / "supervisor-config.json"
    scripts_root = Path(__file__).resolve().parents[1]
    supervisor_env = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(scripts_root),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
    }
    credential_read, credential_write = os.pipe()
    config["credential_fd"] = credential_read
    write_json_atomic(config_path, config)
    try:
        supervisor = subprocess.Popen(
            [sys.executable, "-m", "a1x_runtime.fork_supervisor", str(config_path)],
            cwd=fork_dir,
            env=supervisor_env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            pass_fds=(credential_read,),
        )
        os.close(credential_read)
        credential_read = -1
        os.write(credential_write, os.environ[rpc_env].encode())
    finally:
        if credential_read >= 0:
            os.close(credential_read)
        os.close(credential_write)
    _LOCAL_SUPERVISORS[supervisor.pid] = supervisor
    start_ticks = _proc_start_ticks(supervisor.pid)
    if start_ticks is None:
        raise IntegrityError("failed to fingerprint fork supervisor")
    endpoint = f"http://127.0.0.1:{selected_port}"
    deadline = time.monotonic() + startup_timeout
    last_error = "not ready"
    observed_chain = None
    observed_block = None
    observed_block_hash = None
    ready = False
    while time.monotonic() < deadline:
        if supervisor.poll() is not None:
            last_error = f"supervisor exited {supervisor.returncode}"
            break
        try:
            observed_chain = hex_int(rpc_call(endpoint, "eth_chainId"))
            observed_block = hex_int(rpc_call(endpoint, "eth_blockNumber"))
            observed_record = rpc_call(endpoint, "eth_getBlockByNumber", [hex(block_number), False])
            observed_block_hash = observed_record.get("hash") if isinstance(observed_record, dict) else None
            if socket_path.exists() and observed_block_hash:
                ready = True
                break
        except Exception as exc:  # bounded startup probe; full error retained locally
            last_error = str(exc)
            time.sleep(0.2)
    if not ready:
        _kill_and_reap(supervisor, signal.SIGKILL)
        raise ValidationError(f"Anvil fork did not become ready: {last_error}")
    if observed_chain != chain_id or observed_block != block_number:
        _kill_and_reap(supervisor, signal.SIGKILL)
        raise IntegrityError(
            f"fork identity mismatch: expected chain/block {chain_id}/{block_number}, got {observed_chain}/{observed_block}"
        )
    base_snapshot = rpc_call(endpoint, "evm_snapshot")
    record = {
        "schema": schema_for(root),
        "kind": "fork",
        "id": fork_id,
        "created_at": utc_now(),
        "status": "running",
        "rpc_env": rpc_env,
        "chain_id": chain_id,
        "block_number": block_number,
        "block_hash": observed_block_hash,
        "endpoint": endpoint,
        "port": selected_port,
        "upstream_proxy_port": proxy_port,
        "socket": str(socket_path),
        "upstream_secret_exposed": False,
        "rpc_policy": "credential-free-filtered-writable-local-fork",
        "scope": "lane" if lane_id else "manual",
        "lane_id": lane_id,
        "round_id": round_id,
        "supervisor_pid": supervisor.pid,
        "supervisor_start_ticks": start_ticks,
        "process_group": supervisor.pid,
        "snapshots": [{"snapshot_id": base_snapshot, "created_at": utc_now(), "role": "base"}],
        "logs": {"stdout": f"{fork_id}/stdout.log", "stderr": f"{fork_id}/stderr.log"},
    }
    write_json_atomic(root / "forks" / f"{fork_id}.json", record)
    event(root, "fork.started", fork_id=fork_id, chain_id=chain_id, block_number=block_number, port=selected_port, lane_id=lane_id, round_id=round_id)
    return record


def fork_status(root: Path, fork_id: str) -> dict[str, Any]:
    _, state = _load_fork(root, fork_id)
    alive = _alive(int(state["supervisor_pid"]), int(state["supervisor_start_ticks"]))
    rpc_ok = False
    observed_block = None
    if alive:
        try:
            observed_block = hex_int(rpc_call(state["endpoint"], "eth_blockNumber"))
            rpc_ok = True
        except Exception:
            pass
    accounting_path = root / "forks" / fork_id / "rpc-accounting.json"
    accounting = read_json(accounting_path) if accounting_path.is_file() else {"total": 0, "by_method": {}, "rejected": 0}
    return {
        "fork_id": fork_id, "recorded_status": state["status"], "process_alive": alive,
        "rpc_ready": rpc_ok, "uds_ready": Path(str(state.get("socket", ""))).exists(),
        "block_number": observed_block, "rpc_accounting": accounting,
    }


def snapshot_fork(root: Path, fork_id: str) -> dict[str, Any]:
    path, state = _load_fork(root, fork_id)
    if not _alive(int(state["supervisor_pid"]), int(state["supervisor_start_ticks"])):
        raise IntegrityError("fork supervisor is not alive")
    snapshot_id = rpc_call(state["endpoint"], "evm_snapshot")
    item = {"snapshot_id": snapshot_id, "created_at": utc_now()}
    state["snapshots"].append(item)
    write_json_atomic(path, state)
    event(root, "fork.snapshot", fork_id=fork_id, snapshot_id=snapshot_id)
    return item


def revert_fork(root: Path, fork_id: str, snapshot_id: str | None) -> dict[str, Any]:
    _, state = _load_fork(root, fork_id)
    if not snapshot_id:
        if not state["snapshots"]:
            raise ValidationError("fork has no recorded snapshots")
        snapshot_id = state["snapshots"][-1]["snapshot_id"]
    reverted = bool(rpc_call(state["endpoint"], "evm_revert", [snapshot_id]))
    event(root, "fork.reverted", fork_id=fork_id, snapshot_id=snapshot_id, reverted=reverted)
    return {"fork_id": fork_id, "snapshot_id": snapshot_id, "reverted": reverted}


def stop_fork(root: Path, fork_id: str) -> dict[str, Any]:
    path, state = _load_fork(root, fork_id)
    pid = int(state["supervisor_pid"])
    ticks = int(state["supervisor_start_ticks"])
    if _alive(pid, ticks):
        try:
            os.killpg(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and _alive(pid, ticks):
            time.sleep(0.1)
        if _alive(pid, ticks):
            os.killpg(pid, signal.SIGKILL)
    local_process = _LOCAL_SUPERVISORS.pop(pid, None)
    if local_process is not None:
        try:
            local_process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    state["status"] = "stopped"
    state["stopped_at"] = utc_now()
    socket_value = state.get("socket")
    if socket_value:
        Path(str(socket_value)).unlink(missing_ok=True)
    accounting_path = root / "forks" / fork_id / "rpc-accounting.json"
    state["rpc_accounting"] = read_json(accounting_path) if accounting_path.is_file() else {"total": 0, "by_method": {}, "rejected": 0}
    write_json_atomic(path, state)
    event(root, "fork.stopped", fork_id=fork_id)
    return {"fork_id": fork_id, "stopped": True}
