from __future__ import annotations

import re
import hashlib
from pathlib import Path
from typing import Any

from .atomic import exclusive_lock, read_json, seal, verify_seal, write_json_atomic
from .errors import BudgetError, IntegrityError, ValidationError
from .hashing import is_relative_to, path_digest, safe_relative
from .process import execute, reject_model_argv
from .records import allocate_id, event, require_campaign, schema_for, update_research_counter, utc_now, validate_id

RUN_CLASSES = {"candidate", "control", "repair", "fuzz", "solve", "recon"}


def _anchor_path(campaign_root: Path, campaign: dict[str, Any], path: Path) -> tuple[str, str]:
    source = Path(campaign["source"]["path"])
    if is_relative_to(path, source):
        return "source", safe_relative(path, source)
    if is_relative_to(path, campaign_root):
        return "campaign", safe_relative(path, campaign_root)
    raise ValidationError(f"path must be within campaign source or campaign root: {path}")


def resolve_anchor(
    campaign_root: Path,
    campaign: dict[str, Any],
    anchor: str,
    relative: str,
    *,
    replay_source: Path | None = None,
    replay_campaign: Path | None = None,
) -> Path:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        raise IntegrityError(f"unsafe stored relative path: {relative}")
    if anchor == "source":
        base = replay_source or Path(campaign["source"]["path"])
    elif anchor == "campaign":
        base = replay_campaign or campaign_root
    else:
        raise IntegrityError(f"unknown path anchor: {anchor}")
    result = (base / relative).resolve()
    if not is_relative_to(result, base):
        raise IntegrityError(f"stored path escaped anchor: {relative}")
    return result


def _execution_identity(root: Path, campaign: dict[str, Any], fork_id: str | None) -> dict[str, Any]:
    if fork_id:
        fork_id = validate_id(fork_id, "FORK")
        fork = read_json(root / "forks" / f"{fork_id}.json")
        if fork.get("kind") != "fork":
            raise IntegrityError(f"invalid fork record: {fork_id}")
        chain_id = fork.get("chain_id")
        block_number = fork.get("block_number")
    else:
        chain_id = campaign["chain"].get("chain_id")
        block_number = campaign["chain"].get("block_number")
    return {"chain_id": chain_id, "block_number": block_number}


