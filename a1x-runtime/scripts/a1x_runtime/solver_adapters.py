from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


EXTERNAL_BACKENDS = {
    "foundry": ("forge", ["--version"]),
    "halmos": ("halmos", ["--version"]),
    "medusa": ("medusa", ["--version"]),
    "echidna": ("echidna", ["--version"]),
    "ityfuzz": ("ityfuzz", ["--version"]),
    "wake": ("wake", ["--version"]),
}
OPERATORS = {"==", "!=", ">", ">=", "<", "<="}


def _z3_python() -> Path | None:
    configured = os.environ.get("A1X_Z3_PYTHON")
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path.home() / ".local" / "share" / "a1x" / "z3-4.15.4.0" / "bin" / "python",
    ]
    return next((item for item in candidates if item is not None and item.is_file()), None)


def probe_solver_tools() -> dict[str, Any]:
    tools = {}
    environment = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": "/tmp",
        "CI": "1",
        "FOUNDRY_FFI": "false",
    }
    for name, (executable, version_args) in EXTERNAL_BACKENDS.items():
        path = shutil.which(executable)
        if not path:
            tools[name] = {"installed": False, "executable": executable, "version_probe_passed": False, "version": None}
            continue
        try:
            result = subprocess.run([path, *version_args], capture_output=True, text=True, timeout=15, env=environment)
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip().splitlines()
            tools[name] = {
                "installed": True,
                "executable": path,
                "version_probe_passed": result.returncode == 0,
                "version": output[0][:300] if output else None,
            }
        except (OSError, subprocess.SubprocessError) as exc:
            tools[name] = {
                "installed": True,
                "executable": path,
                "version_probe_passed": False,
                "version": None,
                "diagnostic": f"{type(exc).__name__}: {exc}",
            }
    z3_python = _z3_python()
    if z3_python:
        try:
            result = subprocess.run(
                [str(z3_python), "-c", "import z3; print(z3.get_version_string())"],
                capture_output=True,
                text=True,
                timeout=15,
                env={"PATH": environment["PATH"], "HOME": environment["HOME"]},
            )
            tools["z3-python"] = {
                "installed": True,
                "executable": str(z3_python),
                "version_probe_passed": result.returncode == 0,
                "version": result.stdout.strip() or None,
            }
        except (OSError, subprocess.SubprocessError) as exc:
            tools["z3-python"] = {"installed": True, "version_probe_passed": False, "version": None, "diagnostic": type(exc).__name__}
    else:
        tools["z3-python"] = {"installed": False, "version_probe_passed": False, "version": None}
    tools["python-exact"] = {"installed": True, "version_probe_passed": True, "version": os.sys.version.split()[0]}
    return tools


def _variables(raw: Any) -> list[dict[str, int | str]]:
    if not isinstance(raw, list) or not raw or any(not isinstance(item, dict) for item in raw):
        raise ValidationError("solver variables must be a non-empty array of objects")
    output = []
    names: set[str] = set()
    for item in raw:
        name = str(item.get("name") or "").strip()
        if not name.isidentifier() or name in names:
            raise ValidationError(f"solver variable name is invalid or duplicated: {name}")
        names.add(name)
        minimum = item.get("min")
        maximum = item.get("max")
        step = item.get("step", 1)
        if not all(isinstance(value, int) for value in (minimum, maximum, step)) or step <= 0 or minimum > maximum:
            raise ValidationError(f"solver variable bounds are invalid: {name}")
        output.append({"name": name, "min": minimum, "max": maximum, "step": step})
    return output


