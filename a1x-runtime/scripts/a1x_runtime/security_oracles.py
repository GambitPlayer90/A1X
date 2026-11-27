from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import IntegrityError, ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


ORACLE_TYPES = {
    "asset-conservation",
    "solvency",
    "victim-exitability",
    "authorization",
    "liveness",
    "accounting",
    "erc4626-rounding",
    "multi-asset-wealth",
    "custom",
}
OPERATORS = {"==", "!=", ">", ">=", "<", "<="}
METRIC_ROLES = {"attacker-asset", "attacker-liability", "victim-asset", "protocol-asset", "protocol-liability", "control", "state", "other"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"oracle {field} must be non-empty")
    return result


def _exact_decimal(value: Any, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"oracle {field} must be an exact decimal") from exc
    if not number.is_finite():
        raise ValidationError(f"oracle {field} must be finite")
    return number


def _normalize_metrics(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw or any(not isinstance(item, dict) for item in raw):
        raise ValidationError("oracle metrics must be a non-empty array of objects")
    metrics = []
    names: set[str] = set()
    for item in raw:
        name = _text(item.get("name"), "metric.name")
        if name in names:
            raise ValidationError(f"duplicate oracle metric: {name}")
        names.add(name)
        role = str(item.get("role") or "other")
        if role not in METRIC_ROLES:
            raise ValidationError(f"unsupported oracle metric role: {role}")
        metrics.append(
            {
                "name": name,
                "unit": _text(item.get("unit"), "metric.unit"),
                "role": role,
                "description": _text(item.get("description"), "metric.description"),
            }
        )
    return metrics


def _operand(value: Any, metric_names: set[str]) -> dict[str, str]:
    if isinstance(value, dict):
        if set(value) != {"metric"} or str(value["metric"]) not in metric_names:
            raise ValidationError("oracle assertion metric operand is unknown")
        return {"metric": str(value["metric"])}
    number = _exact_decimal(value, "assertion operand")
    return {"constant": str(number)}


def _normalize_assertions(raw: Any, metric_names: set[str]) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw or any(not isinstance(item, dict) for item in raw):
        raise ValidationError("oracle assertions must be a non-empty array of objects")
    assertions = []
    ids: set[str] = set()
    for item in raw:
        assertion_id = _text(item.get("id"), "assertion.id")
        if assertion_id in ids:
            raise ValidationError(f"duplicate oracle assertion: {assertion_id}")
        ids.add(assertion_id)
        operator = str(item.get("operator") or "")
        if operator not in OPERATORS:
            raise ValidationError(f"unsupported oracle assertion operator: {operator}")
        assertions.append(
            {
                "id": assertion_id,
                "left": _operand(item.get("left"), metric_names),
                "operator": operator,
                "right": _operand(item.get("right"), metric_names),
                "violation_when_true": item.get("violation_when_true") is not False,
                "meaning": _text(item.get("meaning"), "assertion.meaning"),
            }
        )
    return assertions


def create_security_oracle(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not isinstance(payload, dict):
        raise ValidationError("oracle payload must be an object")
    oracle_type = str(payload.get("oracle_type") or "")
    if oracle_type not in ORACLE_TYPES:
        raise ValidationError(f"unsupported oracle type: {oracle_type}")
    metrics = _normalize_metrics(payload.get("metrics"))
    assertions = _normalize_assertions(payload.get("assertions"), {item["name"] for item in metrics})
    valuation = payload.get("valuation")
    if valuation is not None:
        if not isinstance(valuation, dict):
            raise ValidationError("oracle valuation must be an object or null")
        if valuation.get("independent") is not True:
            raise ValidationError("wealth valuation must declare an independent price source")
        refs = normalize_evidence_refs(root, valuation.get("evidence_refs", []), required=True)
        valuation = {
            "independent": True,
            "method": _text(valuation.get("method"), "valuation.method"),
            "block_reference": _text(valuation.get("block_reference"), "valuation.block_reference"),
            "evidence_refs": refs,
            "warning": "same-transaction manipulable spot quotes are not accepted as independent valuation",
        }
    elif oracle_type == "multi-asset-wealth":
        raise ValidationError("a multi-asset wealth oracle requires independent valuation metadata")
    oracle_id = allocate_id(root, "ORACLE")
    record = {
        "schema": schema_for(root),
        "kind": "security-oracle",
        "id": oracle_id,
        "created_at": utc_now(),
        "oracle_type": oracle_type,
        "property": _text(payload.get("property"), "property"),
        "units_policy": _text(payload.get("units_policy"), "units_policy"),
        "actor_model": _text(payload.get("actor_model"), "actor_model"),
        "metrics": metrics,
        "assertions": assertions,
        "valuation": valuation,
        "limitations": _text(payload.get("limitations"), "limitations"),
        "evaluations": [],
    }
    write_json_atomic(root / "oracles" / f"{oracle_id}.json", record)
    event(root, "oracle.created", oracle_id=oracle_id, oracle_type=oracle_type)
    return record


def _value(operand: dict[str, str], observations: dict[str, Decimal]) -> Decimal:
    if "metric" in operand:
        return observations[operand["metric"]]
    return Decimal(operand["constant"])


def _compare(left: Decimal, operator: str, right: Decimal) -> bool:
    return {
        "==": left == right,
        "!=": left != right,
        ">": left > right,
        ">=": left >= right,
        "<": left < right,
        "<=": left <= right,
    }[operator]


def evaluate_security_oracle(
    root: Path,
    *,
    oracle_id: str,
    run_id: str,
    observations: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    control_run: str | None = None,
) -> dict[str, Any]:
    oracle_id = validate_id(oracle_id, "ORACLE")
    run_id = validate_id(run_id, "RUN")
    path = root / "oracles" / f"{oracle_id}.json"
    oracle = read_json(path)
    expected = {item["name"] for item in oracle["metrics"]}
    if set(observations) != expected:
        raise ValidationError(f"oracle observations must exactly match declared metrics: {sorted(expected)}")
    values = {name: _exact_decimal(value, f"observation {name}") for name, value in observations.items()}
    refs = normalize_evidence_refs(root, evidence_refs, required=True)
    if not any(item.get("type") == "run-receipt" and item.get("run_id") == run_id for item in refs):
        raise ValidationError("oracle evaluation requires the evaluated run receipt")
    if control_run is not None:
        control_run = validate_id(control_run, "RUN")
        if not any(item.get("type") == "run-receipt" and item.get("run_id") == control_run for item in refs):
            raise ValidationError("oracle causal control must be present in the evidence references")
    results = []
    for assertion in oracle["assertions"]:
        left = _value(assertion["left"], values)
        right = _value(assertion["right"], values)
        comparison = _compare(left, assertion["operator"], right)
        violated = comparison if assertion["violation_when_true"] else not comparison
        results.append(
            {
                "id": assertion["id"],
                "left": str(left),
                "operator": assertion["operator"],
                "right": str(right),
                "comparison": comparison,
                "violated": violated,
                "meaning": assertion["meaning"],
            }
        )
    evaluation_id = allocate_id(root, "OEVAL")
    record = {
        "schema": schema_for(root),
        "kind": "oracle-evaluation",
        "id": evaluation_id,
        "created_at": utc_now(),
        "oracle_id": oracle_id,
        "run_id": run_id,
        "control_run": control_run,
        "observations": {name: str(value) for name, value in values.items()},
        "assertions": results,
        "property_violated": any(item["violated"] for item in results),
        "evidence_refs": refs,
        "scope": "the declared property and actor model only",
    }
    write_json_atomic(root / "oracles" / f"{evaluation_id}.json", record)
    oracle["evaluations"].append(evaluation_id)
    write_json_atomic(path, oracle)
    event(root, "oracle.evaluated", oracle_id=oracle_id, evaluation_id=evaluation_id, property_violated=record["property_violated"])
    return record


def verify_oracle_evaluation(root: Path, evaluation_id: str) -> dict[str, Any]:
    evaluation_id = validate_id(evaluation_id, "OEVAL")
    record = read_json(root / "oracles" / f"{evaluation_id}.json")
    errors = verify_evidence_refs(root, record.get("evidence_refs", []))
    oracle_path = root / "oracles" / f"{record.get('oracle_id')}.json"
    if not oracle_path.is_file():
        errors.append("oracle definition is missing")
    if not (root / "runs" / str(record.get("run_id")) / "receipt.json").is_file():
        errors.append("evaluated run receipt is missing")
    return {"evaluation_id": evaluation_id, "valid": not errors, "errors": errors, "record": record}


def standard_oracle_profile(profile: str) -> dict[str, Any]:
    profiles = {
        "solvency": {
            "oracle_type": "solvency",
            "property": "protocol assets cover protocol liabilities",
            "units_policy": "assets and liabilities must use the same declared base unit",
            "metrics": [
                {"name": "assets", "unit": "base", "role": "protocol-asset", "description": "independently measured backing"},
                {"name": "liabilities", "unit": "base", "role": "protocol-liability", "description": "independently measured obligations"},
            ],
            "assertions": [{
                "id": "insolvent",
                "left": {"metric": "liabilities"},
                "operator": ">",
                "right": {"metric": "assets"},
                "violation_when_true": True,
                "meaning": "liabilities exceed backing",
            }],
        },
        "victim-exitability": {
            "oracle_type": "victim-exitability",
            "property": "an honest victim can exit without losing declared principal",
            "units_policy": "exit_succeeded is 0/1 and principal_delta uses the victim asset unit",
            "metrics": [
                {"name": "exit_succeeded", "unit": "bool", "role": "control", "description": "honest exit completed"},
                {"name": "principal_delta", "unit": "asset", "role": "victim-asset", "description": "received minus owed principal"},
            ],
            "assertions": [
                {"id": "exit-blocked", "left": {"metric": "exit_succeeded"}, "operator": "==", "right": "0", "violation_when_true": True, "meaning": "honest exit failed"},
                {"id": "principal-loss", "left": {"metric": "principal_delta"}, "operator": "<", "right": "0", "violation_when_true": True, "meaning": "honest exit lost principal"},
            ],
        },
        "erc4626-rounding": {
            "oracle_type": "erc4626-rounding",
            "property": "a deposit and redemption cycle does not create assets for the caller",
            "units_policy": "asset_before and asset_after use the vault asset's smallest unit",
            "metrics": [
                {"name": "asset_before", "unit": "asset", "role": "attacker-asset", "description": "caller assets before cycle"},
                {"name": "asset_after", "unit": "asset", "role": "attacker-asset", "description": "caller assets after cycle"},
            ],
            "assertions": [{
                "id": "profitable-cycle",
                "left": {"metric": "asset_after"},
                "operator": ">",
                "right": {"metric": "asset_before"},
                "violation_when_true": True,
                "meaning": "round trip created caller assets",
            }],
        },
    }
    if profile not in profiles:
        raise ValidationError(f"unknown standard oracle profile: {profile}")
    return profiles[profile]