def plan_run(
    root: Path,
    *,
    hypothesis_id: str,
    run_class: str,
    cwd: Path,
    argv: list[str],
    timeout_seconds: int | None,
    max_output_bytes: int | None,
    inputs: list[Path],
    property_statement: str,
    support_prediction: str,
    refute_prediction: str,
    success_regex: str | None,
    pass_env: list[str],
    inherit_env: list[str],
    fork_id: str | None,
    control_for_run: str | None = None,
    control_change_indices: list[int] | None = None,
    control_claim: str = "",
    extends_candidate_id: str | None = None,
    extends_run: str | None = None,
    extension_prefix: Path | None = None,
    ledger_experiment_id: str | None = None,
) -> dict[str, Any]:
    campaign = require_campaign(root)
    reject_model_argv(argv)
    if timeout_seconds is None:
        timeout_seconds = int(campaign["budgets"]["default_run_timeout_seconds"])
    if max_output_bytes is None:
        max_output_bytes = int(campaign["budgets"]["default_output_bytes"])
    if run_class not in RUN_CLASSES:
        raise ValidationError(f"unsupported run class: {run_class}")
    control_change_indices = sorted(set(control_change_indices or []))
    if (control_for_run or control_change_indices or control_claim) and run_class != "control":
        raise ValidationError("control linkage fields are valid only for control runs")
    if not control_for_run and (control_change_indices or control_claim):
        raise ValidationError("control changes and claim require control_for_run")
    extension_values = (extends_candidate_id, extends_run, extension_prefix)
    if any(value is not None for value in extension_values) and not all(value is not None for value in extension_values):
        raise ValidationError("impact extension requires extends_candidate_id, extends_run, and extension_prefix together")
    if any(value is not None for value in extension_values) and run_class != "candidate":
        raise ValidationError("impact extension linkage is valid only for candidate runs")
    if control_for_run and any(value is not None for value in extension_values):
        raise ValidationError("a run cannot be both an impact extension and a causal control")
    if any(not value.strip() for value in (property_statement, support_prediction, refute_prediction)):
        raise ValidationError("property and supporting/refuting predictions must be non-empty")
    hypothesis_path = root / "hypotheses" / f"{hypothesis_id}.json"
    if not hypothesis_path.exists():
        raise ValidationError(f"unknown hypothesis: {hypothesis_id}")
    hypothesis_record = read_json(hypothesis_path)
    ledger_investigation_id = hypothesis_record.get("ledger_investigation_id")
    if ledger_experiment_id:
        from .ledger import show_record

        experiment = show_record(root, ledger_experiment_id)
        if experiment.get("kind") != "EXP":
            raise ValidationError("ledger_experiment_id must reference an EXP ledger record")
        if ledger_investigation_id and str(ledger_investigation_id) not in experiment.get("parents", []):
            raise ValidationError("typed run EXP must parent its canonical INV record")
    parent_plan: dict[str, Any] | None = None
    if control_for_run:
        control_for_run = validate_id(control_for_run, "RUN")
        parent_dir = root / "runs" / control_for_run
        verify_seal(parent_dir / "plan.json", parent_dir / "plan.sha256")
        parent_plan = read_json(parent_dir / "plan.json")
        if parent_plan.get("hypothesis_id") != hypothesis_id:
            raise ValidationError("control_for_run must reference a run under the same hypothesis")
        if not control_claim.strip():
            raise ValidationError("a linked control requires a non-empty control claim naming the removed transition")
        if not control_change_indices or any(index <= 0 for index in control_change_indices) or len(control_change_indices) > 4:
            raise ValidationError("a linked control requires one to four non-executable argv change indices")
    extension_parent_plan: dict[str, Any] | None = None
    extension_candidate: dict[str, Any] | None = None
    if extends_candidate_id is not None and extends_run is not None:
        extends_candidate_id = validate_id(extends_candidate_id, "CAND")
        extends_run = validate_id(extends_run, "RUN")
        candidate_path = root / "candidates" / f"{extends_candidate_id}.json"
        if not candidate_path.exists():
            raise ValidationError(f"unknown candidate: {extends_candidate_id}")
        extension_candidate = read_json(candidate_path)
        if extension_candidate.get("hypothesis_id") != hypothesis_id:
            raise ValidationError("impact extension candidate must belong to the same hypothesis")
        if extension_candidate.get("support_run") != extends_run:
            raise ValidationError("extends_run must be the candidate's recorded support run")
        parent_dir = root / "runs" / extends_run
        verify_seal(parent_dir / "plan.json", parent_dir / "plan.sha256")
        verify_seal(parent_dir / "receipt.json", parent_dir / "receipt.sha256")
        extension_parent_plan = read_json(parent_dir / "plan.json")
        parent_receipt = read_json(parent_dir / "receipt.json")
        if extension_parent_plan.get("hypothesis_id") != hypothesis_id:
            raise ValidationError("impact extension parent must belong to the same hypothesis")
        if not parent_receipt.get("mechanical_success"):
            raise ValidationError("impact extension parent must have a mechanically successful receipt")
    existing_runs = len([p for p in (root / "runs").iterdir() if p.is_dir()])
    maximum = int(campaign["budgets"].get("max_runs", 0))
    if maximum and existing_runs >= maximum:
        raise BudgetError(f"campaign max_runs budget reached ({maximum})")
    if timeout_seconds <= 0 or max_output_bytes <= 0:
        raise ValidationError("timeout and output limit must be positive")
    if success_regex:
        try:
            re.compile(success_regex)
        except re.error as exc:
            raise ValidationError(f"invalid success regex: {exc}") from exc
    cwd = cwd.resolve()
    cwd_anchor, cwd_relative = _anchor_path(root, campaign, cwd)
    execution_identity = _execution_identity(root, campaign, fork_id)
    declared_inputs = []
    for supplied in inputs:
        candidate = supplied if supplied.is_absolute() else cwd / supplied
        anchor, relative = _anchor_path(root, campaign, candidate.resolve())
        declared_inputs.append({"anchor": anchor, "path": relative, "digest": path_digest(candidate)})
    extension_contract = None
    if extension_parent_plan is not None and extension_prefix is not None:
        parent_identity = extension_parent_plan.get("execution_identity") or _execution_identity(
            root, campaign, extension_parent_plan.get("fork_id")
        )
        if parent_identity != execution_identity:
            raise ValidationError("impact extension must preserve the parent chain and pinned block identity")
        prefix_path = extension_prefix if extension_prefix.is_absolute() else cwd / extension_prefix
        prefix_path = prefix_path.resolve()
        prefix_anchor, prefix_relative = _anchor_path(root, campaign, prefix_path)
        prefix_record = {"anchor": prefix_anchor, "path": prefix_relative, "digest": path_digest(prefix_path)}
        if not any(
            item["anchor"] == prefix_anchor and item["path"] == prefix_relative
            for item in declared_inputs
        ):
            declared_inputs.append(prefix_record)
        parent_dir = root / "runs" / str(extends_run)
        extension_contract = {
            "candidate_id": extends_candidate_id,
            "parent_run": extends_run,
            "parent_plan_sha256": hashlib.sha256((parent_dir / "plan.json").read_bytes()).hexdigest(),
            "parent_receipt_sha256": hashlib.sha256((parent_dir / "receipt.json").read_bytes()).hexdigest(),
            "prefix": prefix_record,
            "execution_identity": execution_identity,
        }
    control_contract = None
    if parent_plan is not None:
        parent_argv = list(parent_plan.get("argv_template", []))
        if len(parent_argv) != len(argv):
            raise ValidationError("linked control argv must have the same length as the support run")
        actual_changes = [index for index, (left, right) in enumerate(zip(parent_argv, argv)) if left != right]
        if actual_changes != control_change_indices:
            raise ValidationError(
                "declared control change indices do not exactly match the support/control argv delta "
                f"(declared={control_change_indices}, actual={actual_changes})"
            )
        executable = Path(parent_argv[0]).name.lower()
        interpreter = executable.startswith("python") or executable in {"node", "deno", "ruby", "bash", "sh", "zsh"}
        package_runner = executable in {"npx", "npm", "pnpm", "yarn", "bunx"}
        stable_prefix = 2
        if interpreter and len(parent_argv) > 2 and parent_argv[1] == "-m":
            stable_prefix = 3
        elif package_runner and len(parent_argv) > 2:
            stable_prefix = 3
        if any(index < stable_prefix for index in actual_changes):
            raise ValidationError("linked control must preserve the executable, harness entry point, and command/subcommand identity")
        opaque_payload_flags = {"-c", "--eval", "-e"}
        if any(
            index > 0
            and (parent_argv[index - 1] in opaque_payload_flags or argv[index - 1] in opaque_payload_flags)
            for index in actual_changes
        ):
            raise ValidationError("linked control cannot replace an opaque inline program; use the same declared harness with bounded selector/parameter changes")
        comparable = {
            "cwd": {"anchor": cwd_anchor, "path": cwd_relative},
            "inputs": declared_inputs,
            "fork_id": fork_id,
            "pass_env": sorted(set(pass_env)),
            "inherit_env": sorted(set(inherit_env)),
            "source_commit": campaign["source"]["git"].get("commit"),
        }
        for field, value in comparable.items():
            if parent_plan.get(field) != value:
                raise ValidationError(f"linked control must preserve support-run {field}")
        control_contract = {
            "support_run": control_for_run,
            "claim": control_claim.strip(),
            "changed_argv": [
                {
                    "index": index,
                    "support_sha256": hashlib.sha256(parent_argv[index].encode()).hexdigest(),
                    "control_sha256": hashlib.sha256(argv[index].encode()).hexdigest(),
                }
                for index in actual_changes
            ],
        }
    run_id = allocate_id(root, "RUN")
    run_dir = root / "runs" / run_id
    run_dir.mkdir()
    plan = {
        "schema": schema_for(root),
        "kind": "run-plan",
        "id": run_id,
        "created_at": utc_now(),
        "hypothesis_id": hypothesis_id,
        "ledger_investigation_id": ledger_investigation_id,
        "ledger_experiment_id": ledger_experiment_id,
        "run_class": run_class,
        "cwd": {"anchor": cwd_anchor, "path": cwd_relative},
        "argv_template": argv,
        "timeout_seconds": timeout_seconds,
        "max_output_bytes": max_output_bytes,
        "inputs": declared_inputs,
        "property": property_statement,
        "support_prediction": support_prediction,
        "refute_prediction": refute_prediction,
        "success_regex": success_regex,
        "pass_env": sorted(set(pass_env)),
        "inherit_env": sorted(set(inherit_env)),
        "fork_id": fork_id,
        "execution_identity": execution_identity,
        "control_for_run": control_for_run,
        "control_contract": control_contract,
        "extension_contract": extension_contract,
        "source_commit": campaign["source"]["git"].get("commit"),
        "network_isolation": {"requested": False, "enforced": False},
    }
    plan_path = run_dir / "plan.json"
    write_json_atomic(plan_path, plan)
    plan_hash = seal(plan_path, run_dir / "plan.sha256")
    with exclusive_lock(root):
        hypothesis = read_json(hypothesis_path)
        hypothesis.setdefault("runs", []).append(run_id)
        hypothesis["updated_at"] = utc_now()
        write_json_atomic(hypothesis_path, hypothesis)
    if ledger_investigation_id:
        from .ledger import link_runtime_ref

        link_runtime_ref(
            root,
            str(ledger_investigation_id),
            f"runs/{run_id}/plan.json",
            expected_kind="INV",
            reason=f"linked sealed experiment {run_id}",
        )
    if ledger_experiment_id:
        from .ledger import link_runtime_ref

        link_runtime_ref(
            root,
            ledger_experiment_id,
            f"runs/{run_id}/plan.json",
            expected_kind="EXP",
            reason=f"linked sealed run plan {run_id}",
            status="active",
        )
    event(root, "run.planned", run_id=run_id, hypothesis_id=hypothesis_id, plan_sha256=plan_hash)
    return {"run_id": run_id, "plan_sha256": plan_hash, "plan": plan}


