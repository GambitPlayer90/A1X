from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .atomic import read_json, write_json_atomic
from .process import RedactingWriter, _pump
from .prestate import _ProxyState
from .records import utc_now
from .rpc_broker import ForwardingState, make_http_server, make_uds_server


def main() -> int:
    if len(sys.argv) != 2:
        return 64
    config_path = Path(sys.argv[1]).resolve()
    config = read_json(config_path)
    rpc_env = config["rpc_env"]
    credential_fd = int(config["credential_fd"])
    try:
        with os.fdopen(credential_fd, "rb", closefd=True) as credential_pipe:
            rpc_url = credential_pipe.read(16 * 1024).decode()
    except (OSError, UnicodeError):
        rpc_url = ""
    if not rpc_url:
        write_json_atomic(config_path.parent / "supervisor-error.json", {"at": utc_now(), "error": "upstream RPC credential pipe was empty"})
        return 78
    upstream_state = _ProxyState(
        upstream_url=rpc_url,
        block_number=int(config["block_number"]),
        cache_dir=Path(config["cache_dir"]),
    )
    upstream_server = make_http_server("127.0.0.1", int(config["proxy_port"]), upstream_state)
    upstream_thread = threading.Thread(target=upstream_server.serve_forever, name="a1x-upstream-proxy", daemon=True)
    upstream_thread.start()
    local_proxy_url = f"http://127.0.0.1:{config['proxy_port']}"
    argv = [
        config["anvil_bin"],
        "--host", "127.0.0.1",
        "--port", str(config["port"]),
        "--chain-id", str(config["chain_id"]),
        "--fork-url", local_proxy_url,
        "--fork-block-number", str(config["block_number"]),
        "--silent",
    ]
    child_env = dict(os.environ)
    child_env.pop(rpc_env, None)
    stdout_path = config_path.parent / "stdout.log"
    stderr_path = config_path.parent / "stderr.log"
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        child = subprocess.Popen(argv, env=child_env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        relay_state = ForwardingState(
            f"http://127.0.0.1:{config['port']}",
            accounting_path=config_path.parent / "rpc-accounting.json",
        )
        relay_server = make_uds_server(Path(config["socket_path"]), relay_state)
        relay_thread = threading.Thread(target=relay_server.serve_forever, name="a1x-lane-uds", daemon=True)
        relay_thread.start()
        write_json_atomic(
            config_path.parent / "supervisor.json",
            {
                "started_at": utc_now(), "supervisor_pid": os.getpid(), "anvil_pid": child.pid,
                "anvil_port": config["port"], "upstream_proxy_port": config["proxy_port"],
                "socket": config["socket_path"], "upstream_secret_exposed": False,
            },
        )
        assert child.stdout is not None and child.stderr is not None
        secrets = [rpc_url.encode()]
        writers = [
            RedactingWriter(stdout_handle, secrets, int(config["max_output_bytes"])),
            RedactingWriter(stderr_handle, secrets, int(config["max_output_bytes"])),
        ]
        threads = [
            threading.Thread(target=_pump, args=(child.stdout, writers[0]), daemon=True),
            threading.Thread(target=_pump, args=(child.stderr, writers[1]), daemon=True),
        ]
        for thread in threads:
            thread.start()
        stopping = threading.Event()

        def terminate(_signal: int, _frame: object) -> None:
            if stopping.is_set():
                return
            stopping.set()
            try:
                child.terminate()
            except ProcessLookupError:
                pass

        signal.signal(signal.SIGTERM, terminate)
        signal.signal(signal.SIGINT, terminate)
        while child.poll() is None:
            time.sleep(0.1)
        return_code = int(child.returncode or 0)
        for thread in threads:
            thread.join(timeout=10)
        relay_server.shutdown()
        relay_server.server_close()
        Path(config["socket_path"]).unlink(missing_ok=True)
        upstream_server.shutdown()
        upstream_server.server_close()
        write_json_atomic(config_path.parent / "supervisor-exit.json", {"finished_at": utc_now(), "exit_code": return_code})
        return return_code


if __name__ == "__main__":
    raise SystemExit(main())
