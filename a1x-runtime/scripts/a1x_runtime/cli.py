from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable

from . import __version__
from .adapters import capability_matrix, probe_target
from .artifacts import ingest_artifact, materialize_artifact, verify_artifact
from .actor_programs import create_actor_program, record_actor_execution, verify_actor_execution
from .blind_review import prepare_blind_review, record_in_session_review
from .campaign import add_hypothesis, add_obligation, doctor, init_campaign, migrate_campaign, save_doctor, show_campaign
from .candidates import add_review, check_gates, create_candidate, promote_validated
from .controller import (
    add_frontier,
    add_impact,
    assess_completion,
    close_campaign,
    record_coverage,
    resolve_frontier,
    resolve_impact,
)
from .continuity import create_continuation_contract, record_continuation_attempt, verify_continuation_contract
from .composition import compose_components, create_component_contract, verify_composition
from .errors import A1XError
from .evidence_bundles import create_bundle, load_bundle, verify_bundle
from .explorer import retrieve_verified_contract, show_retrieval
from .forks import fork_status, revert_fork, snapshot_fork, start_fork, stop_fork
from .harness_coverage import create_expansion_task, create_harness_model, record_harness_telemetry, resolve_expansion_task, verify_harness_model
from .ledger import add_record, brief as ledger_brief, migrate_v4 as migrate_v4_ledger, query_ledger, show_record, update_record, verify_ledger
from .replay import prepare_replay, verify_replay
from .operations import propose_operation, recommend_next, transition_operation
from .mcp_server import serve_stdio
from .prestate import serve_http_bridge, serve_proxy
from .prerequisite_graph import create_backtrack_branch, create_prerequisite_graph, resolve_backtrack_branch, verify_prerequisite_graph
from .recon import active_recon, create_recon_pack
from .research_progress import record_progress, verify_progress
from .records import verify_event_chain
from .runs import execute_run, observe_run, plan_run
from .security_oracles import create_security_oracle, evaluate_security_oracle, standard_oracle_profile, verify_oracle_evaluation
from .solver_adapters import create_solver_job, probe_solver_tools, register_external_solver_job, validate_solver_job, verify_solver_job
from .surface_graph import build_surface_graph
from .trace_facts import analyze_run_trace


def _root(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _json(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False))


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _tri_bool(value: str) -> bool | None:
    table = {"yes": True, "no": False, "unknown": None}
    return table[value]


def _budget_dict(args: argparse.Namespace) -> dict[str, int]:
    return {
        "max_runs": args.max_runs,
        "default_run_timeout_seconds": args.default_run_timeout,
        "default_output_bytes": args.default_output_bytes,
    }


def _metrics(values: list[str]) -> list[dict[str, str]]:
    metrics = []
    for value in values:
        if "=" not in value or ":" not in value.split("=", 1)[1]:
            raise A1XError("--metric must use name=value:unit")
        name, remainder = value.split("=", 1)
        amount, unit = remainder.rsplit(":", 1)
        if not name.strip() or not unit.strip():
            raise A1XError("--metric requires non-empty name and unit")
        try:
            Decimal(amount)
        except InvalidOperation as exc:
            raise A1XError(f"metric value is not an exact decimal: {amount}") from exc
        metrics.append({"name": name.strip(), "value": amount, "unit": unit.strip()})
    return metrics


