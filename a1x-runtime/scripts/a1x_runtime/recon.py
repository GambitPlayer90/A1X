from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import (
    digest_bytes,
    digest_json,
    exclusive_lock,
    read_json,
    seal,
    verify_seal,
    write_json_atomic,
    write_text_atomic,
)
from .errors import IntegrityError, ValidationError
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now


FILE_STATUSES = {"analyzed", "dependency-only", "inactive", "unreachable", "excluded"}
ENTRY_DISPOSITIONS = {"analyzed", "not-applicable"}
READ_DISPOSITIONS = {"analyzed", "not-security-relevant"}


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and bool(value) and all(str(item).strip() for item in value)


def _coverage_errors(
    scan: dict[str, Any],
    coverage: dict[str, Any],
    graph: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    if scan.get("schema_version") != 1 or scan.get("path_basis") != "root-relative":
        errors.append("entry-point scan must use schema_version 1 and root-relative paths")
    if scan.get("scope_mode") not in {"paths", "manifest"} or not _nonempty_list(scan.get("scope_inputs")):
        errors.append("entry-point scan must preserve its scope mode and non-empty scope inputs")
    if not isinstance(scan.get("entry_points"), list) or not isinstance(scan.get("read_surfaces"), list):
        errors.append("entry-point scan must include entry_points and read_surfaces arrays")
    if scan.get("problems"):
        errors.append("entry-point scan contains unreadable or skipped paths")
    if coverage.get("schema_version") != 1:
        errors.append("coverage map must use schema_version 1")

    scanned_files = [str(path) for path in scan.get("files") or []]
    expected_files = set(scanned_files)
    file_rows = coverage.get("files")
    if not isinstance(file_rows, list):
        errors.append("coverage map must include a files array")
        file_rows = []
    actual_file_list = [str(row.get("path")) for row in file_rows if isinstance(row, dict)]
    actual_files = set(actual_file_list)
    if len(scanned_files) != len(expected_files) or len(actual_file_list) != len(actual_files):
        errors.append("source or coverage inventory contains duplicate file paths")
    if expected_files != actual_files:
        errors.append("coverage map does not exactly match the scanned Solidity files")
    for row in file_rows:
        if not isinstance(row, dict):
            errors.append("file coverage rows must be objects")
        elif row.get("status") not in FILE_STATUSES or not _nonempty_list(row.get("evidence")):
            errors.append(f"{row.get('path')}: invalid file coverage status or evidence")

    def reconcile(
        scan_field: str,
        coverage_field: str,
        dispositions: set[str],
        required_text: tuple[str, ...],
        required_lists: tuple[str, ...],
    ) -> None:
        expected_list = [str(row.get("id")) for row in scan.get(scan_field) or [] if isinstance(row, dict)]
        rows = coverage.get(coverage_field)
        if not isinstance(rows, list):
            errors.append(f"coverage map must include a {coverage_field} array")
            rows = []
        actual_list = [str(row.get("id")) for row in rows if isinstance(row, dict)]
        if len(expected_list) != len(set(expected_list)) or "None" in expected_list:
            errors.append(f"{scan_field} contains duplicate or missing IDs")
        if len(actual_list) != len(set(actual_list)) or set(expected_list) != set(actual_list):
            errors.append(f"{coverage_field} does not exactly match the deterministic inventory")
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"{coverage_field} rows must be objects")
                continue
            if row.get("disposition") not in dispositions:
                errors.append(f"{row.get('id')}: invalid {coverage_field} disposition")
            for field in required_text:
                if not str(row.get(field) or "").strip():
                    errors.append(f"{row.get('id')}: {field} is required")
            for field in required_lists:
                if not _nonempty_list(row.get(field)):
                    errors.append(f"{row.get('id')}: non-empty {field} is required")

    reconcile(
        "entry_points",
        "entry_points",
        ENTRY_DISPOSITIONS,
        ("access", "actor", "state_transition", "value_flow"),
        ("obligations", "evidence"),
    )
    reconcile(
        "read_surfaces",
        "read_surfaces",
        READ_DISPOSITIONS,
        ("consumer_role", "observation_timing"),
        ("dependencies", "external_consumers", "obligations", "evidence"),
    )

    if graph is not None:
        graph_files = [str(path) for path in graph.get("expected_solidity_files") or []]
        if len(graph_files) != len(set(graph_files)) or set(graph_files) != expected_files:
            errors.append("Graphify scope does not exactly match the deterministic source inventory")
        if graph.get("missing_solidity_files") or graph.get("unexpected_solidity_files"):
            errors.append("Graphify omitted or added Solidity files")
        review = coverage.get("graph_review") or {}
        for expected_field, reviewed_field, filtered_field in (
            ("relation_counts", "reviewed_relations", "filtered_relations"),
            ("node_kind_counts", "reviewed_node_kinds", "filtered_node_kinds"),
        ):
            expected = set((graph.get(expected_field) or {}).keys())
            reviewed = set(review.get(reviewed_field) or [])
            filtered = set((review.get(filtered_field) or {}).keys())
            if reviewed & filtered or reviewed | filtered != expected:
                errors.append(f"Graphify {expected_field} categories are not fully and uniquely reconciled")
            if any(not str(reason).strip() for reason in (review.get(filtered_field) or {}).values()):
                errors.append(f"{filtered_field} requires a reason for every category")
    return errors


