from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from a1x_runtime.campaign import add_hypothesis, add_obligation, init_campaign, migrate_campaign
from a1x_runtime.blind_review import prepare_blind_review, qualifies, record_in_session_review
from a1x_runtime.candidates import create_candidate
from a1x_runtime.cli import build_parser
from a1x_runtime.controller import assess_completion
from a1x_runtime.errors import IntegrityError, ValidationError
from a1x_runtime.ledger import add_record, link_runtime_ref, migrate_v4, query_ledger, update_record, verify_ledger
from a1x_runtime.process import reject_model_argv


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
            parents=[task["id"]],
            data={"revised_attempt": "replay the callback at the exact bound and then settle", "next_discriminator": "compare post-settlement backing against the one-shot control"},
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
        self.assertEqual(result["campaign"]["runtime_version"], "5.0.0")
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
        run_dir = self.root / "runs" / "RUN-0001"
        run_dir.mkdir()
        (run_dir / "plan.json").write_text(json.dumps({
            "ledger_investigation_id": investigation["id"],
            "ledger_experiment_id": experiment["id"],
        }), encoding="utf-8")
        (run_dir / "receipt.json").write_text(json.dumps({"mechanical_success": True}), encoding="utf-8")
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
        replay = {"id": "REPLAY-0001", "run_id": "RUN-0001", "passed": True}
        candidate = {
            "id": "CAND-0001",
            "replay_id": replay["id"],
            "property": "claims remain backed",
            "support_run": "RUN-0001",
            "control_run": "RUN-0002",
            "fidelity": {"implementation_verified": True},
        }
        (self.root / "replays" / "REPLAY-0001.json").write_text(json.dumps(replay), encoding="utf-8")
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


if __name__ == "__main__":
    unittest.main()
