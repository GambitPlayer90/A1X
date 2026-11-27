from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import read_json, write_json_atomic
from .errors import IntegrityError, ValidationError
from .evidence import normalize_evidence_refs, verify_evidence_refs
from .features import enabled
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now, validate_id


STATES = {"open", "narrowed", "blocked", "resolved", "refuted"}
KINDS = {"capital", "state", "authority", "timing", "numeric", "deployment", "environment", "settlement", "other"}
REVISION_SCOPES = {"parameter", "ordering", "actor", "action", "joint"}


def _text(value: Any, field: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise ValidationError(f"prerequisite {field} must be non-empty")
    return result


def _acyclic(nodes: dict[str, dict[str, Any]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ValidationError(f"prerequisite dependency cycle includes {node_id}")
        if node_id in visited:
            return
        visiting.add(node_id)
        for dependency in nodes[node_id]["dependencies"]:
            visit(dependency)
        visiting.remove(node_id)
        visited.add(node_id)

    for node_id in nodes:
        visit(node_id)


def create_prerequisite_graph(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    require_v4_campaign(root)
    if not enabled(root, "prerequisite_graph"):
        raise ValidationError("prerequisite graphs are disabled by runtime feature policy")
    raw_nodes = payload.get("nodes") if isinstance(payload, dict) else None
    if not isinstance(raw_nodes, list) or not raw_nodes or any(not isinstance(item, dict) for item in raw_nodes):
        raise ValidationError("prerequisite graph requires a non-empty nodes array")
    nodes: dict[str, dict[str, Any]] = {}
    for raw in raw_nodes:
        node_id = _text(raw.get("id"), "node.id")
        if node_id in nodes:
            raise ValidationError(f"duplicate prerequisite node: {node_id}")
        state = str(raw.get("status") or "")
        kind = str(raw.get("kind") or "")
        if state not in STATES or kind not in KINDS:
            raise ValidationError(f"invalid prerequisite kind/status for {node_id}: {kind}/{state}")
        refs = normalize_evidence_refs(
            root,
            raw.get("evidence_refs", []),
            required=state in {"narrowed", "resolved", "refuted"},
        )
        nodes[node_id] = {
            "id": node_id,
            "lineage_id": _text(raw.get("lineage_id"), "node.lineage_id"),
            "description": _text(raw.get("description"), "node.description"),
            "predicate": _text(raw.get("predicate"), "node.predicate"),
            "kind": kind,
            "status": state,
            "dependencies": [str(item) for item in raw.get("dependencies", [])],
            "conflicts": [str(item) for item in raw.get("conflicts", [])],
            "preserves": [str(item) for item in raw.get("preserves", [])],
            "evidence_refs": refs,
        }
    for node in nodes.values():
        for field in ("dependencies", "conflicts"):
            unknown = set(node[field]) - set(nodes)
            if unknown:
                raise ValidationError(f"prerequisite {node['id']} has unknown {field}: {sorted(unknown)}")
        if node["id"] in node["dependencies"] or node["id"] in node["conflicts"]:
            raise ValidationError(f"prerequisite {node['id']} cannot depend on or conflict with itself")
    _acyclic(nodes)
    equivalences = []
    for raw in payload.get("equivalences", []):
        if not isinstance(raw, dict):
            raise ValidationError("prerequisite equivalences must contain objects")
        members = sorted(set(str(item) for item in raw.get("members", [])))
        if len(members) < 2 or set(members) - set(nodes):
            raise ValidationError("prerequisite equivalence requires at least two known nodes")
        if len({nodes[item]["lineage_id"] for item in members}) < 2:
            raise ValidationError("cross-lineage equivalence must connect distinct lineages")
        equivalences.append(
            {
                "members": members,
                "predicate": _text(raw.get("predicate"), "equivalence.predicate"),
                "evidence_refs": normalize_evidence_refs(root, raw.get("evidence_refs", []), required=True),
            }
        )
    graph_id = allocate_id(root, "PGRAPH")
    record = {
        "schema": schema_for(root),
        "kind": "prerequisite-graph",
        "id": graph_id,
        "created_at": utc_now(),
        "mechanism": _text(payload.get("mechanism"), "graph.mechanism"),
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "equivalences": equivalences,
        "branches": [],
    }
    write_json_atomic(root / "compositions" / f"{graph_id}.json", record)
    event(root, "prerequisite.graph-created", graph_id=graph_id, nodes=len(nodes), equivalences=len(equivalences))
    return record


def create_backtrack_branch(root: Path, graph_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    graph_id = validate_id(graph_id, "PGRAPH")
    graph_path = root / "compositions" / f"{graph_id}.json"
    graph = read_json(graph_path)
    node_id = _text(payload.get("prerequisite_id"), "backtrack.prerequisite_id")
    nodes = {item["id"]: item for item in graph["nodes"]}
    if node_id not in nodes:
        raise ValidationError(f"unknown prerequisite for backtracking: {node_id}")
    scope = str(payload.get("revision_scope") or "")
    if scope not in REVISION_SCOPES:
        raise ValidationError(f"unsupported backtracking revision scope: {scope}")
    continuation_id = validate_id(_text(payload.get("continuation_id"), "backtrack.continuation_id"), "CONT")
    continuation = read_json(root / "continuations" / f"{continuation_id}.json")
    preserved = sorted(set(str(item) for item in payload.get("preserve_assertions", [])))
    if not preserved or not set(preserved) <= set(continuation.get("preserve_assertions", [])):
        raise ValidationError("backtracking must preserve assertions from the continuation contract")
    evidence_refs = normalize_evidence_refs(root, payload.get("dead_end_evidence_refs", []), required=True)
    branch_id = allocate_id(root, "BRANCH")
    branch = {
        "schema": schema_for(root),
        "kind": "backtrack-branch",
        "id": branch_id,
        "created_at": utc_now(),
        "graph_id": graph_id,
        "prerequisite_id": node_id,
        "continuation_id": continuation_id,
        "revision_scope": scope,
        "dead_end": _text(payload.get("dead_end"), "backtrack.dead_end"),
        "revision": _text(payload.get("revision"), "backtrack.revision"),
        "preserve_assertions": preserved,
        "dead_end_evidence_refs": evidence_refs,
        "status": "open",
        "attempt_id": None,
    }
    write_json_atomic(root / "compositions" / f"{branch_id}.json", branch)
    graph["branches"].append(branch_id)
    write_json_atomic(graph_path, graph)
    event(root, "prerequisite.backtrack-created", graph_id=graph_id, branch_id=branch_id, prerequisite_id=node_id)
    return branch


def resolve_backtrack_branch(root: Path, branch_id: str, *, attempt_id: str) -> dict[str, Any]:
    branch_id = validate_id(branch_id, "BRANCH")
    attempt_id = validate_id(attempt_id, "ATTEMPT")
    path = root / "compositions" / f"{branch_id}.json"
    branch = read_json(path)
    attempt = read_json(root / "continuations" / f"{attempt_id}.json")
    if attempt.get("continuation_id") != branch.get("continuation_id"):
        raise ValidationError("backtracking result must use the branch continuation contract")
    observed = {item["id"]: item["passed"] for item in attempt.get("assertions", [])}
    failed = [item for item in branch["preserve_assertions"] if observed.get(item) is not True]
    if failed:
        raise IntegrityError(f"backtracking invalidated inherited assertions: {failed}")
    branch["attempt_id"] = attempt_id
    branch["status"] = "resolved" if attempt.get("result") in {"advanced", "narrowed", "resolved"} else attempt.get("result")
    write_json_atomic(path, branch)
    event(root, "prerequisite.backtrack-resolved", branch_id=branch_id, attempt_id=attempt_id, status=branch["status"])
    return branch


def verify_prerequisite_graph(root: Path, graph_id: str) -> dict[str, Any]:
    graph_id = validate_id(graph_id, "PGRAPH")
    record = read_json(root / "compositions" / f"{graph_id}.json")
    errors = []
    nodes = {item["id"]: item for item in record.get("nodes", [])}
    try:
        _acyclic(nodes)
    except ValidationError as exc:
        errors.append(str(exc))
    for node in nodes.values():
        errors.extend(verify_evidence_refs(root, node.get("evidence_refs", [])))
    for item in record.get("equivalences", []):
        errors.extend(verify_evidence_refs(root, item.get("evidence_refs", [])))
    return {"graph_id": graph_id, "valid": not errors, "errors": errors, "record": record}