def _source_inventory(campaign: dict[str, Any], scan: dict[str, Any]) -> list[dict[str, str]]:
    source = Path(str(campaign.get("source", {}).get("path") or "")).resolve()
    scope_inputs = [Path(str(raw)) for raw in scan.get("scope_inputs") or []]
    for relative in scope_inputs:
        if relative.is_absolute() or ".." in relative.parts:
            raise ValidationError(f"unsafe source scope input: {relative}")
    expected_files = {str(raw) for raw in scan.get("files") or []}
    if scan.get("scope_mode") == "manifest":
        if {path.as_posix() for path in scope_inputs} != expected_files:
            raise IntegrityError("source manifest no longer matches the recorded Solidity inventory")
    else:
        discovered: set[str] = set()
        for relative in scope_inputs:
            target = (source / relative).resolve()
            try:
                target.relative_to(source)
            except ValueError as exc:
                raise ValidationError(f"source scope input escapes source root: {relative}") from exc
            if target.is_file() and target.suffix == ".sol":
                discovered.add(target.relative_to(source).as_posix())
            elif target.is_dir():
                for candidate in target.rglob("*.sol"):
                    resolved = candidate.resolve()
                    try:
                        discovered.add(resolved.relative_to(source).as_posix())
                    except ValueError as exc:
                        raise ValidationError(f"scoped Solidity path escapes source root: {candidate}") from exc
            else:
                raise ValidationError(f"source scope input is missing or not Solidity: {relative}")
        if discovered != expected_files:
            raise IntegrityError(
                "current scoped Solidity manifest differs from recon inventory: "
                f"missing={sorted(expected_files-discovered)} extra={sorted(discovered-expected_files)}"
            )
    inventory: list[dict[str, str]] = []
    for raw in scan.get("files") or []:
        relative = Path(str(raw))
        if relative.is_absolute() or ".." in relative.parts or relative.suffix != ".sol":
            raise ValidationError(f"unsafe scoped Solidity path: {raw}")
        path = (source / relative).resolve()
        try:
            path.relative_to(source)
        except ValueError as exc:
            raise ValidationError(f"scoped Solidity path escapes source root: {raw}") from exc
        if not path.is_file():
            raise ValidationError(f"scoped Solidity file is missing: {raw}")
        inventory.append({"path": relative.as_posix(), "sha256": digest_bytes(path.read_bytes())})
    return inventory


def record_coverage_gate(
    root: Path,
    *,
    entry_points_path: Path,
    coverage_map_path: Path,
    graph_summary_path: Path | None = None,
) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    scan = read_json(entry_points_path)
    coverage = read_json(coverage_map_path)
    graph = read_json(graph_summary_path) if graph_summary_path else None
    errors = _coverage_errors(scan, coverage, graph)
    if errors:
        raise ValidationError("recon coverage gate failed: " + "; ".join(errors))
    inventory = _source_inventory(campaign, scan)
    record_id = allocate_id(root, "RECONCOV")
    directory = root / "recon" / "coverage-gates" / record_id
    directory.mkdir(parents=True)
    snapshots = {
        "entry_points": (directory / "entry-points.json", scan),
        "coverage_map": (directory / "coverage-map.json", coverage),
    }
    if graph is not None:
        snapshots["graph_summary"] = (directory / "graph-summary.json", graph)
    hashes: dict[str, str] = {}
    for name, (path, payload) in snapshots.items():
        write_json_atomic(path, payload, mode=0o444)
        hashes[name] = seal(path, path.with_suffix(".sha256"))
    record = {
        "schema": schema_for(root),
        "kind": "recon-coverage-attestation",
        "id": record_id,
        "created_at": utc_now(),
        "status": "passed",
        "input_sha256": hashes,
        "source_inventory": inventory,
        "source_inventory_sha256": digest_json(inventory),
        "file_count": len(scan.get("files") or []),
        "entry_point_count": len(scan.get("entry_points") or []),
        "read_surface_count": len(scan.get("read_surfaces") or []),
    }
    write_json_atomic(directory / "record.json", record, mode=0o444)
    seal(directory / "record.json", directory / "record.sha256")
    write_text_atomic(root / "recon" / "COVERAGE_ACTIVE", record_id + "\n")
    event(root, "recon.coverage-attested", recon_coverage_id=record_id, source_inventory_sha256=record["source_inventory_sha256"])
    return record