def verify_inputs(
    root: Path,
    plan: dict[str, Any],
    *,
    replay_source: Path | None = None,
    replay_campaign: Path | None = None,
) -> list[dict[str, Any]]:
    campaign = require_campaign(root)
    results = []
    for item in plan.get("inputs", []):
        path = resolve_anchor(root, campaign, item["anchor"], item["path"], replay_source=replay_source, replay_campaign=replay_campaign)
        actual = path_digest(path)
        matches = actual == item["digest"]
        results.append({"anchor": item["anchor"], "path": item["path"], "matches": matches, "expected": item["digest"], "actual": actual})
        if not matches:
            raise IntegrityError(f"declared input changed: {item['anchor']}:{item['path']}")
    return results


def execute_run(root: Path, run_id: str) -> dict[str, Any]:
    run_dir = root / "runs" / run_id
    with exclusive_lock(run_dir):
        return _execute_run_locked(root, run_id)


def _execute_run_locked(root: Path, run_id: str) -> dict[str, Any]:
    campaign = require_campaign(root)
    run_dir = root / "runs" / run_id
    receipt_path = run_dir / "receipt.json"
    if receipt_path.exists():
        raise IntegrityError(f"run is immutable and already executed: {run_id}")
    plan_path = run_dir / "plan.json"
    verify_seal(plan_path, run_dir / "plan.sha256")
    plan = read_json(plan_path)
    input_checks = verify_inputs(root, plan)
    cwd = resolve_anchor(root, campaign, plan["cwd"]["anchor"], plan["cwd"]["path"])
    result = execute(
        plan["argv_template"],
        cwd=cwd,
        artifact_dir=run_dir,
        timeout_seconds=int(plan["timeout_seconds"]),
        max_output_bytes=int(plan["max_output_bytes"]),
        pass_env=plan.get("pass_env", []),
        inherit_env=plan.get("inherit_env", []),
    )
    regex_match: bool | None = None
    if plan.get("success_regex"):
        output = (run_dir / "stdout.log").read_text(encoding="utf-8", errors="replace")
        regex_match = bool(re.search(plan["success_regex"], output, flags=re.MULTILINE))
    receipt = {
        "schema": schema_for(root),
        "kind": "run-receipt",
        "run_id": run_id,
        "plan_sha256": (run_dir / "plan.sha256").read_text().strip(),
        "input_checks": input_checks,
        "process": result.to_dict(),
        "success_regex_matched": regex_match,
        "mechanical_success": result.exit_code == 0 and not result.timed_out and (regex_match is not False),
        "semantic_result": "unreviewed",
    }
    write_json_atomic(receipt_path, receipt)
    seal(receipt_path, run_dir / "receipt.sha256")
    counter = {
        "candidate": "candidate_executions",
        "control": "candidate_executions",
        "repair": "compilation_harness_repairs",
        "fuzz": "fuzzer_campaigns",
        "solve": "solver_campaigns",
    }.get(plan["run_class"])
    if counter:
        update_research_counter(root, counter)
    event(root, "run.executed", run_id=run_id, exit_code=result.exit_code, timed_out=result.timed_out)
    return receipt


