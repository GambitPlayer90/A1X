from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from a1x_runtime.campaign import add_hypothesis, add_obligation, init_campaign, migrate_campaign
from a1x_runtime.artifacts import ingest_artifact
from a1x_runtime.blind_review import prepare_blind_review, qualifies, record_in_session_review
from a1x_runtime.atomic import seal, write_json_atomic
from a1x_runtime.candidates import check_gates, create_candidate, promote_validated
from a1x_runtime.cli import build_parser
from a1x_runtime.controller import assess_completion
from a1x_runtime.errors import IntegrityError, ValidationError
from a1x_runtime.ledger import add_record, link_runtime_ref, migrate_v4, query_ledger, update_record, verify_ledger
from a1x_runtime.process import reject_model_argv
from a1x_runtime.recon import record_coverage_gate, verify_coverage_gate


class V5SingleSessionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.source = base / "source"
        self.source.mkdir()
        (self.source / "Target.sol").write_text("contract Target {}\n", encoding="utf-8")
        self.root = base / "campaign"
        init_campaign(
            self.root,
            label="single-session-test",
            source=self.source,
            target="Target",
            chain_id=1,
            block_number=123,
            rpc_env="MAINNET_RPC_URL",
            authorization="authorized local test",
            budgets={"max_runs": 20, "max_scale_lanes": 1, "max_parallel": 2, "default_run_timeout_seconds": 60, "default_output_bytes": 100000},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _sealed_run(
        self,
        run_id: str,
        *,
        plan: dict,
        mechanical_success: bool = True,
        outcome: str = "supports",
        property_violated: bool = True,
    ) -> None:
        run_dir = self.root / "runs" / run_id
        run_dir.mkdir(exist_ok=True)
        plan = {"id": run_id, "hypothesis_id": "HYP-0001", "property": "claims remain backed", **plan}
        write_json_atomic(run_dir / "plan.json", plan)
        plan_sha = seal(run_dir / "plan.json", run_dir / "plan.sha256")
        write_json_atomic(
            run_dir / "receipt.json",
            {"run_id": run_id, "plan_sha256": plan_sha, "mechanical_success": mechanical_success},
        )
        seal(run_dir / "receipt.json", run_dir / "receipt.sha256")
        write_json_atomic(
            run_dir / "observation.json",
            {"run_id": run_id, "outcome": outcome, "property_violated": property_violated},
        )
        seal(run_dir / "observation.json", run_dir / "observation.sha256")

    def _sealed_replay(self, replay_id: str, run_id: str, *, passed: bool = True) -> dict:
        replay = {"id": replay_id, "run_id": run_id, "passed": passed}
        directory = self.root / "replays" / replay_id
        directory.mkdir(exist_ok=True)
        write_json_atomic(directory / "verification.json", replay)
        seal(directory / "verification.json", directory / "verification.sha256")
        write_json_atomic(self.root / "replays" / f"{replay_id}.json", replay)
        return replay

    def _bind_empty_recon_coverage(self) -> dict:
        base = Path(self.temporary.name) / "recon-inputs"
        base.mkdir(exist_ok=True)
        scan = base / "entry-points.json"
        coverage = base / "coverage-map.json"
        scan.write_text(json.dumps({
            "schema_version": 2,
            "path_basis": "root-relative",
            "scope_mode": "paths",
            "scope_inputs": ["."],
            "files": ["Target.sol"],
            "source_inventory": [{
                "path": "Target.sol",
                "sha256": hashlib.sha256((self.source / "Target.sol").read_bytes()).hexdigest(),
            }],
            "entry_points": [],
            "read_surfaces": [],
            "problems": [],
        }), encoding="utf-8")
        coverage.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"path": "Target.sol", "status": "analyzed", "evidence": ["Target.sol:1"]}],
            "entry_points": [],
            "read_surfaces": [],
        }), encoding="utf-8")
        return record_coverage_gate(self.root, entry_points_path=scan, coverage_map_path=coverage)

    def test_init_creates_compact_ledger_and_no_rounds(self) -> None:
        result = verify_ledger(self.root)
        self.assertTrue(result["valid"])
        self.assertEqual(result["records"], 0)
        self.assertFalse(any((self.root / "scale").glob("ROUND-*")))
        self.assertTrue((self.root / "v5" / "ledger.tsv").is_file())
        self.assertTrue((self.root / "v5" / "brief.md").is_file())

    def test_stable_investigation_identity_and_stale_write_guard(self) -> None:
        scope = add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="authorized target and eligible impacts",
            status="active",
            priority="critical",
            data={"impacts": ["direct theft"], "cost": "low"},
        )
        investigation = add_record(
            self.root,
            kind="INV",
            title="ledger drift",
            statement="split settlement may create unbacked credit",
            stage="lead",
            priority="high",
            scope=[scope["id"]],
            next_action="execute the split versus one-shot discriminator",
            data={"cost": "low"},
        )
        updated = update_record(
            self.root,
            investigation["id"],
            expected_revision=1,
            changes={"stage": "candidate", "status": "active"},
            reason="faithful execution reached the suspicious state",
        )
        self.assertEqual(updated["id"], investigation["id"])
        self.assertEqual(updated["revision"], 2)
        with self.assertRaises(IntegrityError):
            update_record(
                self.root,
                investigation["id"],
                expected_revision=1,
                changes={"status": "closed"},
                reason="stale overwrite",
            )

    def test_tasks_and_synthesis_require_actionable_payloads(self) -> None:
        with self.assertRaises(ValidationError):
            add_record(self.root, kind="TASK", title="bad", statement="bad task", data={})
        with self.assertRaises(ValidationError):
            add_record(self.root, kind="SYN", title="bad", statement="summary only", data={"revised_attempt": "try again"})
        scope = add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="authorized target",
            status="active",
            priority="critical",
            data={"impacts": ["direct theft"], "cost": "low"},
        )
        investigation = add_record(
            self.root,
            kind="INV",
            title="settlement drift",
            statement="settlement may preserve transient credit",
            stage="hypothesis",
            scope=[scope["id"]],
            next_action="test settlement",
        )
        task = add_record(
            self.root,
            kind="TASK",
            title="settlement challenge",
            statement="determine whether settlement reconciles callback drift",
            next_action="give the rationale-withheld packet to a visible subagent",
            data={"question": "Does settlement reconcile the measured drift?", "cost": "medium", "withheld": ["preferred explanation"]},
        )
        synthesis = add_record(
            self.root,
            kind="SYN",
            title="revised settlement test",
            statement="combine callback waypoint and exact bound",
            parents=[investigation["id"], task["id"]],
            data={
                "investigation_id": investigation["id"],
                "inputs": [task["id"]],
                "grounded_delta": "the callback reaches the exact bound before settlement",
                "revised_attempt": "replay the callback at the exact bound and then settle",
                "next_discriminator": "compare post-settlement backing against the one-shot control",
                "follow_through": "pending",
                "cost": "low",
            },
        )
        self.assertEqual(query_ledger(self.root, kind="SYN")[0]["id"], synthesis["id"])

    def test_legacy_migration_is_additive_and_idempotent(self) -> None:
        obligation = {"id": "OBL-9999", "title": "legacy obligation", "statement": "legacy property"}
        (self.root / "obligations" / "OBL-9999.json").write_text(json.dumps(obligation), encoding="utf-8")
        campaign_before = hashlib.sha256((self.root / "campaign.json").read_bytes()).hexdigest()
        events_before = hashlib.sha256((self.root / "events.jsonl").read_bytes()).hexdigest()
        preview = migrate_v4(self.root, apply=False)
        self.assertGreaterEqual(preview["pending"], 2)
        first = migrate_v4(self.root, apply=True)
        second = migrate_v4(self.root, apply=True)
        self.assertTrue(first["imported"])
        self.assertEqual(second["imported"], [])
        self.assertEqual(hashlib.sha256((self.root / "campaign.json").read_bytes()).hexdigest(), campaign_before)
        self.assertEqual(hashlib.sha256((self.root / "events.jsonl").read_bytes()).hexdigest(), events_before)

    def test_migrations_are_byte_idempotent_and_never_downgrade_v5(self) -> None:
        first = migrate_v4(self.root, apply=True)
        self.assertTrue(first["imported"])
        ledger_before = (self.root / "v5" / "ledger.json").read_bytes()
        second = migrate_v4(self.root, apply=True)
        self.assertEqual(second["imported"], [])
        self.assertEqual((self.root / "v5" / "ledger.json").read_bytes(), ledger_before)
        campaign_before = (self.root / "campaign.json").read_bytes()
        result = migrate_campaign(self.root)
        self.assertFalse(result["migrated"])
        self.assertEqual(result["campaign"]["runtime_version"], "5.2.0")
        self.assertEqual((self.root / "campaign.json").read_bytes(), campaign_before)

    def test_invalid_cost_is_rejected_before_completion_and_model_cli_is_forbidden(self) -> None:
        with self.assertRaises(ValidationError):
            add_record(
                self.root,
                kind="FACT",
                title="bad cost",
                statement="malformed scheduling data",
                data={"cost": []},
            )
        with self.assertRaises(ValidationError):
            reject_model_argv(["codex", "exec", "hidden"])
        fake_model = Path(self.temporary.name) / "codex"
        fake_model.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake_model.chmod(0o755)
        aliased_tool = Path(self.temporary.name) / "deterministic-tool"
        aliased_tool.symlink_to(fake_model)
        with self.assertRaises(ValidationError):
            reject_model_argv([str(aliased_tool), "exec", "hidden"])

    def test_only_active_scope_satisfies_completion_scope_gate(self) -> None:
        add_record(
            self.root,
            kind="SCOPE",
            title="refuted program",
            statement="not an active scope",
            status="refuted",
            priority="critical",
            data={"impacts": ["direct theft"], "cost": "low"},
        )
        result = assess_completion(self.root)
        gates = {item["gate"] for item in result["blockers"]}
        self.assertIn("PROGRAM-SCOPE", gates)

    def test_typed_records_crosslink_and_candidate_requires_exact_scope_impact(self) -> None:
        scope = add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="exact authorized boundary",
            status="active",
            priority="critical",
            data={"impacts": ["Direct theft of user funds"], "cost": "low"},
        )
        ledger_obligation = add_record(
            self.root,
            kind="OBL",
            title="backing",
            statement="claims remain backed",
            scope=[scope["id"]],
        )
        investigation = add_record(
            self.root,
            kind="INV",
            title="split settlement",
            statement="split updates may create unbacked claims",
            stage="lead",
            priority="high",
            parents=[ledger_obligation["id"]],
            scope=[scope["id"]],
            next_action="execute split versus one-shot",
            data={"cost": "low"},
        )
        obligation = add_obligation(
            self.root,
            title="backing",
            statement="claims remain backed",
            boundary="settlement",
            units="wei",
            oracle="independent assets minus liabilities",
            ledger_obligation_id=ledger_obligation["id"],
        )
        hypothesis = add_hypothesis(
            self.root,
            obligation_id=obligation["id"],
            mechanism="split settlement leaves excess credit",
            sequence="prepare -> split -> settle",
            support_prediction="credit exceeds backing",
            refute_prediction="settlement reconciles",
            next_action="execute the discriminator",
            ledger_investigation_id=investigation["id"],
        )
        experiment = add_record(
            self.root,
            kind="EXP",
            title="split versus one-shot",
            statement="execute the settlement discriminator",
            parents=[investigation["id"]],
            scope=[scope["id"]],
            next_action="execute sealed run",
            data={"cost": "low"},
        )
        self._sealed_run(
            "RUN-0001",
            plan={
                "hypothesis_id": hypothesis["id"],
                "ledger_investigation_id": investigation["id"],
                "ledger_experiment_id": experiment["id"],
            },
        )
        link_runtime_ref(
            self.root,
            experiment["id"],
            "runs/RUN-0001/plan.json",
            expected_kind="EXP",
            reason="test run plan linkage",
            status="active",
        )
        with self.assertRaises(ValidationError):
            create_candidate(
                self.root,
                hypothesis_id=hypothesis["id"], support_run="RUN-0001", control_run=None, replay_id=None,
                root_cause="split accounting", code_evidence="Target.sol:1", reachability="unprivileged call",
                property_statement="claims remain backed", impact="loss", scope_id=scope["id"],
                eligible_impact="direct theft of user funds", implementation_verified=True,
                configuration_verified=True, actor_verified=True, economics_verified=True,
            )
        candidate = create_candidate(
            self.root,
            hypothesis_id=hypothesis["id"], support_run="RUN-0001", control_run=None, replay_id=None,
            root_cause="split accounting", code_evidence="Target.sol:1", reachability="unprivileged call",
            property_statement="claims remain backed", impact="loss", scope_id=scope["id"],
            eligible_impact="Direct theft of user funds", implementation_verified=True,
            configuration_verified=True, actor_verified=True, economics_verified=True,
        )
        linked = query_ledger(self.root, kind="INV")[0]
        self.assertEqual(candidate["ledger_investigation_id"], investigation["id"])
        self.assertIn(f"candidates/{candidate['id']}.json", linked["data"]["runtime_refs"])

    def test_candidate_gate_rejects_wrong_replay_and_tampered_run_evidence(self) -> None:
        self._sealed_run("RUN-0001", plan={"run_class": "candidate"})
        self._sealed_run(
            "RUN-0002",
            plan={
                "run_class": "control",
                "control_for_run": "RUN-0001",
                "control_contract": {
                    "support_run": "RUN-0001",
                    "claim": "remove the enabling transition",
                    "changed_argv": [2],
                },
            },
            outcome="refutes",
            property_violated=False,
        )
        self._sealed_replay("REPLAY-0001", "RUN-0003")
        candidate = {
            "id": "CAND-0001",
            "hypothesis_id": "HYP-0001",
            "support_run": "RUN-0001",
            "control_run": "RUN-0002",
            "replay_id": "REPLAY-0001",
            "root_cause": "split accounting",
            "code_evidence": "Target.sol:1",
            "reachability": "unprivileged sequence",
            "property": "claims remain backed",
            "impact": "direct theft",
            "fidelity": {
                "implementation_verified": True,
                "configuration_verified": True,
                "actor_verified": True,
                "economics_verified": True,
            },
            "blind_reviews": ["BLIND-0001"],
            "reviews": [],
            "status": "candidate",
        }
        write_json_atomic(self.root / "candidates" / "CAND-0001.json", candidate)
        with mock.patch("a1x_runtime.blind_review.qualifies", return_value=True):
            result = check_gates(self.root, "CAND-0001")
            self.assertEqual(result["mechanical_evidence_ceiling"], "E5")
            self.assertTrue(any("not supporting run RUN-0001" in error for error in result["integrity_errors"]))
            with self.assertRaises(ValidationError):
                promote_validated(self.root, "CAND-0001")

        self._sealed_replay("REPLAY-0002", "RUN-0001")
        candidate["replay_id"] = "REPLAY-0002"
        write_json_atomic(self.root / "candidates" / "CAND-0001.json", candidate)
        observation = self.root / "runs" / "RUN-0001" / "observation.json"
        tampered = json.loads(observation.read_text(encoding="utf-8"))
        tampered["property_violated"] = False
        write_json_atomic(observation, tampered)
        with mock.patch("a1x_runtime.blind_review.qualifies", return_value=True):
            result = check_gates(self.root, "CAND-0001")
        self.assertEqual(result["mechanical_evidence_ceiling"], "E2")
        self.assertTrue(any("seal mismatch" in error for error in result["integrity_errors"]))

    def test_synthesis_requires_grounded_links_and_blocks_clean_completion(self) -> None:
        scope = add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="authorized target",
            status="active",
            priority="critical",
            data={"impacts": ["direct theft"], "cost": "low"},
        )
        investigation = add_record(
            self.root,
            kind="INV",
            title="accounting drift",
            statement="callback may expose transient drift",
            status="closed",
            stage="closed",
            priority="medium",
            scope=[scope["id"]],
        )
        fact = add_record(
            self.root,
            kind="FACT",
            title="reachable callback",
            statement="the callback is reachable by an unprivileged actor",
            status="closed",
        )
        with self.assertRaises(ValidationError):
            add_record(
                self.root,
                kind="SYN",
                title="unbound synthesis",
                statement="summary only",
                data={
                    "revised_attempt": "try a different consumer",
                    "next_discriminator": "execute it",
                    "follow_through": "pending",
                },
            )
        synthesis = add_record(
            self.root,
            kind="SYN",
            title="consumer substitution",
            statement="route the transient value into a different consumer",
            status="open",
            priority="high",
            parents=[investigation["id"], fact["id"]],
            scope=[scope["id"]],
            data={
                "investigation_id": investigation["id"],
                "inputs": [fact["id"]],
                "grounded_delta": "the callback is reachable before settlement",
                "revised_attempt": "invoke the alternate consumer inside the callback",
                "next_discriminator": "compare pre-settlement and post-settlement backing",
                "follow_through": "pending",
                "cost": "low",
            },
        )
        result = assess_completion(self.root)
        self.assertTrue(any(synthesis["id"] in item["reason"] for item in result["blockers"]))
        with self.assertRaises(ValidationError):
            update_record(
                self.root,
                synthesis["id"],
                expected_revision=1,
                changes={"status": "closed"},
                reason="incorrectly close without follow-through",
            )
        current = query_ledger(self.root, kind="SYN")[0]
        data = dict(current["data"])
        incomplete_deferral = dict(data)
        incomplete_deferral.update({
            "follow_through": "deferred",
            "deferred_reason": "upstream protocol state is unavailable",
        })
        with self.assertRaisesRegex(ValidationError, "blocker_kind"):
            update_record(
                self.root,
                synthesis["id"],
                expected_revision=current["revision"],
                changes={"status": "closed", "data": incomplete_deferral},
                reason="deferral without recovery metadata must fail",
            )
        data.update({
            "follow_through": "deferred",
            "deferred_reason": "upstream protocol state is unavailable",
            "blocker_kind": "environment",
            "reopen_condition": "a faithful upstream state fixture becomes available",
        })
        closed = update_record(
            self.root,
            synthesis["id"],
            expected_revision=current["revision"],
            changes={"status": "closed", "data": data},
            reason="explicitly defer with a preserved blocker",
        )
        self.assertEqual(closed["data"]["follow_through"], "deferred")
        for family in ("value", "authority", "lifecycle", "numeric", "composition"):
            write_json_atomic(
                self.root / "orchestration" / f"coverage-{family}.json",
                {"family": family, "status": "challenged", "evidence_refs": [], "limitations": "unit fixture"},
            )
        with mock.patch("a1x_runtime.recon.verify_coverage_gate", return_value={"valid": True}):
            completion = assess_completion(self.root)
        self.assertEqual(completion["blockers"], [])
        risk = next(item for item in completion["open_risks"] if item["record"] == synthesis["id"])
        self.assertEqual(risk["kind"], "environment")
        self.assertIn("reopen when", risk["reason"])
        self.assertEqual(completion["disposition"], "ENVIRONMENT_BLOCKED")
        self.assertFalse(completion["ready"])
        brief = (self.root / "v5" / "brief.md").read_text(encoding="utf-8")
        self.assertIn("Deferred synthesis risks", brief)
        self.assertIn(synthesis["id"], brief)
        with self.assertRaises(ValidationError):
            add_record(
                self.root,
                kind="FACT",
                title="missing evidence",
                statement="must not accept a nonexistent artifact",
                evidence=["recon/does-not-exist.json"],
            )

    def test_synthesis_executed_requires_observed_bound_run(self) -> None:
        scope = add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="authorized target",
            status="active",
            priority="critical",
            data={"impacts": ["direct theft"], "cost": "low"},
        )
        investigation = add_record(
            self.root,
            kind="INV",
            title="settlement drift",
            statement="settlement may preserve transient credit",
            status="closed",
            stage="closed",
            scope=[scope["id"]],
        )
        fact = add_record(
            self.root,
            kind="FACT",
            title="reachable callback",
            statement="the callback is attacker reachable",
            status="closed",
        )
        synthesis = add_record(
            self.root,
            kind="SYN",
            title="settlement discriminator",
            statement="execute the revised settlement test",
            parents=[investigation["id"], fact["id"]],
            scope=[scope["id"]],
            data={
                "investigation_id": investigation["id"],
                "inputs": [fact["id"]],
                "grounded_delta": "the callback reaches the disputed state",
                "revised_attempt": "execute settlement from the callback state",
                "next_discriminator": "measure backing after settlement",
                "follow_through": "pending",
                "cost": "low",
            },
        )
        experiment = add_record(
            self.root,
            kind="EXP",
            title="settlement run",
            statement="run the settlement discriminator",
            status="closed",
            parents=[investigation["id"], synthesis["id"]],
            scope=[scope["id"]],
        )
        executed_data = dict(synthesis["data"])
        executed_data.update({
            "follow_through": "executed",
            "result_experiment_id": experiment["id"],
            "outcome": "settlement preserved the measured discrepancy",
        })
        with self.assertRaisesRegex(ValidationError, "observed executed run"):
            update_record(
                self.root,
                synthesis["id"],
                expected_revision=synthesis["revision"],
                changes={"status": "closed", "data": executed_data},
                reason="must not claim an unperformed experiment",
            )

        self._sealed_run(
            "RUN-0001",
            plan={
                "ledger_investigation_id": investigation["id"],
                "ledger_experiment_id": experiment["id"],
            },
        )
        linked = link_runtime_ref(
            self.root,
            experiment["id"],
            "runs/RUN-0001/plan.json",
            expected_kind="EXP",
            reason="link executed discriminator",
            status="active",
        )
        linked = link_runtime_ref(
            self.root,
            experiment["id"],
            "runs/RUN-0001/observation.json",
            expected_kind="EXP",
            reason="link observed discriminator",
            status="closed",
        )
        closed = update_record(
            self.root,
            synthesis["id"],
            expected_revision=synthesis["revision"],
            changes={"status": "closed", "data": executed_data},
            reason="sealed execution completed the discriminator",
        )
        self.assertEqual(closed["data"]["follow_through"], "executed")
        self.assertEqual(linked["status"], "closed")

    def test_synthesis_artifact_route_requires_immutable_derivation(self) -> None:
        scope = add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="authorized target",
            status="active",
            data={"impacts": ["direct theft"]},
        )
        investigation = add_record(
            self.root,
            kind="INV",
            title="source contradiction",
            statement="a writer may be unreachable",
            status="closed",
            stage="closed",
            scope=[scope["id"]],
        )
        fact = add_record(self.root, kind="FACT", title="writer", statement="writer inventory", status="closed")
        proof = Path(self.temporary.name) / "writer-proof.json"
        proof.write_text(json.dumps({"writer": "none", "reason": "all call paths are privileged"}), encoding="utf-8")
        artifact = ingest_artifact(
            self.root,
            proof,
            media_type="application/json",
            role="source-discriminator",
            producer="test",
        )
        base_data = {
            "investigation_id": investigation["id"],
            "inputs": [fact["id"]],
            "grounded_delta": "the complete writer inventory excludes public callers",
            "revised_attempt": "derive reachability from the complete call graph",
            "next_discriminator": "check every external path to the writer",
            "follow_through": "refuted",
            "result_artifact": artifact["id"],
            "outcome": "no attacker-reachable writer exists",
        }
        with self.assertRaisesRegex(ValidationError, "mechanically checkable derivation"):
            add_record(
                self.root,
                kind="SYN",
                title="unexplained artifact",
                statement="artifact without derivation",
                status="closed",
                parents=[investigation["id"], fact["id"]],
                data=base_data,
            )
        base_data["result_derivation"] = "enumerate every writer node and prove each incoming path requires an unavailable role"
        synthesis = add_record(
            self.root,
            kind="SYN",
            title="source refutation",
            statement="content-addressed writer reachability refutation",
            status="closed",
            parents=[investigation["id"], fact["id"]],
            data=base_data,
        )
        self.assertEqual(synthesis["data"]["result_artifact"], artifact["id"])

    def test_recon_coverage_attestation_is_required_and_source_bound(self) -> None:
        before = assess_completion(self.root)
        self.assertTrue(any(item["gate"] == "RECON-COVERAGE" for item in before["blockers"]))
        recorded = self._bind_empty_recon_coverage()
        verified = verify_coverage_gate(self.root)
        self.assertTrue(verified["valid"])
        self.assertEqual(verified["id"], recorded["id"])
        extra = self.source / "NewInScope.sol"
        extra.write_text("contract NewInScope {}\n", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            verify_coverage_gate(self.root)
        extra.unlink()
        (self.source / "Target.sol").write_text("contract Target { uint changed; }\n", encoding="utf-8")
        with self.assertRaises(IntegrityError):
            verify_coverage_gate(self.root)
        after = assess_completion(self.root)
        self.assertTrue(any(
            item["gate"] == "RECON-COVERAGE" and "source hashes do not match" in item["reason"]
            for item in after["blockers"]
        ))

    def test_recon_rejects_scan_from_older_source_bytes(self) -> None:
        base = Path(self.temporary.name) / "stale-recon-inputs"
        base.mkdir()
        scan = base / "entry-points.json"
        coverage = base / "coverage-map.json"
        old_hash = hashlib.sha256((self.source / "Target.sol").read_bytes()).hexdigest()
        scan.write_text(json.dumps({
            "schema_version": 2,
            "path_basis": "root-relative",
            "scope_mode": "paths",
            "scope_inputs": ["."],
            "files": ["Target.sol"],
            "source_inventory": [{"path": "Target.sol", "sha256": old_hash}],
            "entry_points": [],
            "read_surfaces": [],
            "problems": [],
        }), encoding="utf-8")
        coverage.write_text(json.dumps({
            "schema_version": 1,
            "files": [{"path": "Target.sol", "status": "analyzed", "evidence": ["old scan"]}],
            "entry_points": [],
            "read_surfaces": [],
        }), encoding="utf-8")
        (self.source / "Target.sol").write_text(
            "contract Target { uint256 public price; function poke() external { price += 1; } }\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(IntegrityError, "source hashes do not match"):
            record_coverage_gate(self.root, entry_points_path=scan, coverage_map_path=coverage)

    def test_public_cli_has_no_lane_or_external_review_commands(self) -> None:
        parser = build_parser()
        command_action = next(action for action in parser._actions if getattr(action, "dest", None) == "command_name")
        self.assertNotIn("scale", command_action.choices)
        self.assertNotIn("rsa", command_action.choices)
        controller = command_action.choices["controller"]
        controller_action = next(action for action in controller._actions if getattr(action, "dest", None) == "controller_command")
        self.assertNotIn("bootstrap", controller_action.choices)
        self.assertNotIn("expand", controller_action.choices)
        review = command_action.choices["review"]
        review_action = next(action for action in review._actions if getattr(action, "dest", None) == "review_command")
        self.assertNotIn("execute-blind", review_action.choices)
        self.assertIn("complete-in-session", review_action.choices)

    def test_completion_has_no_population_gates(self) -> None:
        add_record(
            self.root,
            kind="SCOPE",
            title="program",
            statement="authorized target and exact impacts",
            status="active",
            priority="critical",
            data={"impacts": ["direct theft"], "cost": "low"},
        )
        result = assess_completion(self.root)
        gates = {item["gate"] for item in result["blockers"]}
        self.assertFalse({"TTS-BOOTSTRAP", "TTS-AGGREGATE", "TTS-HANDOFF", "TTS-ADAPTIVE", "RSA", "IMPACT-EXTENSION"} & gates)

    def test_visible_subagent_review_is_bound_to_a_ledger_task(self) -> None:
        replay = self._sealed_replay("REPLAY-0001", "RUN-0001")
        candidate = {
            "id": "CAND-0001",
            "replay_id": replay["id"],
            "property": "claims remain backed",
            "support_run": "RUN-0001",
            "control_run": "RUN-0002",
            "fidelity": {"implementation_verified": True},
        }
        (self.root / "candidates" / "CAND-0001.json").write_text(json.dumps(candidate), encoding="utf-8")
        prepared = prepare_blind_review(self.root, "CAND-0001")
        task = query_ledger(self.root, kind="TASK")[0]
        self.assertEqual(prepared["ledger_task_id"], task["id"])
        result_path = self.root / prepared["submission_path"]
        result_path.write_text(json.dumps({
            "review_id": prepared["id"],
            "candidate_id": "CAND-0001",
            "packet_sha256": prepared["packet_sha256"],
            "challenge_nonce": prepared["challenge_nonce"],
            "subagent_thread": "independent_reviewer",
            "verdict": "confirmed",
            "reproduced": True,
            "challenges": ["causality checked"],
            "reproduction_commands": ["a1x replay verify ..."],
            "artifact_refs": ["replays/REPLAY-0001.json"],
        }), encoding="utf-8")
        with self.assertRaises(ValidationError):
            record_in_session_review(self.root, prepared["id"], subagent_thread="independent_reviewer", result_path=result_path)
        completed = record_in_session_review(
            self.root,
            prepared["id"],
            subagent_thread="independent_reviewer",
            result_path=result_path,
            attest_visible_subagent=True,
        )
        self.assertTrue(completed["visible_in_session"])
        self.assertIn("runtime-does-not-authenticate", completed["identity_assurance"])
        self.assertTrue(qualifies(self.root, prepared["id"], "CAND-0001"))
        closed_task = query_ledger(self.root, kind="TASK")[0]
        self.assertEqual(closed_task["owner"], "subagent:independent_reviewer")
        output_path = self.root / "reviews" / prepared["id"] / "review-output.json"
        tampered = json.loads(output_path.read_text(encoding="utf-8"))
        tampered["challenges"] = ["tampered after qualification"]
        write_json_atomic(output_path, tampered)
        self.assertFalse(qualifies(self.root, prepared["id"], "CAND-0001"))


if __name__ == "__main__":
    unittest.main()
