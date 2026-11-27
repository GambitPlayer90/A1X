from __future__ import annotations

import http.server
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from a1x_runtime.campaign import add_hypothesis, add_obligation, init_campaign
from a1x_runtime.continuity import (
    create_continuation_contract,
    record_continuation_attempt,
    verify_continuation_contract,
)
from a1x_runtime.errors import ValidationError
from a1x_runtime.explorer import retrieve_verified_contract
from a1x_runtime.forks import start_fork, stop_fork
from a1x_runtime.rpc import rpc_call
from a1x_runtime.rpc_broker import uds_call
from a1x_runtime.replay import prepare_replay, verify_replay
from a1x_runtime.runs import execute_run, observe_run, plan_run
from a1x_runtime.scale import create_round, run_round


def _port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class BrokerIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        if not shutil.which("anvil") or not shutil.which("cast"):
            self.skipTest("Foundry tools unavailable")
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.source = base / "source"
        self.source.mkdir()
        (self.source / "Target.sol").write_text("contract Target {}\n", encoding="utf-8")
        self.root = base / "campaign"
        self.upstream_port = _port()
        self.upstream = subprocess.Popen(
            [shutil.which("anvil") or "anvil", "--host", "127.0.0.1", "--port", str(self.upstream_port), "--chain-id", "1", "--silent"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        endpoint = f"http://127.0.0.1:{self.upstream_port}"
        for _ in range(100):
            try:
                rpc_call(endpoint, "eth_chainId")
                break
            except Exception:
                time.sleep(0.05)
        self.secret = "A1X_TEST_SECRET_93f278"
        self.rpc_url = endpoint + "/?apikey=" + self.secret
        os.environ["A1X_TEST_RPC_URL"] = self.rpc_url
        init_campaign(
            self.root, label="broker-test", source=self.source, target="Target", chain_id=1,
            block_number=0, rpc_env="A1X_TEST_RPC_URL", authorization="local synthetic test",
            budgets={"max_runs": 20, "max_scale_lanes": 20, "max_parallel": 2, "default_run_timeout_seconds": 60, "default_output_bytes": 100000},
        )

    def tearDown(self) -> None:
        os.environ.pop("A1X_TEST_RPC_URL", None)
        if hasattr(self, "upstream"):
            self.upstream.terminate()
            try:
                self.upstream.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.upstream.kill()
        if hasattr(self, "temporary"):
            self.temporary.cleanup()

    def test_credential_free_writable_lane_fork(self) -> None:
        record = start_fork(
            self.root, rpc_env=None, chain_id=None, block_number=None, port=0,
            startup_timeout=30, max_output_bytes=1_000_000, lane_id="LANE-0001", round_id="ROUND-0001",
        )
        try:
            socket_path = Path(record["socket"])
            self.assertTrue(socket_path.exists())
            self.assertEqual(uds_call(socket_path, "eth_chainId"), "0x1")
            account = rpc_call(record["endpoint"], "eth_accounts")[0]
            uds_call(socket_path, "anvil_setBalance", [account, "0x1234"])
            self.assertEqual(uds_call(socket_path, "eth_getBalance", [account, "latest"]), "0x1234")
            snapshot = uds_call(socket_path, "evm_snapshot")
            self.assertTrue(snapshot)
            with self.assertRaises(ValidationError):
                uds_call(socket_path, "anvil_reset", [])
            with self.assertRaises(ValidationError):
                uds_call(socket_path, "anvil_nodeInfo", [])
            with self.assertRaises(ValidationError):
                uds_call(socket_path, "anvil_setRpcUrl", ["http://attacker.invalid"])

            supervisor = json.loads((self.root / "forks" / record["id"] / "supervisor.json").read_text())
            cmdline = Path(f"/proc/{supervisor['anvil_pid']}/cmdline").read_bytes()
            self.assertNotIn(self.secret.encode(), cmdline)
            self.assertNotIn(self.rpc_url.encode(), cmdline)
            supervisor_environ = Path(f"/proc/{record['supervisor_pid']}/environ").read_bytes()
            self.assertNotIn(self.secret.encode(), supervisor_environ)
            self.assertNotIn(self.rpc_url.encode(), supervisor_environ)
            persisted = b"".join(path.read_bytes() for path in (self.root / "forks" / record["id"]).rglob("*") if path.is_file())
            self.assertNotIn(self.secret.encode(), persisted)

            wrapper = Path(__file__).resolve().parents[1] / "scripts" / "a1x-lane-fork"
            completed = subprocess.run(
                [str(wrapper), "exec", "--socket", str(socket_path), "--", "cast", "chain-id", "--rpc-url", "@fork"],
                text=True, capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(completed.stdout.strip(), "1")

            mcp = Path(__file__).resolve().parents[1] / "scripts" / "a1x-lane-fork-mcp"
            requests = "\n".join([
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "identity", "arguments": {}}}),
                json.dumps({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "rpc", "arguments": {"method": "anvil_nodeInfo", "params": []}}}),
            ]) + "\n"
            mcp_result = subprocess.run(
                [str(mcp), "--socket", str(socket_path)], input=requests,
                text=True, capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(mcp_result.returncode, 0, mcp_result.stderr)
            responses = [json.loads(line) for line in mcp_result.stdout.splitlines()]
            identity = responses[1]["result"]["structuredContent"]["result"]
            self.assertEqual(identity["chain_id"], "0x1")
            self.assertTrue(identity["local_disposable_fork"])
            self.assertFalse(identity["upstream_credential_exposed"])
            self.assertTrue(responses[2]["result"]["isError"])
        finally:
            result = stop_fork(self.root, record["id"])
            self.assertTrue(result["stopped"])
            self.assertFalse(Path(record["socket"]).exists())

    def test_real_anvil_checkpoint_and_waypoint_continuation(self) -> None:
        script = self.source / "rpc_trace.py"
        script.write_text(
            """import json, os, time, urllib.request
url = os.environ['A1X_TEST_RPC_URL']
counter = 0
def rpc(method, params):
    global counter
    counter += 1
    body = json.dumps({'jsonrpc':'2.0','id':counter,'method':method,'params':params}).encode()
    request = urllib.request.Request(url, data=body, headers={'content-type':'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        value = json.loads(response.read())
    if 'error' in value:
        raise RuntimeError(value['error'])
    return value['result']
snapshot = rpc('evm_snapshot', [])
sender = rpc('eth_accounts', [])[0]
init = '0x6006600c60003960066000f3600160005500'
created = rpc('eth_sendTransaction', [{'from':sender,'data':init,'gas':'0x100000'}])
receipt = rpc('eth_getTransactionReceipt', [created])
for _ in range(100):
    if receipt:
        break
    time.sleep(0.01)
    receipt = rpc('eth_getTransactionReceipt', [created])
address = receipt['contractAddress']
called = rpc('eth_sendTransaction', [{'from':sender,'to':address,'gas':'0x100000'}])
called_receipt = rpc('eth_getTransactionReceipt', [called])
for _ in range(100):
    if called_receipt:
        break
    time.sleep(0.01)
    called_receipt = rpc('eth_getTransactionReceipt', [called])
trace = rpc('debug_traceTransaction', [called, {'disableMemory':True,'disableStack':False,'disableStorage':False}])
print(json.dumps({'trace_ok':True,'transaction':called,'address':address,'trace':trace}, sort_keys=True))
if not rpc('evm_revert', [snapshot]):
    raise RuntimeError('snapshot revert failed')
""",
            encoding="utf-8",
        )
        obligation = add_obligation(
            self.root,
            title="slot update",
            statement="the executable prefix stores one",
            boundary="top-level transaction",
            units="uint256",
            oracle="trace contains SSTORE",
        )
        hypothesis = add_hypothesis(
            self.root,
            obligation_id=obligation["id"],
            mechanism="call writes the declared slot",
            sequence="deploy then call",
            support_prediction="trace contains SSTORE",
            refute_prediction="trace omits SSTORE",
            next_action="replay",
        )
        planned = plan_run(
            self.root,
            hypothesis_id=hypothesis["id"],
            run_class="candidate",
            cwd=self.source,
            argv=[sys.executable, "rpc_trace.py"],
            timeout_seconds=30,
            max_output_bytes=2_000_000,
            inputs=[script],
            property_statement="the executable prefix reaches SSTORE",
            support_prediction="trace_ok is true",
            refute_prediction="trace command fails",
            success_regex='"trace_ok": true',
            pass_env=["A1X_TEST_RPC_URL"],
            inherit_env=[],
            fork_id=None,
        )
        run_id = planned["run_id"]
        receipt = execute_run(self.root, run_id)
        self.assertTrue(
            receipt["mechanical_success"],
            (self.root / "runs" / run_id / "stderr.log").read_text(encoding="utf-8", errors="replace"),
        )
        observe_run(
            self.root,
            run_id,
            outcome="supports",
            property_violated=True,
            observation="real Anvil trace reached SSTORE",
            impact="fixture continuity only",
            metrics=[],
            limitations="local deterministic fixture",
        )
        replay_workspace = Path(self.temporary.name) / "continuation-replay"
        prepare_replay(self.root, run_id=run_id, destination=replay_workspace)
        replay = verify_replay(self.root, run_id=run_id, workspace=replay_workspace)
        self.assertTrue(replay["passed"], replay)
        run_ref = {"type": "run-receipt", "run_id": run_id, "outcome": "supports"}
        base = {
            "parent_run": run_id,
            "parent_handoff": None,
            "lineage_id": "LINEAGE-anvil-continuity",
            "closure_mode": "witness",
            "execution_topology": "atomic",
            "actors": [{
                "id": "attacker",
                "role": "unprivileged caller",
                "address": None,
                "capabilities": ["send transaction"],
                "authority_basis": "Anvil unlocked fixture account",
            }],
            "transactions": [{
                "index": 0,
                "actor": "attacker",
                "action": "deploy and call trace fixture",
                "boundary": "transaction",
                "expected_effects": ["SSTORE executes"],
                "obligations_created": [],
            }],
            "assertions": [{
                "id": "prefix-sstore",
                "predicate": "trace contains SSTORE",
                "expected": "true",
                "scope": "parent top-level replay",
                "required": True,
                "evidence_refs": [run_ref],
            }],
            "preserve_assertions": ["prefix-sstore"],
            "selected_prerequisite": {
                "id": "PREREQ-next",
                "predicate": "extend after SSTORE",
                "success_condition": "new assertion executes",
                "artificial": False,
                "dependencies": [],
            },
            "reachability": {"predicate": "prefix is public", "writer_paths": []},
        }
        checkpoint_payload = dict(base)
        checkpoint_payload["checkpoint"] = {
            "kind": "transaction-checkpoint",
            "transaction_index": 0,
            "waypoint": None,
        }
        checkpoint = create_continuation_contract(self.root, checkpoint_payload)
        self.assertTrue(verify_continuation_contract(self.root, checkpoint["id"])["valid"])
        trace_ref = {"type": "trace-artifact", "run_id": run_id, "path": "stdout.log"}
        waypoint_payload = json.loads(json.dumps(base))
        waypoint_payload["execution_topology"] = "nested-atomic"
        waypoint_payload["checkpoint"] = {
            "kind": "transaction-waypoint",
            "transaction_index": 0,
            "waypoint": {
                "frame_path": [],
                "program_counter": 4,
                "occurrence": 1,
                "description": "SSTORE inside the top-level call",
                "evidence_refs": [trace_ref],
            },
        }
        waypoint = create_continuation_contract(self.root, waypoint_payload)
        self.assertTrue(verify_continuation_contract(self.root, waypoint["id"])["valid"])
        attempt = record_continuation_attempt(
            self.root,
            checkpoint["id"],
            {
                "replay_id": replay["id"],
                "result": "advanced",
                "assertions": [{
                    "id": "prefix-sstore",
                    "passed": True,
                    "observed": "SSTORE remained present",
                    "evidence_refs": [{"type": "replay", "replay_id": replay["id"]}],
                }],
                "prerequisite_observation": "parent prefix reproduced",
                "next_action": "extend the next edge",
            },
        )
        self.assertEqual(attempt["result"], "advanced")

    def test_scale_lane_receives_tools_wake_mcp_and_no_upstream_secret(self) -> None:
        capabilities = self.root / "capabilities" / "capabilities.json"
        capabilities.write_text(json.dumps({
            "backends": {"wake": {"ready": True}, "foundry": {"ready": True}, "echidna": {"ready": True}},
            "machine": {},
        }))
        prompt = Path(self.temporary.name) / "prompt.md"
        prompt.write_text("Validate the supplied isolated execution environment.\n")
        planned = create_round(self.root, prompt_file=prompt, axes=["environment-smoke"], hypothesis_id=None, per_lane_timeout=60)
        fake = Path(self.temporary.name) / "fake-codex"
        fake.write_text("""#!/usr/bin/env python3
import json, os, shutil, subprocess, sys
from pathlib import Path
args = sys.argv[1:]
assert '--trust' in args
assert '--approve-for-me' in args
assert '--sandbox' not in args
assert args[args.index('--cyber-access-program') + 1] == 'standard'
out = Path(args[args.index('-o') + 1])
workspace = Path(args[args.index('-C') + 1])
assert 'A1X_TEST_RPC_URL' not in os.environ
assert 'ETH_RPC_URL' not in os.environ
assert os.environ['A1X_FORK_SOCKET'] == '.a1x-fork.sock'
assert Path(os.environ['A1X_FORK_SOCKET']).exists()
transport = json.loads((workspace / '.a1x' / 'fork-transport.json').read_text())
assert transport['direct_uds']['ready'] is True
assert transport['http_bridge']['ready'] is True
assert transport['mcp_stdio']['ready'] is True
for tool in ('wake', 'forge', 'cast', 'echidna', 'medusa', 'halmos', 'a1x-lane-fork'):
    assert shutil.which(tool), tool
config = (Path(os.environ['CODEX_HOME']) / 'config.toml').read_text()
assert '[mcp_servers.wake-lane]' in config
assert '[mcp_servers.a1x-fork]' in config
assert config.count('default_tools_approval_mode = "approve"') == 2
assert '[mcp_servers.unrelated]' not in config
assert 'LANE_CONFIG_SECRET' not in config
call = subprocess.run(['a1x-lane-fork', 'rpc', 'eth_chainId', '[]'], capture_output=True, text=True, check=True)
assert json.loads(call.stdout) == '0x1'
artifact = out.parent / 'environment-check.txt'
artifact.write_text('credential-free lane fork and approved toolchain verified\\n')
identity = {'writer':'environment','guard':'broker','consumer':'lane','state':'fork','property':'credentials remain absent'}
handoff = {
 'lane_id':'LANE-0001','status':'blocked','mechanism':'environment smoke only','mechanism_family':'infrastructure','consumer':'lane toolchain',
 'tested_obligation':'lane receives local execution without provider secrets','discriminator':'tool and UDS checks',
 'causal_identity':identity,'causal_anchors':{'writer':'environment-check.txt','guard':'environment-check.txt','consumer':'environment-check.txt','state':'environment-check.txt','property':'environment-check.txt','attacker_model':'environment-check.txt','state_shape':'environment-check.txt','transition_sequence':['environment-check.txt'],'deployment':'environment-check.txt'},
 'attacker_fingerprint':'synthetic lane','state_fingerprint':'local fork','impact_stage':'bounded','terminal_impact':False,
 'execution':{'ran':False,'property':'infrastructure only','property_violated':None,'outcome':'environment verified','command_artifact':'','control_artifact':''},
 'blocker':{'prerequisite':'blind target authorization','resolution_condition':'operator starts blind test','evidence_artifact':'environment-check.txt'},
 'evidence':[{'claim':'lane isolation is usable','observation':'tools, Wake MCP config, and fork UDS verified','artifact':'environment-check.txt'}],
 'artifacts':['environment-check.txt'],'refutations':[],'unresolved':['blind target not started'],'next_action':'await operator blind-test instruction',
 'prerequisites':[{'id':'','description':'blind target not started','kind':'environment','status':'open','resolution_condition':'operator starts blind test','evidence_artifact':''}],
 'witness':{'bug_class':'other','source_faithful':False,'setup_taint':'unknown','phases':[{'id':phase,'status':'open','property':'','evidence_artifact':''} for phase in ('prepare','trigger','persist','impact')],'signals':[]},
 'continuation_replay':{'required':False,'parent_manifests':[],'parent_replayed':False,'assertions_preserved':False,'replay_artifact':''},
 'dimensions':{'evidence_level':'E1','reachability':'high','security_consequence':'unknown','state_novelty':'low','next_test_cost':'low'}
}
out.write_text(json.dumps(handoff))
""")
        fake.chmod(0o755)
        operator_codex_home = Path(self.temporary.name) / "operator-codex"
        operator_codex_home.mkdir()
        (operator_codex_home / "auth.json").write_text("{}\n")
        (operator_codex_home / "config.toml").write_text(
            'model = "gpt-6.2-sol"\n[mcp_servers.unrelated]\ncommand = "unsafe"\nenv = { TOKEN = "LANE_CONFIG_SECRET" }\n'
        )
        previous_codex_home = os.environ.get("CODEX_HOME")
        os.environ["CODEX_HOME"] = str(operator_codex_home)
        try:
            result = run_round(
                self.root, round_id=planned["id"], parallel=1, codex_bin=str(fake), model=None,
                reasoning=None, sandbox="workspace-write", allow_env_auth=False, lane_forks="require",
            )
        finally:
            if previous_codex_home is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = previous_codex_home
        self.assertEqual(result["status"], "completed")
        receipt = json.loads((self.root / "scale" / planned["id"] / "lanes" / "LANE-0001" / "lane-receipt.json").read_text())
        self.assertEqual(receipt["status"], "completed")
        fork_id = result["lanes"][0]["fork_id"]
        fork_record = json.loads((self.root / "forks" / f"{fork_id}.json").read_text())
        self.assertEqual(fork_record["status"], "stopped")
        self.assertNotIn(self.secret, json.dumps(receipt))

        # A repair run must be able to replace the generated, read-only
        # capability snapshot left by an interrupted lane.
        round_dir = self.root / "scale" / planned["id"]
        plan_path = round_dir / "plan.json"
        plan_record = json.loads(plan_path.read_text())
        plan_record["status"] = "partial"
        plan_path.write_text(json.dumps(plan_record))
        lane_dir = round_dir / "lanes" / "LANE-0001"
        (lane_dir / "lane-receipt.json").unlink()
        stale = lane_dir / "workspace" / ".a1x" / "capabilities.json"
        stale.chmod(0o444)
        capabilities.write_text(json.dumps({"backends": {"wake": {"ready": True}}, "revision": 2}))
        retry = run_round(
            self.root, round_id=planned["id"], parallel=1, codex_bin=str(fake), model=None,
            reasoning=None, sandbox="workspace-write", allow_env_auth=False, lane_forks="require",
        )
        self.assertEqual(retry["status"], "completed")
        self.assertEqual(json.loads(stale.read_text())["revision"], 2)

    def test_scale_sigterm_cancels_lane_and_stops_fork(self) -> None:
        """A killed controller must not leave a lane process or fork alive."""
        prompt = Path(self.temporary.name) / "cancel-prompt.md"
        prompt.write_text("Wait until the controller cancels this synthetic lane.\n")
        planned = create_round(
            self.root, prompt_file=prompt, axes=["signal-cleanup"],
            hypothesis_id=None, per_lane_timeout=60,
        )
        fake = Path(self.temporary.name) / "slow-codex"
        fake.write_text(
            "#!/usr/bin/env python3\n"
            "import time\n"
            "time.sleep(30)\n"
        )
        fake.chmod(0o755)
        script = """
import sys
from pathlib import Path
from a1x_runtime.scale import run_round
try:
    run_round(Path(sys.argv[1]), round_id=sys.argv[2], parallel=1,
              codex_bin=sys.argv[3], model=None, reasoning=None,
              sandbox='danger-full-access', allow_env_auth=False,
              lane_forks='require')
except KeyboardInterrupt:
    raise SystemExit(130)
"""
        env = dict(os.environ)
        runtime_scripts = Path(__file__).resolve().parents[1] / "scripts"
        env["PYTHONPATH"] = str(runtime_scripts) + os.pathsep + env.get("PYTHONPATH", "")
        controller = subprocess.Popen(
            [sys.executable, "-c", script, str(self.root), planned["id"], str(fake)],
            env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        fork_record_path: Path | None = None
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            candidates = sorted((self.root / "forks").glob("FORK-*.json"))
            running = [path for path in candidates if json.loads(path.read_text()).get("status") == "running"]
            if running:
                fork_record_path = running[-1]
                break
            if controller.poll() is not None:
                break
            time.sleep(0.05)
        self.assertIsNotNone(fork_record_path, "controller never started its lane fork")
        controller.send_signal(signal.SIGTERM)
        stdout, stderr = controller.communicate(timeout=20)
        self.assertEqual(controller.returncode, 130, (stdout + stderr).decode(errors="replace"))
        assert fork_record_path is not None
        stopped = json.loads(fork_record_path.read_text())
        self.assertEqual(stopped["status"], "stopped")
        self.assertFalse(Path(stopped["socket"]).exists())
        plan = json.loads((self.root / "scale" / planned["id"] / "plan.json").read_text())
        self.assertEqual(plan["status"], "partial")
        self.assertNotIn("controller_pid", plan)


class _ExplorerHandler(http.server.BaseHTTPRequestHandler):
    seen_key = ""
    requests = 0

    def do_GET(self) -> None:  # noqa: N802
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        type(self).seen_key = query.get("apikey", [""])[0]
        type(self).requests += 1
        body = json.dumps({
            "status": "1", "message": "OK", "result": [{
                "SourceCode": "contract Verified {}", "ABI": "[]", "ContractName": "Verified",
                "CompilerVersion": "v0.8.30", "Proxy": "1", "Implementation": "0x" + "2" * 40,
            }],
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class ExplorerIntegrationTest(unittest.TestCase):
    def test_api_key_is_used_but_never_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            (source / "Target.sol").write_text("contract Target {}\n")
            root = base / "campaign"
            init_campaign(
                root, label="explorer-test", source=source, target="Target", chain_id=1,
                block_number=20_000_000, rpc_env="UNSET_TEST_RPC", authorization="local synthetic test",
                budgets={"max_runs": 20, "max_scale_lanes": 20, "max_parallel": 2, "default_run_timeout_seconds": 60, "default_output_bytes": 100000},
            )
            server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ExplorerHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            secret = "EXPLORER_SECRET_4f83"
            os.environ["A1X_TEST_EXPLORER_KEY"] = secret
            try:
                record = retrieve_verified_contract(
                    root, address="0x" + "1" * 40, api_env="A1X_TEST_EXPLORER_KEY",
                    endpoint=f"http://127.0.0.1:{server.server_port}/v2/api",
                    campaign_epoch=1, idempotency_key="explorer-test-1",
                )
                same = retrieve_verified_contract(
                    root, address="0x" + "1" * 40, api_env="A1X_TEST_EXPLORER_KEY",
                    endpoint=f"http://127.0.0.1:{server.server_port}/v2/api",
                    campaign_epoch=1, idempotency_key="explorer-test-1",
                )
                self.assertEqual(record["id"], same["id"])
                self.assertEqual(_ExplorerHandler.seen_key, secret)
                self.assertFalse(record["pinned_implementation_verified"])
                self.assertTrue((root / "recon" / record["recon_version"] / "manifest.json").is_file())
                _ExplorerHandler.requests = 0
                with ThreadPoolExecutor(max_workers=2) as pool:
                    concurrent = list(pool.map(
                        lambda _: retrieve_verified_contract(
                            root, address="0x" + "3" * 40, api_env="A1X_TEST_EXPLORER_KEY",
                            endpoint=f"http://127.0.0.1:{server.server_port}/v2/api",
                            campaign_epoch=1, idempotency_key="explorer-concurrent",
                        ),
                        range(2),
                    ))
                self.assertEqual(concurrent[0]["id"], concurrent[1]["id"])
                self.assertEqual(_ExplorerHandler.requests, 1)
                persisted = b"".join(path.read_bytes() for path in root.rglob("*") if path.is_file())
                self.assertNotIn(secret.encode(), persisted)
            finally:
                os.environ.pop("A1X_TEST_EXPLORER_KEY", None)
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
