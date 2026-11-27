from __future__ import annotations

import json
import sys
from typing import Any

import z3


def solve(problem: dict[str, Any]) -> dict[str, Any]:
    variables = {str(item["name"]): z3.Int(str(item["name"])) for item in problem["variables"]}
    solver = z3.Optimize() if problem["objective"] else z3.Solver()
    for item in problem["variables"]:
        variable = variables[str(item["name"])]
        solver.add(variable >= int(item["min"]), variable <= int(item["max"]))
        solver.add((variable - int(item["min"])) % int(item["step"]) == 0)

    def expression(value: dict[str, Any]) -> Any:
        return int(value["constant"]) + sum(
            int(coefficient) * variables[name]
            for name, coefficient in value["coefficients"].items()
        )

    for item in problem["constraints"]:
        left = expression(item["lhs"])
        right = int(item["rhs"])
        solver.add(
            {
                "==": left == right,
                "!=": left != right,
                ">": left > right,
                ">=": left >= right,
                "<": left < right,
                "<=": left <= right,
            }[item["operator"]]
        )
    if problem["objective"]:
        objective = expression(problem["objective"]["expression"])
        (solver.minimize if problem["objective"]["sense"] == "min" else solver.maximize)(objective)
    status = solver.check()
    if status != z3.sat:
        return {
            "satisfiable": False,
            "models": [],
            "evaluations": None,
            "complete": True,
            "status": str(status),
            "z3_version": z3.get_version_string(),
        }
    model = solver.model()
    values = {
        name: model.eval(variable, model_completion=True).as_long()
        for name, variable in variables.items()
    }
    score = 0
    if problem["objective"]:
        objective = problem["objective"]["expression"]
        score = int(objective["constant"]) + sum(
            int(coefficient) * values[name]
            for name, coefficient in objective["coefficients"].items()
        )
    return {
        "satisfiable": True,
        "models": [{"values": values, "objective": score}],
        "evaluations": None,
        "complete": True,
        "status": str(status),
        "z3_version": z3.get_version_string(),
    }


def main() -> int:
    problem = json.load(sys.stdin)
    json.dump(solve(problem), sys.stdout, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
