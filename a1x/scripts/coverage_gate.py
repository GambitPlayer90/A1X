#!/usr/bin/env python3
"""Fail when X-Ray leaves a scoped file, entry point, or graph category unexplained."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

FILE_STATUSES = {"analyzed", "dependency-only", "inactive", "unreachable", "excluded"}
ENTRY_DISPOSITIONS = {"analyzed", "not-applicable"}
READ_DISPOSITIONS = {"analyzed", "not-security-relevant"}


def _load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(str(item).strip() for item in value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entry-points", required=True, type=Path)
    parser.add_argument("--coverage-map", required=True, type=Path)
    parser.add_argument("--graph-summary", type=Path)
    args = parser.parse_args()

    scan = _load(args.entry_points)
    coverage = _load(args.coverage_map)
    errors: list[str] = []

    if scan.get("schema_version") != 2:
        errors.append("entry-point scan must use schema_version 2")
    if scan.get("path_basis") != "root-relative":
        errors.append("entry-point scan must use root-relative paths")
    if scan.get("scope_mode") not in {"paths", "manifest"} or not _nonempty_list(scan.get("scope_inputs")):
        errors.append("entry-point scan must preserve scope_mode and non-empty scope_inputs")
    if not isinstance(scan.get("entry_points"), list) or not isinstance(scan.get("read_surfaces"), list):
        errors.append("entry-point scan must include entry_points and read_surfaces arrays")
    if scan.get("problems"):
        errors.append("entry-point scan contains unreadable or skipped paths")
    if coverage.get("schema_version") != 1:
        errors.append("coverage map must use schema_version 1")

    scanned_files = [str(path) for path in scan.get("files") or []]
    expected_files = set(scanned_files)
    if len(scanned_files) != len(expected_files):
        errors.append("entry-point scan contains duplicate files")
    source_inventory = scan.get("source_inventory")
    if not isinstance(source_inventory, list):
        errors.append("entry-point scan must contain a source_inventory array")
        source_inventory = []
    inventory_paths = [str(row.get("path")) for row in source_inventory if isinstance(row, dict)]
    if len(inventory_paths) != len(source_inventory) or len(inventory_paths) != len(set(inventory_paths)):
        errors.append("entry-point source inventory contains malformed or duplicate rows")
    if set(inventory_paths) != expected_files:
        errors.append("entry-point source inventory does not match scanned files")
    for row in source_inventory:
        if not isinstance(row, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("sha256") or "")):
            errors.append(f"{row.get('path') if isinstance(row, dict) else '<invalid>'}: invalid source sha256")
    file_rows = coverage.get("files") or []
    actual_file_list = [str(row.get("path")) for row in file_rows if isinstance(row, dict)]
    actual_files = set(actual_file_list)
    if len(actual_file_list) != len(actual_files):
        errors.append("coverage map contains duplicate file rows")
    if expected_files != actual_files:
        errors.append(
            f"file coverage mismatch: missing={sorted(expected_files-actual_files)} "
            f"extra={sorted(actual_files-expected_files)}"
        )
    for row in file_rows:
        if not isinstance(row, dict):
            errors.append("file coverage rows must be objects")
            continue
        if row.get("status") not in FILE_STATUSES:
            errors.append(f"{row.get('path')}: invalid file status {row.get('status')!r}")
        if not _nonempty_list(row.get("evidence")):
            errors.append(f"{row.get('path')}: file evidence is required")

    expected_entry_list = [
        str(row.get("id")) for row in scan.get("entry_points") or [] if isinstance(row, dict)
    ]
    expected_entries = set(expected_entry_list)
    if len(expected_entry_list) != len(expected_entries) or "None" in expected_entries:
        errors.append("entry-point scan contains duplicate or missing IDs")
    entry_rows = coverage.get("entry_points") or []
    actual_entry_list = [str(row.get("id")) for row in entry_rows if isinstance(row, dict)]
    actual_entries = set(actual_entry_list)
    if len(actual_entry_list) != len(actual_entries):
        errors.append("coverage map contains duplicate entry-point rows")
    if expected_entries != actual_entries:
        errors.append(
            f"entry-point coverage mismatch: missing={sorted(expected_entries-actual_entries)} "
            f"extra={sorted(actual_entries-expected_entries)}"
        )
    for row in entry_rows:
        if not isinstance(row, dict):
            errors.append("entry-point coverage rows must be objects")
            continue
        entry_id = row.get("id")
        if row.get("disposition") not in ENTRY_DISPOSITIONS:
            errors.append(f"{entry_id}: invalid entry disposition {row.get('disposition')!r}")
        for field in ("access", "actor", "state_transition", "value_flow"):
            if not str(row.get(field) or "").strip():
                errors.append(f"{entry_id}: {field} is required")
        if not _nonempty_list(row.get("obligations")):
            errors.append(f"{entry_id}: at least one obligation or non-applicability reason is required")
        if not _nonempty_list(row.get("evidence")):
            errors.append(f"{entry_id}: entry-point evidence is required")

    expected_reader_list = [
        str(row.get("id")) for row in scan.get("read_surfaces") or [] if isinstance(row, dict)
    ]
    expected_readers = set(expected_reader_list)
    if len(expected_reader_list) != len(expected_readers) or "None" in expected_readers:
        errors.append("read-surface scan contains duplicate or missing IDs")
    reader_rows = coverage.get("read_surfaces")
    if not isinstance(reader_rows, list):
        errors.append("coverage map must contain a read_surfaces array")
        reader_rows = []
    actual_reader_list = [str(row.get("id")) for row in reader_rows if isinstance(row, dict)]
    actual_readers = set(actual_reader_list)
    if len(actual_reader_list) != len(actual_readers):
        errors.append("coverage map contains duplicate read-surface rows")
    if expected_readers != actual_readers:
        errors.append(
            f"read-surface coverage mismatch: missing={sorted(expected_readers-actual_readers)} "
            f"extra={sorted(actual_readers-expected_readers)}"
        )
    for row in reader_rows:
        if not isinstance(row, dict):
            errors.append("read-surface coverage rows must be objects")
            continue
        reader_id = row.get("id")
        if row.get("disposition") not in READ_DISPOSITIONS:
            errors.append(f"{reader_id}: invalid read-surface disposition {row.get('disposition')!r}")
        for field in ("consumer_role", "observation_timing"):
            if not str(row.get(field) or "").strip():
                errors.append(f"{reader_id}: {field} is required")
        for field in ("dependencies", "external_consumers", "obligations", "evidence"):
            if not _nonempty_list(row.get(field)):
                errors.append(f"{reader_id}: non-empty {field} is required")

    if args.graph_summary and args.graph_summary.is_file():
        graph = _load(args.graph_summary)
        graph_files = [str(path) for path in graph.get("expected_solidity_files") or []]
        graph_file_set = set(graph_files)
        if len(graph_files) != len(graph_file_set):
            errors.append("Graphify summary contains duplicate expected Solidity files")
        if set(scanned_files) != graph_file_set:
            errors.append(
                "entry-point scanner/Graphify scope mismatch: "
                f"missing={sorted(graph_file_set-set(scanned_files))} "
                f"extra={sorted(set(scanned_files)-graph_file_set)}"
            )
        if graph.get("missing_solidity_files"):
            errors.append(f"Graphify missed Solidity files: {graph['missing_solidity_files']}")
        if graph.get("unexpected_solidity_files"):
            errors.append(f"Graphify included unexpected Solidity files: {graph['unexpected_solidity_files']}")
        review = coverage.get("graph_review") or {}
        reviewed_relations = set(review.get("reviewed_relations") or [])
        filtered_relations = set((review.get("filtered_relations") or {}).keys())
        expected_relations = set((graph.get("relation_counts") or {}).keys())
        if reviewed_relations & filtered_relations:
            errors.append("Graphify relation categories cannot be both reviewed and filtered")
        if reviewed_relations | filtered_relations != expected_relations:
            errors.append("Graphify relation categories are not fully reviewed or filtered")
        reviewed_kinds = set(review.get("reviewed_node_kinds") or [])
        filtered_kinds = set((review.get("filtered_node_kinds") or {}).keys())
        expected_kinds = set((graph.get("node_kind_counts") or {}).keys())
        if reviewed_kinds & filtered_kinds:
            errors.append("Graphify node kinds cannot be both reviewed and filtered")
        if reviewed_kinds | filtered_kinds != expected_kinds:
            errors.append("Graphify node kinds are not fully reviewed or filtered")
        for label, reasons in (
            ("filtered_relations", review.get("filtered_relations") or {}),
            ("filtered_node_kinds", review.get("filtered_node_kinds") or {}),
        ):
            if any(not str(reason).strip() for reason in reasons.values()):
                errors.append(f"{label} requires a reason for every filtered category")

    if errors:
        print("coverage gate failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(
        f"coverage gate passed: {len(expected_files)} files, "
        f"{len(expected_entries)} entry points, {len(expected_readers)} read surfaces"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
