#!/usr/bin/env python3
"""Summarize Graphify structural evidence without loading the full graph into context."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path


def _relative_solidity_files(root: Path) -> list[str]:
    return sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.sol")
        if path.is_file()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", required=True, type=Path)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    graph_path = args.graph.resolve()
    source_root = args.source_root.resolve()
    payload = json.loads(graph_path.read_text(encoding="utf-8"))
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise SystemExit("graph.json must contain node and edge arrays")

    by_id = {str(node.get("id")): node for node in nodes if node.get("id") is not None}
    source_files = sorted(
        {
            str(node.get("source_file"))
            for node in nodes
            if str(node.get("source_file") or "").endswith(".sol")
        }
    )
    expected = _relative_solidity_files(source_root)
    node_kinds = collections.Counter(
        str((node.get("metadata") or {}).get("kind") or "unknown") for node in nodes
    )
    relations = collections.Counter(str(edge.get("relation") or "unknown") for edge in edges)
    degree: collections.Counter[str] = collections.Counter()
    cross_file_relations: collections.Counter[str] = collections.Counter()
    for edge in edges:
        source_id, target_id = str(edge.get("source")), str(edge.get("target"))
        degree[source_id] += 1
        degree[target_id] += 1
        source_file = str((by_id.get(source_id) or {}).get("source_file") or "")
        target_file = str((by_id.get(target_id) or {}).get("source_file") or "")
        if source_file and target_file and source_file != target_file:
            cross_file_relations[str(edge.get("relation") or "unknown")] += 1

    hubs = []
    for node_id, count in degree.most_common(30):
        node = by_id.get(node_id) or {}
        hubs.append(
            {
                "id": node_id,
                "label": node.get("label"),
                "kind": (node.get("metadata") or {}).get("kind"),
                "source_file": node.get("source_file"),
                "degree": count,
            }
        )

    raw = graph_path.read_bytes()
    summary = {
        "schema_version": 1,
        "path_basis": "source-root-relative",
        "graph_sha256": hashlib.sha256(raw).hexdigest(),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "node_kind_counts": dict(sorted(node_kinds.items())),
        "relation_counts": dict(sorted(relations.items())),
        "cross_file_relation_counts": dict(sorted(cross_file_relations.items())),
        "expected_solidity_files": expected,
        "represented_solidity_files": source_files,
        "missing_solidity_files": sorted(set(expected) - set(source_files)),
        "unexpected_solidity_files": sorted(set(source_files) - set(expected)),
        "hubs": hubs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(
        f"graph-summary: {len(nodes)} nodes, {len(edges)} edges, "
        f"{len(summary['missing_solidity_files'])} missing Solidity files"
    )
    return 0 if nodes and not summary["missing_solidity_files"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
