from __future__ import annotations

import json
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from a1x_runtime import records
from a1x_runtime.benchmark import attach_benchmark_trial, compare_benchmark, create_benchmark_suite
from a1x_runtime.artifacts import ingest_artifact, verify_artifact
from a1x_runtime.atomic import read_json, write_json_atomic
from a1x_runtime.blind_review import (
    execute_blind_review,
    prepare_blind_review,
    qualifies,
)
from a1x_runtime.campaign import init_campaign, migrate_campaign
from a1x_runtime.evidence import normalize_evidence_refs
from a1x_runtime.evidence_bundles import create_bundle, verify_bundle
from a1x_runtime.errors import StateTransitionError, ValidationError
from a1x_runtime.evaluation import adjudicate_trial, evaluation_summary, record_trial
from a1x_runtime.mcp_server import dispatch
from a1x_runtime.modern_evm import context_template, validate_execution_context
from a1x_runtime.operations import propose_operation, transition_operation
from a1x_runtime.prestate import _ProxyState, _pin_request
from a1x_runtime.recon import create_recon_pack
from a1x_runtime.records import (
    LEGACY_RUNTIME_SCHEMA,
    require_campaign,
    verify_event_chain,
)
from a1x_runtime.scheduling import record_lineage_attempts, scheduling_state, select_fair_lineages
from a1x_runtime.rsa import (
    assess_semantic_delta,
    build_compatibility_graph,
    create_evidence_round,
)
from a1x_runtime.scale import (
    _has_mcp_server,
    _composition_priority,
    _fitness,
    _population_key,
    _rsa_eligible,
    _semantic_delta_against_population,
    _semantic_progress_key,
    _update_lineage_stagnation,
    create_recombination_round,
    evolve_population,
)
from a1x_runtime.witness import (
    canonicalize_prerequisites,
    needs_reachability_closure,
    needs_witness_closure,
    witness_progress,
)


