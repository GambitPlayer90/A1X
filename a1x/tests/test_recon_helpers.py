from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
ENTRY_POINTS = SKILL_ROOT / "scripts" / "entry_points.py"
COVERAGE_GATE = SKILL_ROOT / "scripts" / "coverage_gate.py"


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_entry_inventory_keeps_interfaces_and_uses_root_relative_paths(tmp_path: Path) -> None:
    source = tmp_path / "src"
    interfaces = source / "interfaces"
    interfaces.mkdir(parents=True)
    (source / "A.sol").write_text(
        "contract A { uint x; function f() external { x += 1; } }",
        encoding="utf-8",
    )
    (interfaces / "IA.sol").write_text(
        "interface IA { function f() external; }",
        encoding="utf-8",
    )
    output = tmp_path / "entry-points.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ENTRY_POINTS),
            str(source),
            "--root",
            str(source),
            "--json-output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["files"] == ["A.sol", "interfaces/IA.sol"]
    assert [row["path"] for row in payload["entry_points"]] == ["A.sol"]


def _gate_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    scan = tmp_path / "scan.json"
    coverage = tmp_path / "coverage.json"
    graph = tmp_path / "graph.json"
    _write_json(
        scan,
        {"schema_version": 1, "files": ["A.sol", "B.sol"], "entry_points": []},
    )
    _write_json(
        coverage,
        {
            "schema_version": 1,
            "files": [
                {"path": "A.sol", "status": "analyzed", "evidence": ["A:1"]},
                {"path": "B.sol", "status": "dependency-only", "evidence": ["B:1"]},
            ],
            "entry_points": [],
            "graph_review": {
                "reviewed_relations": ["calls"],
                "filtered_relations": {},
                "reviewed_node_kinds": ["function"],
                "filtered_node_kinds": {},
            },
        },
    )
    _write_json(
        graph,
        {
            "expected_solidity_files": ["A.sol", "B.sol"],
            "missing_solidity_files": [],
            "unexpected_solidity_files": [],
            "relation_counts": {"calls": 1},
            "node_kind_counts": {"function": 1},
        },
    )
    return scan, coverage, graph


def _run_gate(paths: tuple[Path, Path, Path]) -> subprocess.CompletedProcess[str]:
    scan, coverage, graph = paths
    return subprocess.run(
        [
            sys.executable,
            str(COVERAGE_GATE),
            "--entry-points",
            str(scan),
            "--coverage-map",
            str(coverage),
            "--graph-summary",
            str(graph),
        ],
        text=True,
        capture_output=True,
        check=False,
    )


def test_coverage_gate_matches_scanner_to_graph_inventory(tmp_path: Path) -> None:
    paths = _gate_fixture(tmp_path)
    result = _run_gate(paths)
    assert result.returncode == 0, result.stdout + result.stderr


def test_coverage_gate_rejects_scanner_graph_omission(tmp_path: Path) -> None:
    scan, coverage, graph = _gate_fixture(tmp_path)
    _write_json(scan, {"schema_version": 1, "files": ["A.sol"], "entry_points": []})
    _write_json(
        coverage,
        {
            "schema_version": 1,
            "files": [{"path": "A.sol", "status": "analyzed", "evidence": ["A:1"]}],
            "entry_points": [],
            "graph_review": {
                "reviewed_relations": ["calls"],
                "filtered_relations": {},
                "reviewed_node_kinds": ["function"],
                "filtered_node_kinds": {},
            },
        },
    )

    result = _run_gate((scan, coverage, graph))
    assert result.returncode == 1
    assert "entry-point scanner/Graphify scope mismatch" in result.stdout
    assert "B.sol" in result.stdout
