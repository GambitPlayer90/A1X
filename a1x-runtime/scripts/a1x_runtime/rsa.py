from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

from .atomic import (
    digest_bytes,
    digest_json,
    exclusive_lock,
    read_json,
    write_json_atomic,
    write_text_atomic,
)
from .errors import BudgetError, IntegrityError, ValidationError
from .evidence_bundles import load_bundle
from .hashing import path_digest
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now
from .witness import fresh_lineage_id

SEMANTIC_DELTA_FIELDS = {
    "new_causal_edge", "new_reachable_waypoint", "resolved_prerequisite", "stronger_oracle",
    "stronger_consumer", "reduced_assumption", "mechanism_specific_refutation",
    "phase_advanced", "cleaner_setup",
}
SEMANTIC_REGRESSION_FIELDS = {"regressed_prerequisite", "tainted_setup"}


def semantic_identity(bundle: dict[str, Any]) -> str:
    payload = bundle.get("payload", {})
    normalized = {
        "writer": payload.get("writer"), "guard": payload.get("guard"), "consumer": payload.get("consumer"),
        "state": payload.get("state"), "property": payload.get("property"),
        "state_fingerprint": payload.get("state_fingerprint"),
        "transition_sequence": payload.get("transition_sequence"),
    }
    return digest_json(normalized)