def _linear(raw: Any, names: set[str], field: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError(f"solver {field} must be an object")
    coefficients = raw.get("coefficients")
    if not isinstance(coefficients, dict) or set(coefficients) - names or any(not isinstance(value, int) for value in coefficients.values()):
        raise ValidationError(f"solver {field} coefficients are invalid")
    constant = raw.get("constant", 0)
    if not isinstance(constant, int):
        raise ValidationError(f"solver {field} constant must be an integer")
    return {"coefficients": {str(key): int(value) for key, value in coefficients.items()}, "constant": constant}


def _problem(payload: dict[str, Any]) -> dict[str, Any]:
    variables = _variables(payload.get("variables"))
    names = {str(item["name"]) for item in variables}
    constraints = []
    raw_constraints = payload.get("constraints")
    if not isinstance(raw_constraints, list) or not raw_constraints or any(not isinstance(item, dict) for item in raw_constraints):
        raise ValidationError("solver constraints must be a non-empty array")
    for item in raw_constraints:
        operator = str(item.get("operator") or "")
        rhs = item.get("rhs")
        if operator not in OPERATORS or not isinstance(rhs, int):
            raise ValidationError("solver constraint operator/rhs is invalid")
        constraints.append({"lhs": _linear(item.get("lhs"), names, "constraint lhs"), "operator": operator, "rhs": rhs})
    objective = payload.get("objective")
    if objective is not None:
        if not isinstance(objective, dict) or objective.get("sense") not in {"min", "max"}:
            raise ValidationError("solver objective requires min/max sense")
        objective = {"sense": objective["sense"], "expression": _linear(objective.get("expression"), names, "objective")}
    return {
        "question": str(payload.get("question") or "").strip(),
        "variables": variables,
        "constraints": constraints,
        "objective": objective,
        "maximum_models": int(payload.get("maximum_models", 16)),
        "maximum_evaluations": int(payload.get("maximum_evaluations", 100_000)),
    }


def _eval_linear(expression: dict[str, Any], values: dict[str, int]) -> int:
    return int(expression["constant"]) + sum(int(coefficient) * values[name] for name, coefficient in expression["coefficients"].items())


def _compare(left: int, operator: str, right: int) -> bool:
    return {"==": left == right, "!=": left != right, ">": left > right, ">=": left >= right, "<": left < right, "<=": left <= right}[operator]


def _exact(problem: dict[str, Any]) -> dict[str, Any]:
    domains = [range(int(item["min"]), int(item["max"]) + 1, int(item["step"])) for item in problem["variables"]]
    possible = 1
    for domain in domains:
        possible *= len(domain)
    if possible > problem["maximum_evaluations"]:
        raise ValidationError(f"exact search space {possible} exceeds maximum_evaluations {problem['maximum_evaluations']}")
    models = []
    for values_tuple in itertools.product(*domains):
        values = {str(item["name"]): int(value) for item, value in zip(problem["variables"], values_tuple)}
        if all(_compare(_eval_linear(item["lhs"], values), item["operator"], int(item["rhs"])) for item in problem["constraints"]):
            score = _eval_linear(problem["objective"]["expression"], values) if problem["objective"] else 0
            models.append({"values": values, "objective": score})
    if problem["objective"]:
        reverse = problem["objective"]["sense"] == "max"
        models.sort(key=lambda item: (item["objective"], tuple(sorted(item["values"].items()))), reverse=reverse)
    return {"satisfiable": bool(models), "models": models[: problem["maximum_models"]], "evaluations": possible, "complete": True}


def _z3(problem: dict[str, Any]) -> dict[str, Any]:
    python = _z3_python()
    if python is None:
        raise ValidationError("the isolated A1X z3-python environment is unavailable")
    worker = Path(__file__).with_name("z3_worker.py")
    result = subprocess.run(
        [str(python), str(worker)],
        input=json.dumps(problem),
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp"},
    )
    if result.returncode != 0:
        raise ValidationError(f"z3 worker failed: {result.stderr.strip()[:500]}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValidationError("z3 worker returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValidationError("z3 worker returned an invalid result")
    return value


def create_solver_job(root: Path, payload: dict[str, Any], *, backend: str) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "solver_adapters"):
        raise ValidationError("solver adapters are disabled by runtime feature policy")
    if backend not in {"python-exact", "z3-python"}:
        raise ValidationError("direct solver jobs support python-exact or z3-python")
    problem = _problem(payload)
    if not problem["question"]:
        raise ValidationError("solver question must be non-empty")
    result = _exact(problem) if backend == "python-exact" else _z3(problem)
    job_id = allocate_id(root, "SOLVER")
    record = {
        "schema": schema_for(root),
        "kind": "bounded-solver-job",
        "id": job_id,
        "created_at": utc_now(),
        "backend": backend,
        "problem": problem,
        "result": result,
        "status": "solved" if result["satisfiable"] else "unsatisfiable",
        "validation_run": None,
        "validation_replay": None,
        "policy": "solver models are candidate inputs until concrete EVM replay validates them",
    }
    write_json_atomic(root / "solver-jobs" / f"{job_id}.json", record)
    event(root, "solver.completed", solver_job_id=job_id, backend=backend, satisfiable=result["satisfiable"])
    return record


def register_external_solver_job(
    root: Path,
    *,
    backend: str,
    run_id: str,
    witness_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    if backend not in EXTERNAL_BACKENDS:
        raise ValidationError(f"unknown external solver/fuzzer backend: {backend}")
    capabilities = read_json(root / "capabilities" / "capabilities.json")
    target = capabilities.get("backends", {}).get(backend, {})
    if target.get("ready") is not True:
        raise ValidationError(f"backend is not target-ready: {backend}")
    run_id = validate_id(run_id, "RUN")
    refs = normalize_evidence_refs(root, witness_refs, required=True)
    if not any(item.get("type") == "run-receipt" and item.get("run_id") == run_id for item in refs):
        raise ValidationError("external solver job requires its run receipt")
    if not any(item.get("type") == "solver-witness" and item.get("run_id") == run_id for item in refs):
        raise ValidationError("external solver job requires a solver-witness artifact")
    job_id = allocate_id(root, "SOLVER")
    record = {
        "schema": schema_for(root),
        "kind": "external-solver-job",
        "id": job_id,
        "created_at": utc_now(),
        "backend": backend,
        "run_id": run_id,
        "witness_refs": refs,
        "status": "candidate-witness",
        "validation_run": None,
        "validation_replay": None,
    }
    write_json_atomic(root / "solver-jobs" / f"{job_id}.json", record)
    event(root, "solver.external-recorded", solver_job_id=job_id, backend=backend, run_id=run_id)
    return record


def validate_solver_job(root: Path, *, solver_job_id: str, run_id: str, replay_id: str) -> dict[str, Any]:
    solver_job_id = validate_id(solver_job_id, "SOLVER")
    run_id = validate_id(run_id, "RUN")
    replay_id = validate_id(replay_id, "REPLAY")
    path = root / "solver-jobs" / f"{solver_job_id}.json"
    record = read_json(path)
    receipt = read_json(root / "runs" / run_id / "receipt.json")
    replay = read_json(root / "replays" / f"{replay_id}.json")
    if receipt.get("mechanical_success") is not True or replay.get("run_id") != run_id or replay.get("passed") is not True:
        raise ValidationError("solver validation requires a successful concrete run and matching replay")
    record["validation_run"] = run_id
    record["validation_replay"] = replay_id
    record["status"] = "concretely-replayed"
    write_json_atomic(path, record)
    event(root, "solver.validated", solver_job_id=solver_job_id, run_id=run_id, replay_id=replay_id)
    return record


def verify_solver_job(root: Path, solver_job_id: str) -> dict[str, Any]:
    solver_job_id = validate_id(solver_job_id, "SOLVER")
    record = read_json(root / "solver-jobs" / f"{solver_job_id}.json")
    errors = []
    if record.get("kind") == "external-solver-job":
        errors.extend(verify_evidence_refs(root, record.get("witness_refs", [])))
    if record.get("status") == "concretely-replayed":
        replay = root / "replays" / f"{record.get('validation_replay')}.json"
        if not replay.is_file() or read_json(replay).get("passed") is not True:
            errors.append("solver validation replay is missing or failed")
    return {"solver_job_id": solver_job_id, "valid": not errors, "errors": errors, "record": record}