class A1XV4Test(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.source = base / "source"
        self.source.mkdir()
        (self.source / "Target.sol").write_text("contract Target {}\n", encoding="utf-8")
        self.root = base / "campaign"
        init_campaign(
            self.root, label="test", source=self.source, target="Target", chain_id=1,
            block_number=20_000_000, rpc_env="MAINNET_RPC_URL", authorization="local test",
            budgets={"max_runs": 20, "max_scale_lanes": 20, "max_parallel": 2, "default_run_timeout_seconds": 60, "default_output_bytes": 100000},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _artifact(self) -> str:
        path = Path(self.temporary.name) / "trace.json"
        path.write_text('{"ok":true}\n', encoding="utf-8")
        return ingest_artifact(self.root, path, media_type="application/json", role="execution-trace", producer="test")["id"]

    def _bundle(self, consumer: str, writer: str = "writer") -> dict:
        artifact_id = self._artifact()
        context = context_template(chain_id=1, block_number=20_000_000, evm_revision="cancun")
        return create_bundle(self.root, {
            "payload_type": "semantic-waypoint", "observation": f"reached {consumer}",
            "interpretation": f"{writer} may feed {consumer}", "producer": "test",
            "backend": "foundry", "backend_version": "1.8.6", "target_sha256": "a" * 64,
            "evidence_level": "E3", "artifact_ids": [artifact_id], "execution_context": context,
            "resource_budget": {"cpu_seconds": 1},
            "payload": {"writer": writer, "guard": "g", "consumer": consumer, "state": "s", "property": "p", "state_keys": ["slot0"]},
        })

    def test_event_chain_and_artifact_integrity(self) -> None:
        self.assertTrue(verify_event_chain(self.root)["valid"])
        artifact_id = self._artifact()
        self.assertTrue(verify_artifact(self.root, artifact_id)["valid"])
        self.assertTrue(verify_event_chain(self.root)["valid"])

    def test_event_chain_detects_tampering(self) -> None:
        path = self.root / "events.jsonl"
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        events[-1]["event"] = "tampered"
        path.write_text("\n".join(json.dumps(item) for item in events) + "\n", encoding="utf-8")
        result = verify_event_chain(self.root)
        self.assertFalse(result["valid"])
        self.assertTrue(any("event hash mismatch" in error for error in result["errors"]))

    def test_event_journal_recovers_interrupted_materialization(self) -> None:
        target = self.root / "operations" / "OP-9999.json"
        value = {"schema": "a1x.runtime/v2", "kind": "test-operation", "id": "OP-9999"}
        original = records._write_json_atomic_raw
        failed = False

        def interrupt(path: Path, body: object, *, mode: int = 0o600) -> None:
            nonlocal failed
            if Path(path).resolve() == target.resolve() and not failed:
                failed = True
                raise OSError("synthetic interruption after journal append")
            original(Path(path), body, mode=mode)

        with mock.patch.object(records, "_write_json_atomic_raw", side_effect=interrupt):
            with self.assertRaises(OSError):
                write_json_atomic(target, value)
        self.assertFalse(target.exists())
        require_campaign(self.root)
        self.assertEqual(read_json(target), value)
        self.assertTrue(verify_event_chain(self.root)["valid"])

    def test_typed_evidence_and_rsa_graph(self) -> None:
        left = self._bundle("sink", "source")
        right = self._bundle("payout", "sink")
        self.assertTrue(verify_bundle(self.root, left["id"])["valid"])
        graph = build_compatibility_graph(self.root, [left["id"], right["id"]])
        self.assertEqual(graph["edges"][0]["causal_edges"], ["left-consumer-to-right-writer"])
        round_record = create_evidence_round(self.root, [left["id"], right["id"]], children=1, fresh_lanes=1, per_lane_timeout=60)
        self.assertEqual(round_record["purpose"], "evidence-recombination")
        self.assertTrue((self.root / "scale" / round_record["id"] / "lanes" / "LANE-0001" / "parent-evidence" / "A" / "bundle.json").is_file())
        third = self._bundle("treasury", "payout")
        first = build_compatibility_graph(self.root, [left["id"], right["id"]], idempotency_key="stable-key")
        self.assertEqual(first["nodes"], sorted([left["id"], right["id"]]))
        with self.assertRaises(ValidationError):
            build_compatibility_graph(self.root, [left["id"], third["id"]], idempotency_key="stable-key")

    def test_e6_bundle_requires_replay_and_mechanical_blind_review(self) -> None:
        artifact_id = self._artifact()
        with self.assertRaisesRegex(ValidationError, "candidate_id"):
            create_bundle(self.root, {
                "payload_type": "impact-extension", "observation": "terminal impact reached",
                "interpretation": "the primitive composes into loss", "producer": "test",
                "backend": "foundry", "backend_version": "1.8.6", "target_sha256": "b" * 64,
                "evidence_level": "E6", "artifact_ids": [artifact_id],
                "execution_context": context_template(chain_id=1, block_number=20_000_000, evm_revision="cancun"),
                "resource_budget": {"cpu_seconds": 1}, "payload": {"consumer": "treasury"},
            })

    def test_source_anchor_digest_matches_structured_schema(self) -> None:
        resolved = normalize_evidence_refs(self.root, [{
            "type": "source-anchor", "anchor": "source", "path": "Target.sol",
            "line_start": 1, "line_end": 1,
        }], required=True)[0]
        self.assertEqual(resolved["digest"]["kind"], "file")
        schema_path = Path(__file__).resolve().parents[1] / "scripts" / "schemas" / "evidence-ref.schema.json"
        schema = json.loads(schema_path.read_text())
        source_variant = next(item for item in schema["oneOf"] if item["properties"]["type"].get("const") == "source-anchor")
        self.assertEqual(source_variant["properties"]["digest"]["type"], "object")

    def test_execution_context_7702_and_1153(self) -> None:
        context = context_template(chain_id=1, block_number=1, evm_revision="prague")
        context["eip7702"] = {"starting_delegations": [{"authority": "0x" + "1" * 40, "delegate": "0x" + "2" * 40, "delegate_code_hash": "0x" + "3" * 64}], "authorization_list": None}
        context["eip1153"] = {"transaction_scoped": True, "revert_aware": True, "call_ownership": "DELEGATECALL-caller", "static_context_checked": True}
        self.assertIs(validate_execution_context(context), context)
        context["eip1153"]["revert_aware"] = False
        with self.assertRaises(ValidationError):
            validate_execution_context(context)

    def test_operation_state_machine_and_idempotency(self) -> None:
        (self.root / "capabilities" / "capabilities.json").write_text(json.dumps({"backends": {"foundry": {"ready": True}}}), encoding="utf-8")
        operation = propose_operation(self.root, hypothesis_id=None, blocker="reachability", question="can state be reached?", backend="foundry", expected_information="trace", idempotency_key="one", prerequisites=[], budget={"seconds": 10})
        same = propose_operation(self.root, hypothesis_id=None, blocker="reachability", question="can state be reached?", backend="foundry", expected_information="trace", idempotency_key="one", prerequisites=[], budget={"seconds": 10})
        self.assertEqual(operation["id"], same["id"])
        planned = transition_operation(self.root, operation["id"], status="planned", reason="accepted")
        self.assertEqual(planned["status"], "planned")
        with self.assertRaises(StateTransitionError):
            transition_operation(self.root, operation["id"], status="resolved", reason="skip")

    def test_recon_pack_versions_facts_and_unknowns(self) -> None:
        first = create_recon_pack(self.root, facts=[{"statement": "proxy points to implementation", "source": "cast", "confidence": "observed"}], unknowns=[{"question": "which keeper?", "why_it_matters": "actor model", "next_probe": "read role"}], artifact_ids=[])
        second = create_recon_pack(self.root, facts=[{"statement": "keeper is EOA", "source": "storage", "confidence": "observed"}], unknowns=[], artifact_ids=[], parent=first["version"])
        self.assertEqual(second["parent"], "v0001")

    def test_recon_version_allocation_is_concurrency_safe(self) -> None:
        def create(index: int) -> str:
            return create_recon_pack(
                self.root,
                facts=[{"statement": f"fact-{index}", "source": "test", "confidence": "observed"}],
                unknowns=[], artifact_ids=[],
            )["version"]

        with ThreadPoolExecutor(max_workers=4) as pool:
            versions = list(pool.map(create, range(8)))
        self.assertEqual(len(versions), len(set(versions)))
        self.assertEqual(sorted(versions), [f"v{index:04d}" for index in range(1, 9)])

    def test_progress_identity_ignores_lane_origin_but_retention_does_not(self) -> None:
        base = {"lane_id": "LANE-0001", "status": "near-miss", "causal_identity": {"writer": "W", "guard": "G", "consumer": "C", "state": "S", "property": "P"}, "attacker_fingerprint": "A", "state_fingerprint": "F", "impact_stage": "primitive", "terminal_impact": False, "refutations": [], "evidence": [], "runtime_verification": {"origin_round": "ROUND-0001", "dedup_eligible": False}}
        other = json.loads(json.dumps(base))
        other["lane_id"] = "LANE-0002"
        other["runtime_verification"]["origin_round"] = "ROUND-0002"
        self.assertNotEqual(_population_key(base), _population_key(other))
        self.assertEqual(_semantic_progress_key(base), _semantic_progress_key(other))
        self.assertTrue(assess_semantic_delta({"new_causal_edge": True})["improved"])

    def test_executed_blocked_primitive_remains_rsa_eligible(self) -> None:
        grounded = {
            "status": "blocked",
            "execution": {"ran": True, "property_violated": True},
            "evidence": [{"artifact": "trace", "claim": "counterexample"}],
            "runtime_verification": {"evidence_level": "E4"},
        }
        self.assertTrue(_rsa_eligible(grounded))
        grounded["execution"]["property_violated"] = False
        self.assertFalse(_rsa_eligible(grounded))
        grounded["execution"] = {"ran": False, "property_violated": None}
        self.assertFalse(_rsa_eligible(grounded))

    def test_rsa_progress_requires_evidence_bound_semantic_delta(self) -> None:
        descriptors = {
            name: {"content_sha256": str(index) * 64}
            for index, name in enumerate(("writer", "guard", "consumer", "state", "property", "attacker_model", "state_shape"), start=1)
        }
        descriptors["transition_sequence"] = [{"content_sha256": "8" * 64}]
        parent = {
            "lane_id": "LANE-0001", "mechanism_family": "accounting", "impact_stage": "primitive",
            "causal_identity": {"writer": "claim update", "guard": "none", "consumer": "redeem", "state": "claims", "property": "backing"},
            "attacker_fingerprint": "public caller", "state_fingerprint": "unbacked claims", "terminal_impact": False,
            "evidence": [{"artifact": "trace.txt"}], "refutations": [], "unresolved": ["capital"],
            "runtime_verification": {"evidence_level": "E3", "anchor_descriptors": descriptors},
        }
        reworded = json.loads(json.dumps(parent))
        reworded["lane_id"] = "LANE-0002"
        reworded["causal_identity"]["writer"] = "updates the claim accounting"
        self.assertFalse(_semantic_delta_against_population(reworded, [parent])["improved"])
        advanced = json.loads(json.dumps(reworded))
        advanced["runtime_verification"]["anchor_descriptors"]["consumer"]["content_sha256"] = "9" * 64
        self.assertTrue(_semantic_delta_against_population(advanced, [parent])["improved"])

    def _closure_handoff(self, lane_id: str, lineage_id: str, *, phase: str = "trigger") -> dict:
        phases = []
        order = ("prepare", "trigger", "persist", "settle", "realize", "impact")
        for item in order:
            reached = item == phase
            phases.append({
                "id": item,
                "status": "reached" if reached else "open",
                "property": "invariant drift" if reached else "",
                "evidence_artifact": "trace.txt" if reached else "",
            })
        return {
            "lane_id": lane_id,
            "status": "near-miss",
            "mechanism": "exact-out rounding drift",
            "mechanism_family": "rounding",
            "consumer": "vault settlement",
            "tested_obligation": "invariant does not shrink",
            "discriminator": "fractional factor versus integral control",
            "causal_identity": {"writer": "W", "guard": "G", "consumer": "C", "state": "S", "property": "P"},
            "attacker_fingerprint": "public swapper",
            "state_fingerprint": "dust reserve",
            "impact_stage": "primitive",
            "terminal_impact": False,
            "execution": {"ran": True, "property_violated": False, "command_artifact": "trace.txt", "control_artifact": ""},
            "evidence": [{"artifact": "trace.txt", "claim": "drift", "observation": "D decreased"}],
            "artifacts": ["trace.txt"],
            "refutations": [],
            "unresolved": ["construct reserve-compression prefix"],
            "prerequisites": [{
                "id": "PREREQ-compress",
                "description": "construct reserve-compression prefix",
                "kind": "state",
                "status": "open",
                "resolution_condition": "reach dust using public calls",
                "evidence_artifact": "",
            }],
            "witness": {
                "bug_class": "economic",
                "source_faithful": True,
                "setup_taint": "setup-only",
                "phases": phases,
                "signals": [{"kind": "invariant-drift", "value": "-1", "unit": "D", "evidence_artifact": "trace.txt"}],
            },
            "reachability_guard": {
                "artificial_prerequisite": False,
                "predicate": "reserve compression",
                "writer_paths": [{"actor": "public swapper", "target": "pool reserve", "direction": "decrease", "status": "possible", "non_privileged": True, "evidence_artifact": "trace.txt"}],
            },
            "next_action": "close reserve compression",
            "dimensions": {"evidence_level": "E3", "reachability": "medium", "security_consequence": "high", "state_novelty": "high", "next_test_cost": "medium"},
            "runtime_verification": {
                "evidence_level": "E3",
                "origin_round": "ROUND-9000",
                "origin_lane_id": lane_id,
                "lineage_id": lineage_id,
                "dedup_eligible": False,
                "family_key": "artifact-family:rounding",
                "anchor_descriptors": {},
            },
        }

    def test_balancer_shaped_lead_gets_unary_witness_closure_lane(self) -> None:
        round_id = "ROUND-9000"
        directory = self.root / "scale" / round_id
        (directory / "lanes").mkdir(parents=True)
        handoffs = [
            self._closure_handoff("LANE-0001", "LINEAGE-balancer"),
            self._closure_handoff("LANE-0002", "LINEAGE-other"),
        ]
        handoffs[1]["dimensions"]["security_consequence"] = "medium"
        for handoff in handoffs:
            lane_dir = directory / "lanes" / handoff["lane_id"]
            lane_dir.mkdir()
            (lane_dir / "trace.txt").write_text("D decreased\n", encoding="utf-8")
            (lane_dir / "handoff.json").write_text(json.dumps(handoff), encoding="utf-8")
        write_json_atomic(directory / "plan.json", {
            "id": round_id, "purpose": "population-pool", "generation": 0, "status": "completed",
            "lanes": [{"lane_id": item["lane_id"], "path": f"lanes/{item['lane_id']}"} for item in handoffs],
        })
        write_json_atomic(directory / "aggregate.json", {
            "round_id": round_id, "handoffs": handoffs, "reserve_handoffs": [], "invalid_lanes": [],
        })
        child = create_recombination_round(
            self.root, parent_round=round_id, children=2, closure_lanes=1, fresh_lanes=0, per_lane_timeout=60,
        )
        self.assertEqual(child["lanes"][0]["lane_role"], "witness-closure")
        self.assertEqual(child["lanes"][0]["lineage_id"], "LINEAGE-balancer")
        self.assertEqual(child["lanes"][1]["lane_role"], "recombination")
        self.assertIn("Do not switch targets", (self.root / "scale" / child["id"] / "lanes" / "LANE-0001" / "prompt.md").read_text())
        full = create_recombination_round(
            self.root, parent_round=round_id, children=4, closure_lanes=1, fresh_lanes=0, per_lane_timeout=60,
        )
        self.assertEqual(
            {item.get("composition_topology") for item in full["lanes"] if item["lane_role"] == "recombination"},
            {"sequential", "nested", "temporal"},
        )

    def test_mcp_config_detection_is_structural(self) -> None:
        self.assertFalse(_has_mcp_server("# [mcp_servers.wake-lane]\n", "wake-lane"))
        self.assertTrue(_has_mcp_server("[mcp_servers.wake-lane]\ncommand = \"wake\"\n", "wake-lane"))

    def test_prerequisite_regression_cannot_masquerade_as_consumer_progress(self) -> None:
        parent = self._closure_handoff("LANE-0001", "LINEAGE-balancer")
        child = json.loads(json.dumps(parent))
        child["lane_id"] = "LANE-0002"
        child["impact_stage"] = "consumer"
        child["prerequisites"].append({
            "id": "PREREQ-new",
            "description": "new speculative dependency",
            "kind": "other",
            "status": "open",
            "resolution_condition": "prove it",
            "evidence_artifact": "",
        })
        delta = _semantic_delta_against_population(child, [parent])
        self.assertTrue(delta["regressed"])
        self.assertFalse(delta["claimed"]["stronger_consumer"])
        self.assertFalse(delta["improved"])

        child["witness"]["phases"][0].update({
            "status": "reached", "property": "dust reached", "evidence_artifact": "trace.txt",
        })
        advanced = _semantic_delta_against_population(child, [parent])
        self.assertTrue(advanced["regressed"])
        self.assertTrue(advanced["claimed"]["phase_advanced"])
        self.assertTrue(advanced["improved"])

    def test_host_preserves_omitted_parent_prerequisite_and_scores_phase_progress(self) -> None:
        parent = self._closure_handoff("LANE-0001", "LINEAGE-balancer")
        canonical = canonicalize_prerequisites(
            [], lineage_id="LINEAGE-balancer", parents=[parent], artifact_exists=lambda _: True,
        )
        self.assertEqual([item["id"] for item in canonical], ["PREREQ-compress"])
        child = json.loads(json.dumps(parent))
        child["witness"]["phases"][0].update({"status": "reached", "property": "dust reached", "evidence_artifact": "trace.txt"})
        delta = _semantic_delta_against_population(child, [parent])
        self.assertTrue(delta["claimed"]["phase_advanced"])
        self.assertTrue(delta["improved"])
        self.assertTrue(needs_witness_closure(parent))
        self.assertGreater(_fitness(child), _fitness(parent))

    def test_composition_priority_uses_structured_prerequisite_edges(self) -> None:
        left = self._closure_handoff("LANE-0001", "LINEAGE-left")
        right = self._closure_handoff("LANE-0002", "LINEAGE-right")
        right["prerequisites"][0]["id"] = "PREREQ-shared"
        left["prerequisites"][0].update({"id": "PREREQ-shared", "status": "resolved", "evidence_artifact": "trace.txt"})
        self.assertEqual(_composition_priority(left, right)[0], 1)

    def test_unrelated_fresh_progress_does_not_reset_balancer_lineage(self) -> None:
        balancer = self._closure_handoff("LANE-0001", "LINEAGE-balancer")
        fresh = self._closure_handoff("LANE-0002", "LINEAGE-fresh")
        counters = {"LINEAGE-balancer": 1}
        improved = _update_lineage_stagnation(
            counters,
            prior=[balancer],
            children=[fresh],
            semantic_deltas={"LANE-0002": {"lineage_id": "LINEAGE-fresh", "improved": True}},
        )
        self.assertEqual(improved, {"LINEAGE-fresh"})
        self.assertEqual(counters["LINEAGE-balancer"], 1)
        self.assertEqual(counters["LINEAGE-fresh"], 0)

    def test_contiguous_phase_progress_and_reachability_closure(self) -> None:
        conditional = self._closure_handoff("LANE-0001", "LINEAGE-conditional", phase="trigger")
        conditional["witness"]["source_faithful"] = False
        conditional["witness"]["setup_taint"] = "attack-path"
        conditional["reachability_guard"]["artificial_prerequisite"] = True
        self.assertEqual(witness_progress(conditional)[0], -1)
        self.assertTrue(needs_reachability_closure(conditional))
        self.assertFalse(needs_witness_closure(conditional))
        conditional["witness"]["phases"][0].update(
            {"status": "reached", "property": "state constructed", "evidence_artifact": "trace.txt"}
        )
        self.assertEqual(witness_progress(conditional)[0], 1)

    def test_failed_protected_closure_is_retried_and_not_replaced(self) -> None:
        parent = self._closure_handoff("LANE-0001", "LINEAGE-balancer")
        unrelated_a = self._closure_handoff("LANE-0002", "LINEAGE-a")
        unrelated_b = self._closure_handoff("LANE-0003", "LINEAGE-b")
        child_id = "ROUND-9100"
        child_dir = self.root / "scale" / child_id
        child_dir.mkdir()
        child_plan = {
            "id": child_id,
            "status": "partial",
            "lanes": [
                {"lane_id": "LANE-0001", "lane_role": "witness-closure"},
                {"lane_id": "LANE-0002", "lane_role": "recombination"},
                {"lane_id": "LANE-0003", "lane_role": "fresh-exploration"},
            ],
        }
        write_json_atomic(child_dir / "plan.json", child_plan)
        write_json_atomic(child_dir / "results.json", {
            "results": [
                {"lane_id": "LANE-0001", "status": "failed"},
                {"lane_id": "LANE-0002", "status": "completed"},
                {"lane_id": "LANE-0003", "status": "completed"},
            ]
        })

        def aggregate(_root: Path, *, round_id: str) -> dict:
            if round_id == "ROUND-parent":
                return {"handoffs": [parent], "reserve_handoffs": []}
            return {"handoffs": [unrelated_a, unrelated_b], "reserve_handoffs": []}

        with (
            mock.patch("a1x_runtime.scale.aggregate_round", side_effect=aggregate),
            mock.patch("a1x_runtime.scale.auto_select_frontier"),
            mock.patch("a1x_runtime.scale.create_recombination_round", return_value=child_plan),
            mock.patch("a1x_runtime.scale.run_round", return_value={"status": "partial"}) as run,
        ):
            result = evolve_population(
                self.root,
                parent_round="ROUND-parent",
                generations=2,
                children=3,
                fresh_lanes=1,
                stagnation_rounds=2,
                parallel=1,
                codex_bin="codex",
                model=None,
                reasoning=None,
                sandbox="workspace-write",
                allow_env_auth=False,
                per_lane_timeout=60,
            )
        self.assertEqual(run.call_count, 2)
        self.assertEqual(result["stop_reason"], "protected-witness-closure-failed")
        self.assertEqual(result["history"][0]["missing_witness_closure_lanes"], ["LANE-0001"])

    def test_pinned_prestate_rejects_writes(self) -> None:
        request = _pin_request({"jsonrpc": "2.0", "id": 1, "method": "eth_getCode", "params": ["0x" + "0" * 40, "latest"]}, 123)
        self.assertEqual(request["params"][-1], hex(123))
        receipts = _pin_request({"jsonrpc": "2.0", "id": 2, "method": "eth_getBlockReceipts", "params": ["latest"]}, 123)
        self.assertEqual(receipts["params"][0], hex(123))
        fees = _pin_request({"jsonrpc": "2.0", "id": 3, "method": "eth_feeHistory", "params": [5, "latest", []]}, 123)
        self.assertEqual(fees["params"][1], hex(123))
        with self.assertRaises(ValidationError):
            _pin_request({"method": "eth_getCode", "params": ["0x" + "0" * 40, hex(124)]}, 123)
        with self.assertRaises(ValidationError):
            _pin_request({"method": "eth_getLogs", "params": [{"fromBlock": hex(1), "toBlock": hex(124)}]}, 123)
        with self.assertRaises(ValidationError):
            _pin_request({"method": "eth_sendRawTransaction", "params": []}, 123)

    def test_pinned_prestate_rejects_future_transaction_and_block_hash(self) -> None:
        state = _ProxyState(upstream_url="https://redacted.invalid", block_number=123, cache_dir=self.root / "prestate-cache")

        def upstream(_url: str, request: dict) -> dict:
            if request["method"] == "eth_getTransactionByHash":
                return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"blockNumber": hex(124)}}
            if request["method"] == "eth_getBlockByHash":
                return {"jsonrpc": "2.0", "id": request.get("id"), "result": {"number": hex(124)}}
            raise AssertionError(request)

        with mock.patch("a1x_runtime.prestate._upstream", side_effect=upstream):
            transaction = state.dispatch({
                "jsonrpc": "2.0", "id": 1, "method": "debug_traceTransaction", "params": ["0x" + "1" * 64],
            })
            self.assertIn("beyond pinned block", transaction["error"]["message"])
            block = state.dispatch({
                "jsonrpc": "2.0", "id": 2, "method": "eth_getBlockByHash", "params": ["0x" + "2" * 64, False],
            })
            self.assertIn("beyond pinned block", block["error"]["message"])

    def test_mcp_facade_has_no_private_runtime_state(self) -> None:
        response = dispatch({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        self.assertEqual(response["result"]["serverInfo"]["version"], "4.4.0")
        tools = dispatch({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        self.assertIn("campaign_show", tool_names)
        self.assertIn("explorer_retrieve", tool_names)

    def test_mechanical_blind_review_runs_fresh_process(self) -> None:
        (self.root / "candidates" / "CAND-0001.json").write_text(json.dumps({"id": "CAND-0001", "property": "assets remain backed", "support_run": "RUN-0001", "control_run": "RUN-0002", "replay_id": "REPLAY-0001", "fidelity": {}}), encoding="utf-8")
        (self.root / "replays" / "REPLAY-0001.json").write_text(json.dumps({"id": "REPLAY-0001", "passed": True}), encoding="utf-8")
        prepared = prepare_blind_review(self.root, "CAND-0001")
        script = Path(self.temporary.name) / "reviewer.py"
        script.write_text("import json,sys\njson.load(open(sys.argv[1]))\njson.dump({'verdict':'confirmed','reproduced':True,'challenges':['causality','actor','impact']},open(sys.argv[2],'w'))\n", encoding="utf-8")
        completed = execute_blind_review(self.root, prepared["id"], argv=[sys.executable, str(script), "{packet}", "{output}"], timeout_seconds=30)
        self.assertEqual(completed["status"], "completed")
        self.assertTrue(qualifies(self.root, prepared["id"], "CAND-0001"))

    def test_equal_cost_evaluation_records_all_dimensions(self) -> None:
        costs = {"wall_seconds": 10, "cpu_core_seconds": 20, "peak_memory_bytes": 1000, "llm_input_tokens": 30, "llm_output_tokens": 10, "rpc_requests": 2, "evm_executions": 500}
        record_trial(self.root, incident="incident-1", configuration="v4-foundry-wake", outcome="near-miss", costs=costs, evidence_id=None, notes="smoke")
        summary = evaluation_summary(self.root)
        self.assertEqual(summary["configurations"]["v4-foundry-wake"]["replayable_witnesses"], 0)
        with self.assertRaisesRegex(ValidationError, "requires linked evidence"):
            record_trial(self.root, incident="incident-2", configuration="v4.4", outcome="replayable-witness", costs=costs, evidence_id=None, notes="invalid")

    def test_attempt_aware_fairness_and_operational_allowance(self) -> None:
        first = select_fair_lineages(
            self.root,
            candidates=[
                {"lineage_id": "LINEAGE-a", "priority": [1]},
                {"lineage_id": "LINEAGE-b", "priority": [9]},
            ],
            slots=1,
            generation=1,
        )
        self.assertEqual(first, ["LINEAGE-b"])
        record_lineage_attempts(self.root, generation=1, outcomes=[{
            "lineage_id": "LINEAGE-b", "operational_failure": True,
            "semantic_progress": False, "witness_progress": False, "information_progress": False,
        }])
        second = select_fair_lineages(
            self.root,
            candidates=[
                {"lineage_id": "LINEAGE-a", "priority": [1]},
                {"lineage_id": "LINEAGE-b", "priority": [9]},
            ],
            slots=1,
            generation=2,
        )
        self.assertEqual(second, ["LINEAGE-a"])
        state = scheduling_state(self.root)
        self.assertEqual(state["lineages"]["LINEAGE-b"]["research_attempts"], 0)
        self.assertEqual(state["lineages"]["LINEAGE-b"]["operational_failures"], 1)

    def test_three_profile_equal_budget_benchmark_requires_adjudication(self) -> None:
        budget = {"wall_seconds": 100, "cpu_core_seconds": 200, "peak_memory_bytes": 10000, "llm_input_tokens": 1000, "llm_output_tokens": 500, "rpc_requests": 100, "evm_executions": 10000}
        costs = {"wall_seconds": 10, "cpu_core_seconds": 20, "peak_memory_bytes": 1000, "llm_input_tokens": 100, "llm_output_tokens": 50, "rpc_requests": 10, "evm_executions": 1000}
        suite = create_benchmark_suite(self.root, {
            "name": "frozen-integrity-full",
            "incidents": ["held-out-incident"],
            "controlled_variables": {
                "model": "same-model",
                "target_information": "same-package",
                "tools": "same-installed-capabilities",
                "chain_block": "chain-1-block-20000000",
                "attacker_model": "unprivileged",
            },
            "resource_budget": budget,
            "v4_commit": "working-tree",
            "held_out_required": True,
        })
        evidence = self._bundle("benchmark-adjudication")
        outcomes = {
            "v4.3.0-frozen": "near-miss",
            "v4.4.0-integrity": "replayable-witness",
            "v4.4.0-full": "validated-root-cause",
        }
        for configuration, outcome in outcomes.items():
            trial = record_trial(
                self.root,
                incident="held-out-incident",
                configuration=configuration,
                outcome=outcome,
                costs=costs,
                evidence_id=evidence["id"] if outcome != "near-miss" else None,
                notes="equal-envelope regression fixture",
            )
            adjudicate_trial(self.root, trial_id=trial["id"], outcome=outcome, evidence_id=evidence["id"], notes="independent fixture adjudication")
            attach_benchmark_trial(self.root, benchmark_id=suite["id"], trial_id=trial["id"])
        compared = compare_benchmark(self.root, suite["id"])
        self.assertTrue(compared["valid"], compared["errors"])
        self.assertEqual(compared["metrics"]["v4.4.0-full"]["validated_root_causes"], 1)


class MigrationTest(unittest.TestCase):
    def test_explicit_legacy_migration_preserves_old_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "campaign.json").write_text(json.dumps({"schema": LEGACY_RUNTIME_SCHEMA, "kind": "campaign", "runtime_version": "3.1.2", "updated_at": "old", "source": {"initial_digest": "x"}, "research_counters": {}}), encoding="utf-8")
            (root / "counters.json").write_text("{}", encoding="utf-8")
            legacy = b'{"at":"old","event":"legacy"}\n'
            (root / "events.jsonl").write_bytes(legacy)
            with self.assertRaises(ValidationError):
                create_recon_pack(root, facts=[{"statement": "x", "source": "y", "confidence": "z"}], unknowns=[], artifact_ids=[])
            result = migrate_campaign(root)
            self.assertTrue(result["migrated"])
            self.assertTrue((root / "events.jsonl").read_bytes().startswith(legacy))
            self.assertTrue(verify_event_chain(root)["valid"])

    def test_v43_to_v44_migration_is_additive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            (source / "Target.sol").write_text("contract Target {}\n", encoding="utf-8")
            root = base / "campaign"
            init_campaign(
                root, label="v43", source=source, target="Target", chain_id=1,
                block_number=20_000_000, rpc_env="MAINNET_RPC_URL", authorization="local test",
                budgets={"max_runs": 20, "max_scale_lanes": 20, "max_parallel": 2, "default_run_timeout_seconds": 60, "default_output_bytes": 100000},
            )
            campaign = read_json(root / "campaign.json")
            campaign["runtime_version"] = "4.3.0"
            write_json_atomic(root / "campaign.json", campaign)
            preserved = root / "orchestration" / "v43-preserved.json"
            preserved.write_bytes(b'{"kind":"frozen-v43-record","value":7}\n')
            before = preserved.read_bytes()
            result = migrate_campaign(root)
            self.assertTrue(result["migrated"])
            self.assertEqual(result["migration"]["from_runtime_version"], "4.3.0")
            self.assertEqual(result["campaign"]["runtime_version"], "4.4.0")
            self.assertEqual(preserved.read_bytes(), before)
            self.assertTrue((root / "harnesses").is_dir())
            self.assertTrue((root / "orchestration" / "features.json").is_file())
            self.assertTrue(verify_event_chain(root)["valid"])


if __name__ == "__main__":
    unittest.main()