def compatibility(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    lp, rp = left.get("payload", {}), right.get("payload", {})
    contradictions = []
    for key in ("chain_id", "block_number"):
        lv = (left.get("execution_context") or {}).get(key)
        rv = (right.get("execution_context") or {}).get(key)
        if lv is not None and rv is not None and lv != rv:
            contradictions.append(f"{key} mismatch")
    if left.get("target_sha256") != right.get("target_sha256"):
        contradictions.append("target mismatch")
    edges = []
    if lp.get("consumer") and lp.get("consumer") == rp.get("writer"):
        edges.append("left-consumer-to-right-writer")
    if rp.get("consumer") and rp.get("consumer") == lp.get("writer"):
        edges.append("right-consumer-to-left-writer")
    shared = sorted(set(lp.get("state_keys", [])) & set(rp.get("state_keys", [])))
    topologies = ["sequential"]
    if any(
        value
        for value in (
            lp.get("callback_context"),
            rp.get("callback_context"),
            lp.get("transient_window"),
            rp.get("transient_window"),
        )
    ):
        topologies.append("nested")
    if any(
        value
        for value in (
            lp.get("temporal_context"),
            rp.get("temporal_context"),
            lp.get("block_transition"),
            rp.get("block_transition"),
        )
    ):
        topologies.append("temporal")
    score = len(edges) * 4 + len(shared) + (left.get("payload_type") != right.get("payload_type"))
    return {
        "compatible": not contradictions,
        "contradictions": contradictions,
        "causal_edges": edges,
        "shared_state": shared,
        "composition_topologies": topologies,
        "score": score,
    }


def build_compatibility_graph(root: Path, evidence_ids: list[str], *, idempotency_key: str | None = None, campaign_epoch: int | None = None) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    epoch = int(campaign.get("epoch", 0))
    if campaign_epoch is not None and campaign_epoch != epoch:
        raise ValidationError(f"campaign epoch mismatch: requested {campaign_epoch}, current {epoch}")
    nodes = sorted(set(evidence_ids))
    if len(nodes) < 2:
        raise ValidationError("RSA compatibility graph requires at least two distinct evidence bundles")
    key = idempotency_key or "rsa-graph:" + digest_json(nodes)
    request_hash = digest_json({"campaign_epoch": epoch, "evidence_ids": nodes})
    bundles = {item: load_bundle(root, item) for item in nodes}
    edges = []
    for left_id, right_id in combinations(sorted(bundles), 2):
        result = compatibility(bundles[left_id], bundles[right_id])
        edges.append({"left": left_id, "right": right_id, **result})
    with exclusive_lock(root):
        for path in (root / "rsa").glob("RSA-*.json"):
            existing = read_json(path)
            if existing.get("idempotency_key") != key:
                continue
            existing_hash = existing.get("request_sha256") or digest_json({
                "campaign_epoch": int(existing.get("campaign_epoch", epoch)),
                "evidence_ids": sorted(existing.get("nodes", [])),
            })
            if existing_hash != request_hash:
                raise ValidationError("idempotency key was already used for a different RSA graph request")
            return existing
        graph_id = allocate_id(root, "RSA")
        record = {
            "schema": schema_for(root), "kind": "rsa-compatibility-graph", "id": graph_id,
            "created_at": utc_now(), "nodes": nodes, "edges": edges,
            "campaign_epoch": epoch, "idempotency_key": key, "request_sha256": request_hash,
            "selection_policy": "maximize missing-causal-edge resolution and information gain; preserve incompatible parents",
        }
        write_json_atomic(root / "rsa" / f"{graph_id}.json", record)
        event(root, "rsa.graph-created", rsa_id=graph_id, nodes=len(nodes), edges=len(edges))
        return record


def assess_semantic_delta(delta: dict[str, Any]) -> dict[str, Any]:
    unknown = set(delta) - SEMANTIC_DELTA_FIELDS - SEMANTIC_REGRESSION_FIELDS
    if unknown:
        raise ValidationError(f"unknown semantic delta fields: {sorted(unknown)}")
    achieved = sorted(key for key in SEMANTIC_DELTA_FIELDS if delta.get(key) is True)
    regressions = sorted(key for key in SEMANTIC_REGRESSION_FIELDS if delta.get(key) is True)
    normalized = {
        key: bool(delta.get(key))
        for key in sorted(SEMANTIC_DELTA_FIELDS | SEMANTIC_REGRESSION_FIELDS)
    }
    return {
        "improved": bool(achieved),
        "criteria": achieved,
        "regressed": bool(regressions),
        "regressions": regressions,
        "semantic_delta_sha256": digest_json(normalized),
    }


def _export_bundle(root: Path, destination: Path, bundle: dict[str, Any]) -> None:
    destination.mkdir(parents=True)
    write_json_atomic(destination / "bundle.json", bundle, mode=0o444)
    exported = []
    for artifact_id in bundle.get("artifact_ids", []):
        record = read_json(root / "evidence" / f"{artifact_id}.json")
        source = root / record["object"]
        data = source.read_bytes()
        if digest_bytes(data) != record["sha256"]:
            raise IntegrityError(f"immutable artifact failed verification: {artifact_id}")
        target = destination / record["sha256"]
        target.write_bytes(data)
        target.chmod(0o444)
        exported.append({"artifact_id": artifact_id, "sha256": record["sha256"], "file": target.name})
    write_json_atomic(destination / "manifest.json", {"evidence_id": bundle["id"], "artifacts": exported}, mode=0o444)


def create_evidence_round(root: Path, evidence_ids: list[str], *, children: int, fresh_lanes: int, per_lane_timeout: int) -> dict[str, Any]:
    """Turn cross-backend evidence into executable RSA lanes."""
    from .scale import _lane_prompt

    if children <= 0 or fresh_lanes < 0 or per_lane_timeout <= 0:
        raise ValidationError("evidence RSA requires positive children/timeout and non-negative fresh lanes")

    bundles = {item: load_bundle(root, item) for item in evidence_ids}
    ranked = []
    for left_id, right_id in combinations(sorted(bundles), 2):
        result = compatibility(bundles[left_id], bundles[right_id])
        if result["compatible"]:
            ranked.append((result["score"], left_id, right_id, result))
    ranked.sort(reverse=True)
    if not ranked:
        raise ValidationError("evidence RSA requires at least one compatible pair")
    campaign = require_v4_campaign(root)
    maximum = int(campaign["budgets"].get("max_scale_lanes", 0))
    existing = len(list((root / "scale").glob("ROUND-*/lanes/LANE-*")))
    total = min(children, len(ranked)) + fresh_lanes
    if maximum and existing + total > maximum:
        raise BudgetError(f"max_scale_lanes budget would be exceeded ({maximum})")
    round_id = allocate_id(root, "ROUND")
    directory = root / "scale" / round_id
    lanes_dir = directory / "lanes"
    lanes_dir.mkdir(parents=True)
    lanes = []
    for index, (_, left_id, right_id, result) in enumerate(ranked[:children], start=1):
        lane_id = f"LANE-{index:04d}"
        lane_dir = lanes_dir / lane_id
        lane_dir.mkdir()
        _export_bundle(root, lane_dir / "parent-evidence" / "A", bundles[left_id])
        _export_bundle(root, lane_dir / "parent-evidence" / "B", bundles[right_id])
        prompt = f"""Compose two typed, cross-backend evidence bundles. Their immutable packets will be mounted read-only at `.a1x-parent-evidence/A` and `.a1x-parent-evidence/B`.

Compatibility analysis: {result}

Reconstruct the state prefix and causal prerequisites. Treat native corpus/snapshot formats as supporting artifacts, never interchangeable state. Translate compatible observations into one concrete transaction witness, execute it, and compare it with a causal negative control. If incompatible after inspection, record the exact contradiction and preserve both parents.
"""
        write_text_atomic(lane_dir / "prompt.md", _lane_prompt(lane_id=lane_id, axis=f"evidence-rsa:{left_id}+{right_id}", base_prompt=prompt, hypothesis_id=None))
        lanes.append({
            "lane_id": lane_id,
            "axis": f"evidence-rsa:{left_id}+{right_id}",
            "status": "planned",
            "path": f"lanes/{lane_id}",
            "lane_role": "evidence-recombination",
            "lineage_id": fresh_lineage_id("evidence-composition", left_id, right_id),
            "parent_handoffs": [],
            "evidence_parents": [left_id, right_id],
        })
    for offset in range(fresh_lanes):
        index = len(lanes) + 1
        lane_id = f"LANE-{index:04d}"
        lane_dir = lanes_dir / lane_id
        lane_dir.mkdir()
        write_text_atomic(lane_dir / "prompt.md", _lane_prompt(lane_id=lane_id, axis=f"fresh-evidence-control:{offset + 1}", base_prompt="Independently investigate a different mechanism family and execute the cheapest discriminator. Do not inherit the parent interpretation.", hypothesis_id=None))
        lanes.append({
            "lane_id": lane_id,
            "axis": f"fresh-evidence-control:{offset + 1}",
            "status": "planned",
            "path": f"lanes/{lane_id}",
            "lane_role": "fresh-exploration",
            "lineage_id": fresh_lineage_id("fresh-evidence", round_id, lane_id),
            "parent_handoffs": [],
        })
    plan = {
        "schema": schema_for(root), "kind": "scale-round", "id": round_id, "created_at": utc_now(),
        "hypothesis_id": None, "per_lane_timeout": per_lane_timeout,
        "source_commit": campaign["source"]["git"].get("commit"),
        "source_digest": path_digest(Path(campaign["source"]["path"])), "lanes": lanes,
        "parent_round": None, "purpose": "evidence-recombination", "generation": 1, "status": "planned",
    }
    write_json_atomic(directory / "plan.json", plan)
    event(root, "rsa.round-created", round_id=round_id, evidence_ids=evidence_ids, lanes=len(lanes))
    return plan
