from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import A1XError
from .features import enabled
from .records import require_v4_campaign, schema_for, utc_now


def _entry(
    *,
    source: str,
    kind: str,
    reason: str,
    next_action: str,
    priority: str = "high",
    cost: str = "medium",
    disposition: str = "open",
) -> dict[str, str]:
    return {
        "source": source,
        "kind": kind,
        "reason": reason,
        "next_action": next_action,
        "priority": priority,
        "cost": cost,
        "disposition": disposition,
    }


def sweep_research_state(root: Path) -> dict[str, Any]:
    """Register surviving research state directly with completion assessment."""
    require_v4_campaign(root)
    if not enabled(root, "automatic_frontier_sweep"):
        return {"schema": schema_for(root), "kind": "research-state-sweep", "created_at": utc_now(), "open": [], "risks": [], "invalid": []}
    open_items: list[dict[str, str]] = []
    risks: list[dict[str, str]] = []
    invalid: list[dict[str, str]] = []

    for path in sorted((root / "continuations").glob("CONT-*.json")):
        record = read_json(path)
        status = str(record.get("status"))
        if status not in {"resolved", "refuted"}:
            prerequisite = record.get("selected_prerequisite", {})
            open_items.append(_entry(
                source=str(record.get("id")),
                kind="continuation",
                reason=f"{record.get('closure_mode')} closure remains {status}: {prerequisite.get('predicate', 'unknown prerequisite')}",
                next_action=(record.get("reachability", {}).get("writer_paths") or [{}])[0].get("next_probe") or "execute the selected prerequisite predicate and preserve inherited assertions",
                cost="medium",
            ))

    for path in sorted((root / "compositions").glob("PGRAPH-*.json")):
        graph = read_json(path)
        for node in graph.get("nodes", []):
            status = str(node.get("status"))
            if status in {"open", "narrowed"}:
                open_items.append(_entry(
                    source=f"{graph.get('id')}:{node.get('id')}", kind="prerequisite",
                    reason=f"prerequisite remains {status}: {node.get('predicate')}",
                    next_action="execute a transition satisfying or refuting this exact predicate",
                ))
            elif status == "blocked":
                risks.append(_entry(
                    source=f"{graph.get('id')}:{node.get('id')}", kind="external-prerequisite",
                    reason=f"prerequisite is blocked: {node.get('predicate')}",
                    next_action="record the external resolution condition",
                    disposition="blocked",
                ))
    for path in sorted((root / "compositions").glob("BRANCH-*.json")):
        branch = read_json(path)
        if branch.get("status") == "open":
            open_items.append(_entry(
                source=str(branch.get("id")), kind="backtracking",
                reason=f"evidence-driven revision remains untested: {branch.get('revision')}",
                next_action="execute the revision and re-check every preserved assertion",
            ))

    components = [read_json(path) for path in sorted((root / "compositions").glob("COMP-*.json"))]
    compositions = [read_json(path) for path in sorted((root / "compositions").glob("COMPOSE-*.json"))]
    composed_ids = {str(item.get(field)) for item in compositions for field in ("left_component", "right_component")}
    if len(components) >= 2:
        for component in components:
            if str(component.get("id")) not in composed_ids:
                open_items.append(_entry(
                    source=str(component.get("id")), kind="composition",
                    reason="grounded executable component has not received an executable compatibility experiment",
                    next_action="test sequential, nested, or temporal compatibility against another grounded component",
                    priority="medium", cost="medium",
                ))
    from .composition import verify_composition

    for composition in compositions:
        try:
            checked = verify_composition(root, str(composition["id"]))
        except (A1XError, OSError, ValueError) as exc:
            checked = {"valid": False, "errors": [f"composition verification failed: {type(exc).__name__}: {exc}"]}
        if not checked["valid"]:
            invalid.append(_entry(
                source=str(composition["id"]), kind="composition-integrity",
                reason="; ".join(checked["errors"]), next_action="restore exact execution and replay evidence",
            ))

    for path in sorted((root / "actors").glob("ACTORS-*.json")):
        program = read_json(path)
        if program.get("status") != "executed":
            open_items.append(_entry(
                source=str(program.get("id")), kind="actor-program",
                reason="declared multi-actor or temporal program has not executed",
                next_action="execute and cleanly replay every declared actor step",
                priority="medium", cost="low",
            ))

    for path in sorted((root / "solver-jobs").glob("SOLVER-*.json")):
        job = read_json(path)
        if job.get("result", {}).get("satisfiable") is True and job.get("status") != "concretely-replayed":
            open_items.append(_entry(
                source=str(job.get("id")), kind="solver-validation",
                reason="solver counterexample or boundary has not been replayed against the executable target",
                next_action="concretely execute the model and replay the exact run",
                priority="medium", cost="low",
            ))

    for path in sorted((root / "harnesses").glob("HTASK-*.json")):
        task = read_json(path)
        if task.get("status") == "open":
            open_items.append(_entry(
                source=str(task.get("id")), kind="harness-expansion",
                reason=str(task.get("reason")), next_action=str(task.get("experiment")),
                priority="high", cost="medium",
            ))
        elif task.get("status") == "blocked":
            risks.append(_entry(
                source=str(task.get("id")), kind="tooling",
                reason=str(task.get("resolution")), next_action="satisfy the recorded harness-expansion blocker",
                disposition="blocked",
            ))

    for path in sorted((root / "scale").glob("EVOLVE-*.json")):
        evolution = read_json(path)
        protected = any(int(item.get("protected_unresolved_leads", 0)) > 0 for item in evolution.get("history", []))
        reason = str(evolution.get("stop_reason"))
        if protected and reason == "generation-budget":
            risks.append(_entry(
                source=str(evolution.get("id")), kind="budget",
                reason="generation budget ended while a protected lineage remained unresolved",
                next_action="increase the bounded adaptive-depth allowance or close the lineage with evidence",
                disposition="blocked",
            ))
        elif reason == "protected-witness-closure-failed":
            risks.append(_entry(
                source=str(evolution.get("id")), kind="tooling",
                reason="protected closure failed operationally after its retry",
                next_action="repair the execution environment and resume the protected lineage",
                disposition="blocked",
            ))

    key = lambda item: (item["kind"], item["source"], item["reason"])
    record = {
        "schema": schema_for(root),
        "kind": "research-state-sweep",
        "created_at": utc_now(),
        "open": sorted({key(item): item for item in open_items}.values(), key=key),
        "risks": sorted({key(item): item for item in risks}.values(), key=key),
        "invalid": sorted({key(item): item for item in invalid}.values(), key=key),
        "policy": "silence is not closure; every surviving executable lead remains visible until resolved, refuted, or explicitly blocked",
    }
    write_json_atomic(root / "orchestration" / "research-state-sweep.json", record)
    return record
