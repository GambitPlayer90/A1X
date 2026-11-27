from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .atomic import digest_json, read_json, seal, write_json_atomic
from .errors import IntegrityError, ValidationError
from .process import execute
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now


def prepare_blind_review(root: Path, candidate_id: str) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    candidate = read_json(root / "candidates" / f"{candidate_id}.json")
    if not candidate.get("replay_id"):
        raise ValidationError("blind review requires a prepared replay")
    replay = read_json(root / "replays" / f"{candidate['replay_id']}.json")
    review_id = allocate_id(root, "BLIND")
    directory = root / "reviews" / review_id
    directory.mkdir(parents=True)
    packet = {
        "schema": schema_for(root), "kind": "blind-review-packet", "review_id": review_id,
        "candidate_id": candidate_id, "target": campaign["target"],
        "target_sha256": campaign["source"]["initial_digest"], "property": candidate["property"],
        "support_run": candidate["support_run"], "control_run": candidate.get("control_run"),
        "replay": replay, "fidelity": candidate.get("fidelity", {}),
        "instructions": [
            "First reproduce the behavior from the supplied replay artifacts.",
            "Then challenge causality, attacker capabilities, deployed applicability, and economic impact.",
            "Do not infer support from the original investigator; their rationale is intentionally absent.",
        ],
    }
    write_json_atomic(directory / "packet.json", packet, mode=0o444)
    packet_sha = seal(directory / "packet.json", directory / "packet.sha256")
    record = {
        "schema": schema_for(root), "kind": "mechanical-blind-review", "id": review_id,
        "created_at": utc_now(), "candidate_id": candidate_id, "status": "prepared",
        "packet_sha256": packet_sha, "rationale_withheld": True, "fresh_process": None,
    }
    write_json_atomic(directory / "record.json", record)
    event(root, "blind-review.prepared", blind_review_id=review_id, candidate_id=candidate_id, packet_sha256=packet_sha)
    return record


def execute_blind_review(root: Path, review_id: str, *, argv: list[str], timeout_seconds: int = 1800) -> dict[str, Any]:
    directory = root / "reviews" / review_id
    record = read_json(directory / "record.json")
    if record.get("status") != "prepared":
        raise ValidationError("blind review is not prepared")
    output = directory / "review-output.json"
    rendered = [item.replace("{packet}", str(directory / "packet.json")).replace("{output}", str(output)) for item in argv]
    if all("{packet}" not in item for item in argv) or all("{output}" not in item for item in argv):
        raise ValidationError("review command must contain {packet} and {output} placeholders")
    receipt = execute(rendered, cwd=directory, artifact_dir=directory / "process", timeout_seconds=timeout_seconds, max_output_bytes=16 * 1024 * 1024)
    write_json_atomic(directory / "process.json", receipt.to_dict())
    if receipt.exit_code != 0 or receipt.timed_out or not output.is_file():
        record.update({"status": "failed", "fresh_process": True, "process": receipt.to_dict()})
        write_json_atomic(directory / "record.json", record)
        event(root, "blind-review.failed", blind_review_id=review_id)
        return record
    result = read_json(output)
    if result.get("verdict") not in {"confirmed", "rejected", "needs-work"}:
        raise IntegrityError("blind reviewer output has invalid verdict")
    if not isinstance(result.get("reproduced"), bool) or not isinstance(result.get("challenges"), list):
        raise IntegrityError("blind reviewer output requires reproduced and challenges")
    output_sha = seal(output, directory / "review-output.sha256")
    record.update({
        "status": "completed", "completed_at": utc_now(), "fresh_process": True,
        "process": receipt.to_dict(), "output_sha256": output_sha, "verdict": result["verdict"],
        "reproduced": result["reproduced"], "reviewer_identity": {"executable": receipt.executable, "process_input_sha256": digest_json(rendered)},
    })
    write_json_atomic(directory / "record.json", record)
    candidate_path = root / "candidates" / f"{record['candidate_id']}.json"
    candidate = read_json(candidate_path)
    candidate.setdefault("blind_reviews", []).append(review_id)
    write_json_atomic(candidate_path, candidate)
    event(root, "blind-review.completed", blind_review_id=review_id, candidate_id=record["candidate_id"], verdict=result["verdict"])
    return record


def qualifies(root: Path, review_id: str, candidate_id: str) -> bool:
    path = root / "reviews" / review_id / "record.json"
    if not path.is_file():
        return False
    record = read_json(path)
    return bool(record.get("candidate_id") == candidate_id and record.get("status") == "completed" and record.get("fresh_process") is True and record.get("rationale_withheld") is True and record.get("reproduced") is True and record.get("verdict") == "confirmed")