def observe_run(
    root: Path,
    run_id: str,
    *,
    outcome: str,
    property_violated: bool | None,
    observation: str,
    impact: str,
    metrics: list[dict[str, str]],
    limitations: str,
) -> dict[str, Any]:
    if outcome not in {"supports", "refutes", "inconclusive"}:
        raise ValidationError(f"invalid outcome: {outcome}")
    run_dir = root / "runs" / run_id
    receipt_path = run_dir / "receipt.json"
    if not receipt_path.exists():
        raise ValidationError(f"run has not executed: {run_id}")
    observation_path = run_dir / "observation.json"
    if observation_path.exists():
        raise IntegrityError(f"observation is immutable; create a new run to reinterpret changed evidence: {run_id}")
    record = {
        "schema": schema_for(root),
        "kind": "run-observation",
        "run_id": run_id,
        "created_at": utc_now(),
        "outcome": outcome,
        "property_violated": property_violated,
        "observation": observation,
        "impact": impact,
        "metrics": metrics,
        "limitations": limitations,
        "reviewed_by": "codex-investigator",
    }
    write_json_atomic(observation_path, record)
    seal(observation_path, run_dir / "observation.sha256")
    event(root, "run.observed", run_id=run_id, outcome=outcome, property_violated=property_violated)
    plan = read_json(run_dir / "plan.json")
    ledger_experiment_id = plan.get("ledger_experiment_id")
    if ledger_experiment_id:
        from .ledger import link_runtime_ref

        link_runtime_ref(
            root,
            str(ledger_experiment_id),
            f"runs/{run_id}/observation.json",
            expected_kind="EXP",
            reason=f"linked observed experiment {run_id}: {outcome}",
            status="closed",
        )
    return record