def _evidence_refs(values: list[str]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for value in values:
        try:
            item = json.loads(value)
        except json.JSONDecodeError as exc:
            raise A1XError(f"--evidence-ref must be a JSON object: {exc}") from exc
        if not isinstance(item, dict):
            raise A1XError("--evidence-ref must decode to a JSON object")
        refs.append(item)
    return refs


def _cmd_campaign_init(args: argparse.Namespace) -> Any:
    campaign = init_campaign(
        args.root,
        label=args.label,
        source=args.source,
        target=args.target,
        chain_id=args.chain_id,
        block_number=args.block,
        block_hash=args.block_hash,
        rpc_env=args.rpc_env,
        authorization=args.authorization,
        budgets=_budget_dict(args),
    )
    return {"campaign": campaign, "ledger": verify_ledger(args.root, repair_views=True)}


def _parse_json_object(value: str, field: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise A1XError(f"{field} must be a JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise A1XError(f"{field} must be a JSON object")
    return parsed


def _cmd_ledger_add(args: argparse.Namespace) -> Any:
    return add_record(
        args.root,
        kind=args.kind,
        title=args.title,
        statement=args.statement,
        status=args.status,
        priority=args.priority,
        stage=args.stage,
        parents=args.parent,
        scope=args.scope,
        evidence=args.evidence,
        artifacts=args.artifact,
        next_action=args.next_action,
        owner=args.owner,
        data=_parse_json_object(args.data, "--data"),
    )


def _cmd_ledger_update(args: argparse.Namespace) -> Any:
    return update_record(
        args.root,
        args.id,
        expected_revision=args.expected_revision,
        changes=_parse_json_object(args.changes, "--changes"),
        reason=args.reason,
    )


def _cmd_run_plan(args: argparse.Namespace) -> Any:
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise A1XError("run plan requires a command after --")
    return plan_run(
        args.root,
        hypothesis_id=args.hypothesis,
        run_class=args.run_class,
        cwd=args.cwd,
        argv=command,
        timeout_seconds=args.timeout,
        max_output_bytes=args.max_output_bytes,
        inputs=args.input,
        property_statement=args.property,
        support_prediction=args.support_prediction,
        refute_prediction=args.refute_prediction,
        success_regex=args.success_regex,
        pass_env=args.pass_env,
        inherit_env=args.inherit_env,
        fork_id=args.fork,
        control_for_run=args.control_for,
        control_change_indices=args.control_change,
        control_claim=args.control_claim,
        extends_candidate_id=args.extends_candidate,
        extends_run=args.extends_run,
        extension_prefix=args.extension_prefix,
        ledger_experiment_id=args.ledger,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="a1x", description="Deterministic execution and evidence runtime for A1X skills")
    parser.add_argument("--version", action="version", version=f"a1x {__version__}")
    commands = parser.add_subparsers(dest="command_name", required=True)

    doctor_parser = commands.add_parser("doctor", help="detect expected and optional local tools without reading secrets")
    doctor_parser.add_argument("--root", type=_root, help="also save the version inventory in an existing campaign")
    doctor_parser.set_defaults(handler=lambda a: save_doctor(a.root) if a.root else doctor())

    campaign = commands.add_parser("campaign", help="create or inspect a durable campaign")
    campaign_sub = campaign.add_subparsers(dest="campaign_command", required=True)
    campaign_init = campaign_sub.add_parser("init")
    campaign_init.add_argument("--root", required=True, type=_root)
    campaign_init.add_argument("--label", required=True)
    campaign_init.add_argument("--source", required=True, type=_root)
    campaign_init.add_argument("--target", required=True)
    campaign_init.add_argument("--chain-id", type=int)
    campaign_init.add_argument("--block", type=int)
    campaign_init.add_argument("--block-hash", help="expected 0x-prefixed 32-byte hash for the pinned block")
    campaign_init.add_argument("--rpc-env")
    campaign_init.add_argument("--authorization", required=True)
    campaign_init.add_argument("--max-runs", type=int, default=500)
    campaign_init.add_argument("--default-run-timeout", type=int, default=1800)
    campaign_init.add_argument("--default-output-bytes", type=int, default=64 * 1024 * 1024)
    campaign_init.set_defaults(handler=_cmd_campaign_init)
    campaign_show = campaign_sub.add_parser("show")
    campaign_show.add_argument("--root", required=True, type=_root)
    campaign_show.set_defaults(handler=lambda a: show_campaign(a.root))
    campaign_migrate = campaign_sub.add_parser("migrate", help="explicitly migrate v3 metadata while preserving legacy artifacts")
    campaign_migrate.add_argument("--root", required=True, type=_root)
    campaign_migrate.set_defaults(handler=lambda a: migrate_campaign(a.root))
    campaign_verify = campaign_sub.add_parser("verify-events")
    campaign_verify.add_argument("--root", required=True, type=_root)
    campaign_verify.set_defaults(handler=lambda a: verify_event_chain(a.root))

    ledger = commands.add_parser("ledger", help="operate the compact single-session hunt ledger")
    ledger_sub = ledger.add_subparsers(dest="ledger_command", required=True)
    ledger_add = ledger_sub.add_parser("add")
    ledger_add.add_argument("--root", required=True, type=_root)
    ledger_add.add_argument("--kind", required=True, choices=["SCOPE", "OBL", "INV", "EXP", "FACT", "TASK", "SYN"])
    ledger_add.add_argument("--title", required=True)
    ledger_add.add_argument("--statement", required=True)
    ledger_add.add_argument("--status", default="open", choices=["open", "active", "blocked", "closed", "validated", "refuted", "out-of-scope", "not-applicable"])
    ledger_add.add_argument("--priority", default="medium", choices=["low", "medium", "high", "critical"])
    ledger_add.add_argument("--stage", choices=["lead", "hypothesis", "candidate", "validated", "refuted", "closed"])
    ledger_add.add_argument("--parent", action="append", default=[])
    ledger_add.add_argument("--scope", action="append", default=[])
    ledger_add.add_argument("--evidence", action="append", default=[])
    ledger_add.add_argument("--artifact", action="append", default=[])
    ledger_add.add_argument("--next-action", default="")
    ledger_add.add_argument("--owner", default="primary")
    ledger_add.add_argument("--data", default="{}", help="kind-specific JSON object")
    ledger_add.set_defaults(handler=_cmd_ledger_add)
    ledger_update = ledger_sub.add_parser("update")
    ledger_update.add_argument("--root", required=True, type=_root)
    ledger_update.add_argument("--id", required=True)
    ledger_update.add_argument("--expected-revision", required=True, type=int)
    ledger_update.add_argument("--changes", required=True, help="JSON object containing fields to change")
    ledger_update.add_argument("--reason", required=True)
    ledger_update.set_defaults(handler=_cmd_ledger_update)
    ledger_list = ledger_sub.add_parser("list")
    ledger_list.add_argument("--root", required=True, type=_root)
    ledger_list.add_argument("--kind", choices=["SCOPE", "OBL", "INV", "EXP", "FACT", "TASK", "SYN"])
    ledger_list.add_argument("--status")
    ledger_list.add_argument("--priority")
    ledger_list.add_argument("--scope")
    ledger_list.set_defaults(handler=lambda a: query_ledger(a.root, kind=a.kind, status=a.status, priority=a.priority, scope_id=a.scope))
    ledger_show = ledger_sub.add_parser("show")
    ledger_show.add_argument("--root", required=True, type=_root)
    ledger_show.add_argument("--id", required=True)
    ledger_show.set_defaults(handler=lambda a: show_record(a.root, a.id))
    ledger_verify = ledger_sub.add_parser("verify")
    ledger_verify.add_argument("--root", required=True, type=_root)
    ledger_verify.add_argument("--repair-views", action="store_true")
    ledger_verify.set_defaults(handler=lambda a: verify_ledger(a.root, repair_views=a.repair_views))
    ledger_brief_parser = ledger_sub.add_parser("brief")
    ledger_brief_parser.add_argument("--root", required=True, type=_root)
    ledger_brief_parser.set_defaults(handler=lambda a: ledger_brief(a.root))
    ledger_migrate = ledger_sub.add_parser("migrate-v4")
    ledger_migrate.add_argument("--root", required=True, type=_root)
    ledger_migrate.add_argument("--apply", action="store_true")
    ledger_migrate.set_defaults(handler=lambda a: migrate_v4_ledger(a.root, apply=a.apply))

    artifact = commands.add_parser("artifact", help="manage immutable content-addressed evidence")
    artifact_sub = artifact.add_subparsers(dest="artifact_command", required=True)
    artifact_add = artifact_sub.add_parser("add")
    artifact_add.add_argument("--root", required=True, type=_root)
    artifact_add.add_argument("--file", required=True, type=_root)
    artifact_add.add_argument("--media-type", required=True)
    artifact_add.add_argument("--role", required=True)
    artifact_add.add_argument("--producer", required=True)
    artifact_add.set_defaults(handler=lambda a: ingest_artifact(a.root, a.file, media_type=a.media_type, role=a.role, producer=a.producer))
    artifact_verify = artifact_sub.add_parser("verify")
    artifact_verify.add_argument("--root", required=True, type=_root)
    artifact_verify.add_argument("--artifact", required=True)
    artifact_verify.set_defaults(handler=lambda a: verify_artifact(a.root, a.artifact))
    artifact_materialize = artifact_sub.add_parser("materialize")
    artifact_materialize.add_argument("--root", required=True, type=_root)
    artifact_materialize.add_argument("--artifact", required=True)
    artifact_materialize.add_argument("--destination", required=True, type=_root)
    artifact_materialize.set_defaults(handler=lambda a: materialize_artifact(a.root, a.artifact, a.destination))

    evidence = commands.add_parser("evidence", help="create and verify typed EvidenceBundles")
    evidence_sub = evidence.add_subparsers(dest="evidence_command", required=True)
    evidence_add = evidence_sub.add_parser("add")
    evidence_add.add_argument("--root", required=True, type=_root)
    evidence_add.add_argument("--json", required=True, type=_root)
    evidence_add.set_defaults(handler=lambda a: create_bundle(a.root, _load_json(a.json)))
    evidence_show = evidence_sub.add_parser("show")
    evidence_show.add_argument("--root", required=True, type=_root)
    evidence_show.add_argument("--evidence", required=True)
    evidence_show.set_defaults(handler=lambda a: load_bundle(a.root, a.evidence))
    evidence_verify = evidence_sub.add_parser("verify")
    evidence_verify.add_argument("--root", required=True, type=_root)
    evidence_verify.add_argument("--evidence", required=True)
    evidence_verify.set_defaults(handler=lambda a: verify_bundle(a.root, a.evidence))


    continuation = commands.add_parser("continuation", help="manage executable parent-to-child continuation contracts")
    continuation_sub = continuation.add_subparsers(dest="continuation_command", required=True)
    continuation_create = continuation_sub.add_parser("create")
    continuation_create.add_argument("--root", required=True, type=_root)
    continuation_create.add_argument("--json", required=True, type=_root)
    continuation_create.set_defaults(handler=lambda a: create_continuation_contract(a.root, _load_json(a.json)))
    continuation_verify = continuation_sub.add_parser("verify")
    continuation_verify.add_argument("--root", required=True, type=_root)
    continuation_verify.add_argument("--continuation", required=True)
    continuation_verify.set_defaults(handler=lambda a: verify_continuation_contract(a.root, a.continuation))
    continuation_attempt = continuation_sub.add_parser("attempt")
    continuation_attempt.add_argument("--root", required=True, type=_root)
    continuation_attempt.add_argument("--continuation", required=True)
    continuation_attempt.add_argument("--json", required=True, type=_root)
    continuation_attempt.set_defaults(handler=lambda a: record_continuation_attempt(a.root, a.continuation, _load_json(a.json)))

    trace = commands.add_parser("trace", help="extract deterministic facts from EVM traces")
    trace_sub = trace.add_subparsers(dest="trace_command", required=True)
    trace_analyze = trace_sub.add_parser("analyze")
    trace_analyze.add_argument("--root", required=True, type=_root)
    trace_analyze.add_argument("--run", required=True)
    trace_analyze.add_argument("--path", required=True)
    trace_analyze.add_argument("--metrics", type=_root)
    trace_analyze.set_defaults(handler=lambda a: analyze_run_trace(a.root, run_id=a.run, path=a.path, declared_metrics=_load_json(a.metrics) if a.metrics else []))

    surface = commands.add_parser("surface", help="build a bounded cross-contract and pinned-fork graph")
    surface_sub = surface.add_subparsers(dest="surface_command", required=True)
    surface_build = surface_sub.add_parser("build")
    surface_build.add_argument("--root", required=True, type=_root)
    surface_build.add_argument("--json", required=True, type=_root)
    surface_build.set_defaults(handler=lambda a: build_surface_graph(a.root, _load_json(a.json)))

    oracle = commands.add_parser("oracle", help="define and evaluate protocol security properties")
    oracle_sub = oracle.add_subparsers(dest="oracle_command", required=True)
    oracle_profile = oracle_sub.add_parser("profile")
    oracle_profile.add_argument("--name", required=True)
    oracle_profile.set_defaults(handler=lambda a: standard_oracle_profile(a.name))
    oracle_create = oracle_sub.add_parser("create")
    oracle_create.add_argument("--root", required=True, type=_root)
    oracle_create.add_argument("--json", required=True, type=_root)
    oracle_create.set_defaults(handler=lambda a: create_security_oracle(a.root, _load_json(a.json)))
    oracle_evaluate = oracle_sub.add_parser("evaluate")
    oracle_evaluate.add_argument("--root", required=True, type=_root)
    oracle_evaluate.add_argument("--oracle", required=True)
    oracle_evaluate.add_argument("--run", required=True)
    oracle_evaluate.add_argument("--control-run")
    oracle_evaluate.add_argument("--observations", required=True, type=_root)
    oracle_evaluate.add_argument("--evidence-ref", action="append", default=[])
    oracle_evaluate.set_defaults(handler=lambda a: evaluate_security_oracle(a.root, oracle_id=a.oracle, run_id=a.run, control_run=a.control_run, observations=_load_json(a.observations), evidence_refs=_evidence_refs(a.evidence_ref)))
    oracle_verify = oracle_sub.add_parser("verify")
    oracle_verify.add_argument("--root", required=True, type=_root)
    oracle_verify.add_argument("--evaluation", required=True)
    oracle_verify.set_defaults(handler=lambda a: verify_oracle_evaluation(a.root, a.evaluation))

    prerequisite = commands.add_parser("prerequisite", help="manage executable prerequisite graphs and backtracking")
    prerequisite_sub = prerequisite.add_subparsers(dest="prerequisite_command", required=True)
    prerequisite_create = prerequisite_sub.add_parser("create")
    prerequisite_create.add_argument("--root", required=True, type=_root)
    prerequisite_create.add_argument("--json", required=True, type=_root)
    prerequisite_create.set_defaults(handler=lambda a: create_prerequisite_graph(a.root, _load_json(a.json)))
    prerequisite_verify = prerequisite_sub.add_parser("verify")
    prerequisite_verify.add_argument("--root", required=True, type=_root)
    prerequisite_verify.add_argument("--graph", required=True)
    prerequisite_verify.set_defaults(handler=lambda a: verify_prerequisite_graph(a.root, a.graph))
    prerequisite_backtrack = prerequisite_sub.add_parser("backtrack")
    prerequisite_backtrack.add_argument("--root", required=True, type=_root)
    prerequisite_backtrack.add_argument("--graph", required=True)
    prerequisite_backtrack.add_argument("--json", required=True, type=_root)
    prerequisite_backtrack.set_defaults(handler=lambda a: create_backtrack_branch(a.root, a.graph, _load_json(a.json)))
    prerequisite_resolve = prerequisite_sub.add_parser("resolve-backtrack")
    prerequisite_resolve.add_argument("--root", required=True, type=_root)
    prerequisite_resolve.add_argument("--branch", required=True)
    prerequisite_resolve.add_argument("--attempt", required=True)
    prerequisite_resolve.set_defaults(handler=lambda a: resolve_backtrack_branch(a.root, a.branch, attempt_id=a.attempt))

    component = commands.add_parser("component", help="define and execute sequential, nested, and temporal attack composition")
    component_sub = component.add_subparsers(dest="component_command", required=True)
    component_create = component_sub.add_parser("create")
    component_create.add_argument("--root", required=True, type=_root)
    component_create.add_argument("--json", required=True, type=_root)
    component_create.set_defaults(handler=lambda a: create_component_contract(a.root, _load_json(a.json)))
    component_compose = component_sub.add_parser("compose")
    component_compose.add_argument("--root", required=True, type=_root)
    component_compose.add_argument("--json", required=True, type=_root)
    component_compose.set_defaults(handler=lambda a: compose_components(a.root, _load_json(a.json)))
    component_verify = component_sub.add_parser("verify")
    component_verify.add_argument("--root", required=True, type=_root)
    component_verify.add_argument("--composition", required=True)
    component_verify.set_defaults(handler=lambda a: verify_composition(a.root, a.composition))

    actors = commands.add_parser("actors", help="define and replay multi-actor adversarial programs")
    actors_sub = actors.add_subparsers(dest="actors_command", required=True)
    actors_create = actors_sub.add_parser("create")
    actors_create.add_argument("--root", required=True, type=_root)
    actors_create.add_argument("--json", required=True, type=_root)
    actors_create.set_defaults(handler=lambda a: create_actor_program(a.root, _load_json(a.json)))
    actors_execute = actors_sub.add_parser("execute")
    actors_execute.add_argument("--root", required=True, type=_root)
    actors_execute.add_argument("--program", required=True)
    actors_execute.add_argument("--run", required=True)
    actors_execute.add_argument("--replay", required=True)
    actors_execute.add_argument("--steps", required=True, type=_root)
    actors_execute.add_argument("--evidence-ref", action="append", default=[])
    actors_execute.set_defaults(handler=lambda a: record_actor_execution(a.root, actor_program_id=a.program, run_id=a.run, replay_id=a.replay, observed_steps=_load_json(a.steps), evidence_refs=_evidence_refs(a.evidence_ref)))
    actors_verify = actors_sub.add_parser("verify")
    actors_verify.add_argument("--root", required=True, type=_root)
    actors_verify.add_argument("--execution", required=True)
    actors_verify.set_defaults(handler=lambda a: verify_actor_execution(a.root, a.execution))

    solver = commands.add_parser("solver", help="run bounded exact/Z3 search and register verified specialist jobs")
    solver_sub = solver.add_subparsers(dest="solver_command", required=True)
    solver_probe = solver_sub.add_parser("probe")
    solver_probe.set_defaults(handler=lambda a: probe_solver_tools())
    solver_create = solver_sub.add_parser("create")
    solver_create.add_argument("--root", required=True, type=_root)
    solver_create.add_argument("--backend", choices=["python-exact", "z3-python"], required=True)
    solver_create.add_argument("--json", required=True, type=_root)
    solver_create.set_defaults(handler=lambda a: create_solver_job(a.root, _load_json(a.json), backend=a.backend))
    solver_register = solver_sub.add_parser("register-external")
    solver_register.add_argument("--root", required=True, type=_root)
    solver_register.add_argument("--backend", required=True)
    solver_register.add_argument("--run", required=True)
    solver_register.add_argument("--evidence-ref", action="append", default=[])
    solver_register.set_defaults(handler=lambda a: register_external_solver_job(a.root, backend=a.backend, run_id=a.run, witness_refs=_evidence_refs(a.evidence_ref)))
    solver_validate = solver_sub.add_parser("validate")
    solver_validate.add_argument("--root", required=True, type=_root)
    solver_validate.add_argument("--solver-job", required=True)
    solver_validate.add_argument("--run", required=True)
    solver_validate.add_argument("--replay", required=True)
    solver_validate.set_defaults(handler=lambda a: validate_solver_job(a.root, solver_job_id=a.solver_job, run_id=a.run, replay_id=a.replay))
    solver_verify = solver_sub.add_parser("verify")
    solver_verify.add_argument("--root", required=True, type=_root)
    solver_verify.add_argument("--solver-job", required=True)
    solver_verify.set_defaults(handler=lambda a: verify_solver_job(a.root, a.solver_job))

    progress = commands.add_parser("progress", help="record evidence-bound witness and information progress")
    progress_sub = progress.add_subparsers(dest="progress_command", required=True)
    progress_record = progress_sub.add_parser("record")
    progress_record.add_argument("--root", required=True, type=_root)
    progress_record.add_argument("--json", required=True, type=_root)
    progress_record.set_defaults(handler=lambda a: record_progress(a.root, _load_json(a.json)))
    progress_verify = progress_sub.add_parser("verify")
    progress_verify.add_argument("--root", required=True, type=_root)
    progress_verify.add_argument("--progress", required=True)
    progress_verify.set_defaults(handler=lambda a: verify_progress(a.root, a.progress))

    harness = commands.add_parser("harness", help="measure protocol-surface representation and bounded harness expansion")
    harness_sub = harness.add_subparsers(dest="harness_command", required=True)
    harness_create = harness_sub.add_parser("create")
    harness_create.add_argument("--root", required=True, type=_root)
    harness_create.add_argument("--json", required=True, type=_root)
    harness_create.set_defaults(handler=lambda a: create_harness_model(a.root, _load_json(a.json)))
    harness_task = harness_sub.add_parser("expand")
    harness_task.add_argument("--root", required=True, type=_root)
    harness_task.add_argument("--harness", required=True)
    harness_task.add_argument("--item", required=True)
    harness_task.add_argument("--reason", required=True)
    harness_task.add_argument("--experiment", required=True)
    harness_task.add_argument("--maximum-executions", type=int, required=True)
    harness_task.set_defaults(handler=lambda a: create_expansion_task(a.root, harness_id=a.harness, item_id=a.item, reason=a.reason, experiment=a.experiment, maximum_executions=a.maximum_executions))
    harness_telemetry = harness_sub.add_parser("telemetry")
    harness_telemetry.add_argument("--root", required=True, type=_root)
    harness_telemetry.add_argument("--harness", required=True)
    harness_telemetry.add_argument("--run", required=True)
    harness_telemetry.add_argument("--replay", required=True)
    harness_telemetry.add_argument("--action-stats", required=True, type=_root)
    harness_telemetry.add_argument("--state-fingerprint", action="append", default=[])
    harness_telemetry.add_argument("--evidence-ref", action="append", default=[])
    harness_telemetry.set_defaults(handler=lambda a: record_harness_telemetry(a.root, harness_id=a.harness, run_id=a.run, replay_id=a.replay, action_stats=_load_json(a.action_stats), state_fingerprints=a.state_fingerprint, evidence_refs=_evidence_refs(a.evidence_ref)))
    harness_resolve = harness_sub.add_parser("resolve")
    harness_resolve.add_argument("--root", required=True, type=_root)
    harness_resolve.add_argument("--task", required=True)
    harness_resolve.add_argument("--status", choices=["executed", "refuted", "blocked"], required=True)
    harness_resolve.add_argument("--resolution", required=True)
    harness_resolve.add_argument("--run")
    harness_resolve.add_argument("--replay")
    harness_resolve.add_argument("--evidence-ref", action="append", default=[])
    harness_resolve.set_defaults(handler=lambda a: resolve_expansion_task(a.root, task_id=a.task, status=a.status, resolution=a.resolution, run_id=a.run, replay_id=a.replay, evidence_refs=_evidence_refs(a.evidence_ref)))
    harness_verify = harness_sub.add_parser("verify")
    harness_verify.add_argument("--root", required=True, type=_root)
    harness_verify.add_argument("--harness", required=True)
    harness_verify.set_defaults(handler=lambda a: verify_harness_model(a.root, a.harness))


    recon = commands.add_parser("recon", help="manage immutable versioned Recon Packs")
    recon_sub = recon.add_subparsers(dest="recon_command", required=True)
    recon_create = recon_sub.add_parser("create")
    recon_create.add_argument("--root", required=True, type=_root)
    recon_create.add_argument("--facts", required=True, type=_root)
    recon_create.add_argument("--unknowns", required=True, type=_root)
    recon_create.add_argument("--artifact", action="append", default=[])
    recon_create.add_argument("--parent")
    recon_create.set_defaults(handler=lambda a: create_recon_pack(a.root, facts=_load_json(a.facts), unknowns=_load_json(a.unknowns), artifact_ids=a.artifact, parent=a.parent))
    recon_active = recon_sub.add_parser("active")
    recon_active.add_argument("--root", required=True, type=_root)
    recon_active.set_defaults(handler=lambda a: active_recon(a.root))

    explorer = commands.add_parser("explorer", help="retrieve verified metadata through the host coordinator without exposing API credentials")
    explorer_sub = explorer.add_subparsers(dest="explorer_command", required=True)
    explorer_retrieve = explorer_sub.add_parser("retrieve")
    explorer_retrieve.add_argument("--root", required=True, type=_root)
    explorer_retrieve.add_argument("--address", required=True)
    explorer_retrieve.add_argument("--campaign-epoch", type=int)
    explorer_retrieve.add_argument("--idempotency-key", required=True)
    explorer_retrieve.set_defaults(handler=lambda a: retrieve_verified_contract(
        a.root, address=a.address, api_env="ETHERSCAN_API_KEY",
        campaign_epoch=a.campaign_epoch, idempotency_key=a.idempotency_key,
    ))
    explorer_show = explorer_sub.add_parser("show")
    explorer_show.add_argument("--root", required=True, type=_root)
    explorer_show.add_argument("--retrieval", required=True)
    explorer_show.set_defaults(handler=lambda a: show_retrieval(a.root, a.retrieval))

    capability = commands.add_parser("capability", help="probe backend compatibility for this target")
    capability_sub = capability.add_subparsers(dest="capability_command", required=True)
    capability_probe = capability_sub.add_parser("probe")
    capability_probe.add_argument("--root", required=True, type=_root)
    capability_probe.set_defaults(handler=lambda a: probe_target(a.root))
    capability_show = capability_sub.add_parser("show")
    capability_show.add_argument("--root", required=True, type=_root)
    capability_show.set_defaults(handler=lambda a: capability_matrix(a.root))

    operation = commands.add_parser("operation", help="run sequential propose-execute-observe-update loops")
    operation_sub = operation.add_subparsers(dest="operation_command", required=True)
    operation_propose = operation_sub.add_parser("propose")
    operation_propose.add_argument("--root", required=True, type=_root)
    operation_propose.add_argument("--hypothesis")
    operation_propose.add_argument("--blocker", required=True)
    operation_propose.add_argument("--question", required=True)
    operation_propose.add_argument("--backend", required=True)
    operation_propose.add_argument("--expected-information", required=True)
    operation_propose.add_argument("--idempotency-key", required=True)
    operation_propose.add_argument("--prerequisite", action="append", default=[])
    operation_propose.add_argument("--budget-json", required=True, type=_root)
    operation_propose.set_defaults(handler=lambda a: propose_operation(a.root, hypothesis_id=a.hypothesis, blocker=a.blocker, question=a.question, backend=a.backend, expected_information=a.expected_information, idempotency_key=a.idempotency_key, prerequisites=a.prerequisite, budget=_load_json(a.budget_json)))
    operation_transition = operation_sub.add_parser("transition")
    operation_transition.add_argument("--root", required=True, type=_root)
    operation_transition.add_argument("--operation", required=True)
    operation_transition.add_argument("--status", required=True)
    operation_transition.add_argument("--evidence", action="append", default=[])
    operation_transition.add_argument("--reason", required=True)
    operation_transition.set_defaults(handler=lambda a: transition_operation(a.root, a.operation, status=a.status, evidence_ids=a.evidence, reason=a.reason))
    operation_recommend = operation_sub.add_parser("recommend")
    operation_recommend.add_argument("--root", required=True, type=_root)
    operation_recommend.add_argument("--blocker", required=True)
    operation_recommend.add_argument("--backend", action="append", required=True)
    operation_recommend.set_defaults(handler=lambda a: recommend_next(a.root, blocker=a.blocker, available_backends=a.backend))



    prestate = commands.add_parser("prestate", help="serve pinned read-only RPC through a Unix socket")
    prestate_sub = prestate.add_subparsers(dest="prestate_command", required=True)
    prestate_serve = prestate_sub.add_parser("serve")
    prestate_serve.add_argument("--root", required=True, type=_root)
    prestate_serve.add_argument("--socket", required=True, type=_root)
    prestate_serve.add_argument("--rpc-env")
    prestate_serve.set_defaults(handler=lambda a: serve_proxy(a.root, socket_path=a.socket, rpc_env=a.rpc_env))
    prestate_bridge = prestate_sub.add_parser("bridge")
    prestate_bridge.add_argument("--socket", required=True, type=_root)
    prestate_bridge.add_argument("--host", default="127.0.0.1")
    prestate_bridge.add_argument("--port", type=int, default=8545)
    prestate_bridge.set_defaults(handler=lambda a: serve_http_bridge(a.socket, host=a.host, port=a.port))

    mcp = commands.add_parser("mcp", help="serve the stateless campaign MCP facade")
    mcp_sub = mcp.add_subparsers(dest="mcp_command", required=True)
    mcp_stdio = mcp_sub.add_parser("stdio")
    mcp_stdio.set_defaults(handler=lambda a: serve_stdio())

    obligation = commands.add_parser("obligation", help="record protocol obligations")
    obligation_sub = obligation.add_subparsers(dest="obligation_command", required=True)
    obligation_add = obligation_sub.add_parser("add")
    obligation_add.add_argument("--root", required=True, type=_root)
    obligation_add.add_argument("--ledger", required=True, help="canonical OBL ledger record")
    obligation_add.add_argument("--title", required=True)
    obligation_add.add_argument("--statement", required=True)
    obligation_add.add_argument("--boundary", required=True)
    obligation_add.add_argument("--units", required=True)
    obligation_add.add_argument("--oracle", required=True)
    obligation_add.set_defaults(handler=lambda a: add_obligation(a.root, title=a.title, statement=a.statement, boundary=a.boundary, units=a.units, oracle=a.oracle, ledger_obligation_id=a.ledger))

    hypothesis = commands.add_parser("hypothesis", help="record falsifiable mechanisms")
    hypothesis_sub = hypothesis.add_subparsers(dest="hypothesis_command", required=True)
    hypothesis_add = hypothesis_sub.add_parser("add")
    hypothesis_add.add_argument("--root", required=True, type=_root)
    hypothesis_add.add_argument("--ledger", required=True, help="canonical INV ledger record")
    hypothesis_add.add_argument("--obligation", required=True)
    hypothesis_add.add_argument("--mechanism", required=True)
    hypothesis_add.add_argument("--sequence", required=True)
    hypothesis_add.add_argument("--support-prediction", required=True)
    hypothesis_add.add_argument("--refute-prediction", required=True)
    hypothesis_add.add_argument("--next-action", required=True)
    hypothesis_add.set_defaults(
        handler=lambda a: add_hypothesis(
            a.root,
            obligation_id=a.obligation,
            mechanism=a.mechanism,
            sequence=a.sequence,
            support_prediction=a.support_prediction,
            refute_prediction=a.refute_prediction,
            next_action=a.next_action,
            ledger_investigation_id=a.ledger,
        )
    )

    run = commands.add_parser("run", help="seal, execute, and annotate experiments")
    run_sub = run.add_subparsers(dest="run_command", required=True)
    run_plan_parser = run_sub.add_parser("plan")
    run_plan_parser.add_argument("--root", required=True, type=_root)
    run_plan_parser.add_argument("--ledger", required=True, help="canonical EXP ledger record parented by the hypothesis INV")
    run_plan_parser.add_argument("--hypothesis", required=True)
    run_plan_parser.add_argument("--class", dest="run_class", required=True, choices=["candidate", "control", "repair", "fuzz", "solve", "recon"])
    run_plan_parser.add_argument("--cwd", required=True, type=_root)
    run_plan_parser.add_argument("--timeout", type=int, help="defaults to the campaign budget")
    run_plan_parser.add_argument("--max-output-bytes", type=int, help="defaults to the campaign budget")
    run_plan_parser.add_argument("--input", action="append", default=[], type=_path)
    run_plan_parser.add_argument("--property", required=True)
    run_plan_parser.add_argument("--support-prediction", required=True)
    run_plan_parser.add_argument("--refute-prediction", required=True)
    run_plan_parser.add_argument("--success-regex")
    run_plan_parser.add_argument("--pass-env", action="append", default=[])
    run_plan_parser.add_argument("--inherit-env", action="append", default=[])
    run_plan_parser.add_argument("--fork")
    run_plan_parser.add_argument("--control-for", help="support run whose exact mechanism this control removes; valid only with --class control")
    run_plan_parser.add_argument("--control-change", action="append", default=[], type=int, help="repeatable nonzero argv index changed from the linked support run")
    run_plan_parser.add_argument("--control-claim", default="", help="exact enabling transition removed by the linked control")
    run_plan_parser.add_argument("--extends-candidate", help="candidate whose proven primitive this downstream support run extends")
    run_plan_parser.add_argument("--extends-run", help="that candidate's sealed support run")
    run_plan_parser.add_argument("--extension-prefix", type=_path, help="declared harness or sequence prefix that carries the primitive into the downstream sink")
    run_plan_parser.add_argument("command", nargs=argparse.REMAINDER)
    run_plan_parser.set_defaults(handler=_cmd_run_plan)
    run_execute = run_sub.add_parser("execute")
    run_execute.add_argument("--root", required=True, type=_root)
    run_execute.add_argument("--run", required=True)
    run_execute.set_defaults(handler=lambda a: execute_run(a.root, a.run))
    run_observe = run_sub.add_parser("observe")
    run_observe.add_argument("--root", required=True, type=_root)
    run_observe.add_argument("--run", required=True)
    run_observe.add_argument("--outcome", required=True, choices=["supports", "refutes", "inconclusive"])
    run_observe.add_argument("--property-violated", required=True, choices=["yes", "no", "unknown"])
    run_observe.add_argument("--observation", required=True)
    run_observe.add_argument("--impact", default="")
    run_observe.add_argument("--metric", action="append", default=[], help="repeatable exact measurement as name=value:unit")
    run_observe.add_argument("--limitations", default="")
    run_observe.set_defaults(
        handler=lambda a: observe_run(
            a.root,
            a.run,
            outcome=a.outcome,
            property_violated=_tri_bool(a.property_violated),
            observation=a.observation,
            impact=a.impact,
            metrics=_metrics(a.metric),
            limitations=a.limitations,
        )
    )

    fork = commands.add_parser("fork", help="manage a pinned Anvil fork")
    fork_sub = fork.add_subparsers(dest="fork_command", required=True)
    fork_start = fork_sub.add_parser("start")
    fork_start.add_argument("--root", required=True, type=_root)
    fork_start.add_argument("--rpc-env")
    fork_start.add_argument("--chain-id", type=int)
    fork_start.add_argument("--block", type=int)
    fork_start.add_argument("--block-hash", help="expected hash; defaults to the campaign pin")
    fork_start.add_argument("--port", type=int, default=0)
    fork_start.add_argument("--startup-timeout", type=int, default=30)
    fork_start.add_argument("--max-output-bytes", type=int, default=16 * 1024 * 1024)
    fork_start.set_defaults(
        handler=lambda a: start_fork(
            a.root,
            rpc_env=a.rpc_env,
            chain_id=a.chain_id,
            block_number=a.block,
            expected_block_hash=a.block_hash,
            port=a.port,
            startup_timeout=a.startup_timeout,
            max_output_bytes=a.max_output_bytes,
        )
    )
    for name, handler in (("status", fork_status), ("snapshot", snapshot_fork), ("stop", stop_fork)):
        child = fork_sub.add_parser(name)
        child.add_argument("--root", required=True, type=_root)
        child.add_argument("--fork", required=True)
        child.set_defaults(handler=lambda a, fn=handler: fn(a.root, a.fork))
    fork_revert = fork_sub.add_parser("revert")
    fork_revert.add_argument("--root", required=True, type=_root)
    fork_revert.add_argument("--fork", required=True)
    fork_revert.add_argument("--snapshot")
    fork_revert.set_defaults(handler=lambda a: revert_fork(a.root, a.fork, a.snapshot))

    replay = commands.add_parser("replay", help="verify a sealed run in a clean source workspace")
    replay_sub = replay.add_subparsers(dest="replay_command", required=True)
    replay_prepare = replay_sub.add_parser("prepare")
    replay_prepare.add_argument("--root", required=True, type=_root)
    replay_prepare.add_argument("--run", required=True)
    replay_prepare.add_argument("--destination", required=True, type=_root)
    replay_prepare.set_defaults(handler=lambda a: prepare_replay(a.root, run_id=a.run, destination=a.destination))
    replay_verify = replay_sub.add_parser("verify")
    replay_verify.add_argument("--root", required=True, type=_root)
    replay_verify.add_argument("--run", required=True)
    replay_verify.add_argument("--workspace", required=True, type=_root)
    replay_verify.set_defaults(handler=lambda a: verify_replay(a.root, run_id=a.run, workspace=a.workspace))

    candidate = commands.add_parser("candidate", help="assemble and gate candidate evidence")
    candidate_sub = candidate.add_subparsers(dest="candidate_command", required=True)
    candidate_create = candidate_sub.add_parser("create")
    candidate_create.add_argument("--root", required=True, type=_root)
    candidate_create.add_argument("--hypothesis", required=True)
    candidate_create.add_argument("--support-run", required=True)
    candidate_create.add_argument("--control-run")
    candidate_create.add_argument("--replay")
    candidate_create.add_argument("--root-cause", required=True)
    candidate_create.add_argument("--code-evidence", required=True)
    candidate_create.add_argument("--reachability", required=True)
    candidate_create.add_argument("--property", required=True)
    candidate_create.add_argument("--impact", required=True)
    candidate_create.add_argument("--scope", required=True, help="active SCOPE ledger record")
    candidate_create.add_argument("--eligible-impact", required=True, help="exact matching data.impacts entry from --scope")
    candidate_create.add_argument(
        "--consequence-class",
        required=True,
        choices=["asset-loss", "insolvency", "permanent-freeze", "integrity", "authorization", "governance", "configuration", "upgrade", "role", "liveness", "unknown"],
    )
    candidate_create.add_argument("--terminal-impact", required=True, choices=["yes", "no"])
    for flag in ("implementation", "configuration", "actor", "economics"):
        candidate_create.add_argument(f"--{flag}-verified", action="store_true")
    candidate_create.set_defaults(
        handler=lambda a: create_candidate(
            a.root,
            hypothesis_id=a.hypothesis,
            support_run=a.support_run,
            control_run=a.control_run,
            replay_id=a.replay,
            root_cause=a.root_cause,
            code_evidence=a.code_evidence,
            reachability=a.reachability,
            property_statement=a.property,
            impact=a.impact,
            scope_id=a.scope,
            eligible_impact=a.eligible_impact,
            implementation_verified=a.implementation_verified,
            configuration_verified=a.configuration_verified,
            actor_verified=a.actor_verified,
            economics_verified=a.economics_verified,
            consequence_class=a.consequence_class,
            terminal_impact=a.terminal_impact == "yes",
        )
    )
    candidate_gate = candidate_sub.add_parser("gate")
    candidate_gate.add_argument("--root", required=True, type=_root)
    candidate_gate.add_argument("--candidate", required=True)
    candidate_gate.set_defaults(handler=lambda a: check_gates(a.root, a.candidate))
    candidate_promote = candidate_sub.add_parser("promote")
    candidate_promote.add_argument("--root", required=True, type=_root)
    candidate_promote.add_argument("--candidate", required=True)
    candidate_promote.set_defaults(handler=lambda a: promote_validated(a.root, a.candidate))

    review = commands.add_parser("review", help="record independent or coordinator candidate review")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_add = review_sub.add_parser("add")
    review_add.add_argument("--root", required=True, type=_root)
    review_add.add_argument("--candidate", required=True)
    review_add.add_argument("--reviewer", required=True)
    review_add.add_argument("--verdict", required=True, choices=["confirmed", "rejected", "needs-work"])
    review_add.add_argument("--notes", required=True)
    review_add.add_argument("--independent", action="store_true")
    review_add.add_argument("--evidence-ref", action="append", default=[])
    review_add.set_defaults(
        handler=lambda a: add_review(
            a.root,
            candidate_id=a.candidate,
            reviewer=a.reviewer,
            verdict=a.verdict,
            notes=a.notes,
            independent=a.independent,
            evidence_refs=_evidence_refs(a.evidence_ref),
        )
    )
    review_prepare = review_sub.add_parser("prepare-blind")
    review_prepare.add_argument("--root", required=True, type=_root)
    review_prepare.add_argument("--candidate", required=True)
    review_prepare.set_defaults(handler=lambda a: prepare_blind_review(a.root, a.candidate))
    review_complete = review_sub.add_parser("complete-in-session")
    review_complete.add_argument("--root", required=True, type=_root)
    review_complete.add_argument("--review", required=True)
    review_complete.add_argument("--subagent-thread", required=True)
    review_complete.add_argument("--result", required=True, type=_root)
    review_complete.add_argument(
        "--attest-visible-subagent",
        action="store_true",
        help="attest that /subagents shows this distinct built-in thread in the current CLI session; runtime records but cannot authenticate UI identity",
    )
    review_complete.set_defaults(handler=lambda a: record_in_session_review(
        a.root,
        a.review,
        subagent_thread=a.subagent_thread,
        result_path=a.result,
        attest_visible_subagent=a.attest_visible_subagent,
    ))

    controller = commands.add_parser("controller", help="enforce impact, evidence, frontier, and campaign completion")
    controller_sub = controller.add_subparsers(dest="controller_command", required=True)
    controller_assess = controller_sub.add_parser("assess")
    controller_assess.add_argument("--root", required=True, type=_root)
    controller_assess.set_defaults(handler=lambda a: assess_completion(a.root))
    controller_close = controller_sub.add_parser("close")
    controller_close.add_argument("--root", required=True, type=_root)
    controller_close.add_argument("--conclusion", required=True)
    controller_close.add_argument("--closure", required=True, choices=["clean", "open-risk", "budget-exhausted", "environment-blocked"])
    controller_close.set_defaults(handler=lambda a: close_campaign(a.root, conclusion=a.conclusion, closure=a.closure))

    coverage = commands.add_parser("coverage", help="record challenged adversarial coverage families")
    coverage_sub = coverage.add_subparsers(dest="coverage_command", required=True)
    coverage_record = coverage_sub.add_parser("record")
    coverage_record.add_argument("--root", required=True, type=_root)
    coverage_record.add_argument("--family", required=True, choices=["value", "authority", "lifecycle", "numeric", "composition"])
    coverage_record.add_argument("--status", required=True, choices=["challenged", "refuted", "not-applicable"])
    coverage_record.add_argument("--evidence-ref", action="append", required=True)
    coverage_record.add_argument("--limitations", default="")
    coverage_record.set_defaults(handler=lambda a: record_coverage(a.root, family=a.family, status=a.status, evidence_refs=_evidence_refs(a.evidence_ref), limitations=a.limitations))

    frontier = commands.add_parser("frontier", help="track unresolved high-value research branches")
    frontier_sub = frontier.add_subparsers(dest="frontier_command", required=True)
    frontier_add = frontier_sub.add_parser("add")
    frontier_add.add_argument("--root", required=True, type=_root)
    frontier_add.add_argument("--kind", required=True)
    frontier_add.add_argument("--statement", required=True)
    frontier_add.add_argument("--evidence-ref", action="append", required=True)
    frontier_add.add_argument("--next-action", required=True)
    frontier_add.add_argument("--priority", required=True, choices=["low", "medium", "high"])
    frontier_add.add_argument("--cost", required=True, choices=["low", "medium", "high"])
    frontier_add.add_argument("--candidate")
    frontier_add.set_defaults(handler=lambda a: add_frontier(a.root, kind=a.kind, statement=a.statement, grounding_refs=_evidence_refs(a.evidence_ref), next_action=a.next_action, priority=a.priority, cost=a.cost, candidate_id=a.candidate))
    frontier_resolve = frontier_sub.add_parser("resolve")
    frontier_resolve.add_argument("--root", required=True, type=_root)
    frontier_resolve.add_argument("--item", required=True)
    frontier_resolve.add_argument("--status", required=True, choices=["demonstrated", "refuted", "blocked", "superseded"])
    frontier_resolve.add_argument("--evidence-ref", action="append", required=True)
    frontier_resolve.add_argument("--blocker-kind", choices=["budget", "environment", "external-prerequisite", "tooling"])
    frontier_resolve.add_argument("--resolution-condition", default="")
    frontier_resolve.set_defaults(handler=lambda a: resolve_frontier(a.root, frontier_id=a.item, status=a.status, evidence_refs=_evidence_refs(a.evidence_ref), blocker_kind=a.blocker_kind, resolution_condition=a.resolution_condition))

    impact = commands.add_parser("impact", help="propagate a primitive through downstream consumers and terminal sinks")
    impact_sub = impact.add_subparsers(dest="impact_command", required=True)
    impact_add = impact_sub.add_parser("add")
    impact_add.add_argument("--root", required=True, type=_root)
    impact_add.add_argument("--candidate", required=True)
    impact_add.add_argument("--capability", required=True)
    impact_add.add_argument("--sink", required=True)
    impact_add.add_argument("--consequence", required=True)
    impact_add.add_argument("--impact-property", required=True, help="exact downstream security property tested by support and control runs")
    impact_add.add_argument("--status", required=True, choices=["open", "demonstrated", "refuted", "blocked"])
    impact_add.add_argument("--evidence-ref", action="append", required=True)
    impact_add.add_argument("--next-action", required=True)
    impact_add.add_argument("--high-consequence", action="store_true")
    impact_add.add_argument("--low-cost", action="store_true")
    impact_add.add_argument("--blocker-kind", choices=["budget", "environment", "external-prerequisite", "tooling"])
    impact_add.add_argument("--resolution-condition", default="")
    impact_add.set_defaults(
        handler=lambda a: add_impact(
            a.root,
            candidate_id=a.candidate,
            capability=a.capability,
            sink=a.sink,
            consequence=a.consequence,
            impact_property=a.impact_property,
            status=a.status,
            evidence_refs=_evidence_refs(a.evidence_ref),
            next_action=a.next_action,
            high_consequence=a.high_consequence,
            low_cost=a.low_cost,
            blocker_kind=a.blocker_kind,
            resolution_condition=a.resolution_condition,
        )
    )
    impact_resolve = impact_sub.add_parser("resolve")
    impact_resolve.add_argument("--root", required=True, type=_root)
    impact_resolve.add_argument("--impact", required=True)
    impact_resolve.add_argument("--status", required=True, choices=["demonstrated", "refuted", "blocked"])
    impact_resolve.add_argument("--evidence-ref", action="append", required=True)
    impact_resolve.add_argument("--next-action", default="none")
    impact_resolve.add_argument("--blocker-kind", choices=["budget", "environment", "external-prerequisite", "tooling"])
    impact_resolve.add_argument("--resolution-condition", default="")
    impact_resolve.set_defaults(handler=lambda a: resolve_impact(a.root, impact_id=a.impact, status=a.status, evidence_refs=_evidence_refs(a.evidence_ref), next_action=a.next_action, blocker_kind=a.blocker_kind, resolution_condition=a.resolution_condition))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except (A1XError, OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "message": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    if args.command_name == "mcp":
        return 0
    _json({"ok": True, "result": result})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
