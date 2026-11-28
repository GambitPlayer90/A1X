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
        "interface IA { function f() external; function quote() external view returns (uint256); }",
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
    assert payload["schema_version"] == 2
    assert payload["files"] == ["A.sol", "interfaces/IA.sol"]
    assert [row["path"] for row in payload["source_inventory"]] == payload["files"]
    assert all(len(row["sha256"]) == 64 for row in payload["source_inventory"])
    assert [row["path"] for row in payload["entry_points"]] == ["A.sol"]
    assert len(payload["read_surfaces"]) == 1
    assert "[interface] IA.quote" in payload["read_surfaces"][0]["declaration"]


def test_reader_inventory_includes_view_function_and_generated_public_getter(tmp_path: Path) -> None:
    source = tmp_path / "src"
    source.mkdir()
    (source / "Oracle.sol").write_text(
        """contract Oracle {
    uint256 public price;
    function quote() external view returns (uint256) { return price; }
    function poke() external { price += 1; }
}
""",
        encoding="utf-8",
    )
    output = tmp_path / "entry-points.json"
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINTS), str(source), "--root", str(source), "--json-output", str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert [row["declaration"].split("(", 1)[0] for row in payload["entry_points"]] == ["Oracle.poke"]
    readers = payload["read_surfaces"]
    assert any("Oracle.quote" in row["declaration"] and row["surface_kind"] == "function" for row in readers)
    assert any("Oracle.price" in row["declaration"] and row["surface_kind"] == "generated-getter" for row in readers)
    assert next(row["line"] for row in readers if "Oracle.price" in row["declaration"]) == 2


def _gate_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    scan = tmp_path / "scan.json"
    coverage = tmp_path / "coverage.json"
    graph = tmp_path / "graph.json"
    _write_json(
        scan,
        {
            "schema_version": 2,
            "path_basis": "root-relative",
            "scope_mode": "manifest",
            "scope_inputs": ["A.sol", "B.sol"],
            "files": ["A.sol", "B.sol"],
            "source_inventory": [
                {"path": "A.sol", "sha256": "a" * 64},
                {"path": "B.sol", "sha256": "b" * 64},
            ],
            "entry_points": [],
            "read_surfaces": [],
            "problems": [],
        },
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
            "read_surfaces": [],
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
    _write_json(
        scan,
        {
            "schema_version": 2,
            "path_basis": "root-relative",
            "scope_mode": "manifest",
            "scope_inputs": ["A.sol"],
            "files": ["A.sol"],
            "source_inventory": [{"path": "A.sol", "sha256": "a" * 64}],
            "entry_points": [],
            "read_surfaces": [],
            "problems": [],
        },
    )
    _write_json(
        coverage,
        {
            "schema_version": 1,
            "files": [{"path": "A.sol", "status": "analyzed", "evidence": ["A:1"]}],
            "entry_points": [],
            "read_surfaces": [],
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


def test_coverage_gate_rejects_missing_reader_classification(tmp_path: Path) -> None:
    scan, coverage, graph = _gate_fixture(tmp_path)
    reader = {
        "id": "A.sol:3:A.quote() external view returns (uint256)",
        "path": "A.sol",
        "line": 3,
        "declaration": "A.quote() external view returns (uint256)",
        "surface_kind": "function",
        "mutability": "view",
    }
    scan_payload = json.loads(scan.read_text(encoding="utf-8"))
    scan_payload["read_surfaces"] = [reader]
    _write_json(scan, scan_payload)
    result = _run_gate((scan, coverage, graph))
    assert result.returncode == 1
    assert "read-surface coverage mismatch" in result.stdout