def verify_coverage_gate(root: Path) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    pointer = root / "recon" / "COVERAGE_ACTIVE"
    if not pointer.is_file():
        raise ValidationError("no active recon coverage attestation")
    record_id = pointer.read_text(encoding="utf-8").strip()
    if not record_id.startswith("RECONCOV-"):
        raise IntegrityError("invalid recon coverage pointer")
    directory = root / "recon" / "coverage-gates" / record_id
    verify_seal(directory / "record.json", directory / "record.sha256")
    record = read_json(directory / "record.json")
    if record.get("id") != record_id or record.get("status") != "passed":
        raise IntegrityError("recon coverage attestation identity/status mismatch")
    payloads: dict[str, dict[str, Any]] = {}
    names = {
        "entry_points": "entry-points",
        "coverage_map": "coverage-map",
        "graph_summary": "graph-summary",
    }
    for key, stem in names.items():
        expected = record.get("input_sha256", {}).get(key)
        path = directory / f"{stem}.json"
        if expected is None:
            if key != "graph_summary":
                raise IntegrityError(f"recon coverage attestation lacks {key}")
            continue
        verify_seal(path, directory / f"{stem}.sha256")
        actual = digest_bytes(path.read_bytes())
        if actual != expected:
            raise IntegrityError(f"recon coverage input hash changed: {key}")
        payloads[key] = read_json(path)
    errors = _coverage_errors(
        payloads["entry_points"],
        payloads["coverage_map"],
        payloads.get("graph_summary"),
    )
    if errors:
        raise IntegrityError("sealed recon coverage no longer validates: " + "; ".join(errors))
    inventory = _source_inventory(campaign, payloads["entry_points"])
    if inventory != record.get("source_inventory") or digest_json(inventory) != record.get("source_inventory_sha256"):
        raise IntegrityError("scoped Solidity source changed after recon coverage attestation")
    return {"valid": True, **record}


def create_recon_pack(
    root: Path, *, facts: list[dict[str, Any]], unknowns: list[dict[str, Any]], artifact_ids: list[str], parent: str | None = None
) -> dict[str, Any]:
    require_v4_campaign(root)
    if not facts and not unknowns:
        raise ValidationError("Recon Pack requires at least one fact or explicit unknown")
    for fact in facts:
        if not all(isinstance(fact.get(key), str) and fact[key].strip() for key in ("statement", "source", "confidence")):
            raise ValidationError("each recon fact needs statement, source, and confidence")
    for unknown in unknowns:
        if not all(isinstance(unknown.get(key), str) and unknown[key].strip() for key in ("question", "why_it_matters", "next_probe")):
            raise ValidationError("each recon unknown needs question, why_it_matters, and next_probe")
    for artifact_id in artifact_ids:
        if not (root / "evidence" / f"{artifact_id}.json").is_file():
            raise ValidationError(f"unknown artifact: {artifact_id}")
    with exclusive_lock(root):
        versions = sorted(path for path in (root / "recon").glob("v[0-9][0-9][0-9][0-9]") if path.is_dir())
        number = int(versions[-1].name[1:]) + 1 if versions else 1
        version = f"v{number:04d}"
        resolved_parent = parent
        if resolved_parent is None and versions:
            resolved_parent = versions[-1].name
        if resolved_parent and not (root / "recon" / resolved_parent / "manifest.json").is_file():
            raise ValidationError(f"unknown parent Recon Pack: {resolved_parent}")
        manifest = {
            "schema": schema_for(root), "kind": "recon-pack", "version": version,
            "created_at": utc_now(), "parent": resolved_parent, "facts": facts, "unknowns": unknowns,
            "artifact_ids": artifact_ids, "source_digest": require_v4_campaign(root)["source"]["initial_digest"],
        }
        manifest["manifest_sha256"] = digest_json(manifest)
        directory = root / "recon" / version
        directory.mkdir()
        write_json_atomic(directory / "manifest.json", manifest, mode=0o444)
        write_text_atomic(root / "recon" / "ACTIVE", version + "\n", mode=0o644)
        event(root, "recon.created", version=version, manifest_sha256=manifest["manifest_sha256"])
        return manifest


def active_recon(root: Path) -> dict[str, Any] | None:
    pointer = root / "recon" / "ACTIVE"
    if not pointer.is_file():
        return None
    version = pointer.read_text(encoding="utf-8").strip()
    return read_json(root / "recon" / version / "manifest.json")
