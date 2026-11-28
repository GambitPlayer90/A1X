from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

from .atomic import digest_bytes, read_json, seal, verify_seal, write_json_atomic
from .errors import IntegrityError, ValidationError
from .replay import load_verified_replay
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now


def prepare_blind_review(root: Path, candidate_id: str) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    candidate = read_json(root / "candidates" / f"{candidate_id}.json")
    if not candidate.get("replay_id"):
        raise ValidationError("blind review requires a prepared replay")
    replay = load_verified_replay(
        root,
        str(candidate["replay_id"]),
        expected_run_id=str(candidate.get("support_run") or ""),
    )
    if replay.get("passed") is not True:
        raise ValidationError("blind review requires a passing replay of the exact candidate support run")
    review_id = allocate_id(root, "BLIND")
    directory = root / "reviews" / review_id
    directory.mkdir(parents=True)
    challenge_nonce = secrets.token_hex(24)
    packet = {
        "schema": schema_for(root), "kind": "blind-review-packet", "review_id": review_id,
        "candidate_id": candidate_id, "target": campaign["target"],
        "target_sha256": campaign["source"]["initial_digest"], "property": candidate["property"],
        "support_run": candidate["support_run"], "control_run": candidate.get("control_run"),
        "replay": replay, "fidelity": candidate.get("fidelity", {}),
        "scope_id": candidate.get("scope_id"), "eligible_impact": candidate.get("eligible_impact"),
        "challenge_nonce": challenge_nonce,
        "instructions": [
            "First reproduce the behavior from the supplied replay artifacts.",
            "Then challenge causality, attacker capabilities, deployed applicability, and economic impact.",
            "Do not infer support from the original investigator; their rationale is intentionally absent.",
            "Write the bound result schema to the disclosed subagent-result.json path; echo every binding field exactly.",
        ],
    }
    write_json_atomic(directory / "packet.json", packet, mode=0o444)
    packet_sha = seal(directory / "packet.json", directory / "packet.sha256")
    from .ledger import add_record

    task = add_record(
        root,
        kind="TASK",
        title=f"Independent review of {candidate_id}",
        statement="Reproduce the sealed behavior and challenge causality, attacker reachability, deployed applicability, accounting, and impact",
        status="open",
        priority="high",
        next_action="Assign the rationale-withheld packet to a distinct visible built-in subagent",
        owner="primary",
        artifacts=[str((directory / "packet.json").relative_to(root))],
        data={
            "question": "Does the sealed candidate reproduce and withstand independent causal, reachability, applicability, accounting, and impact challenge?",
            "inputs": [candidate_id, candidate["replay_id"], str((directory / "packet.json").relative_to(root))],
            "withheld": ["primary investigator rationale", "preferred explanation"],
            "cost": "medium",
            "review_id": review_id,
            "packet_sha256": packet_sha,
            "challenge_nonce": challenge_nonce,
        },
    )
    record = {
        "schema": schema_for(root), "kind": "mechanical-blind-review", "id": review_id,
        "created_at": utc_now(), "candidate_id": candidate_id, "status": "prepared",
        "packet_sha256": packet_sha, "rationale_withheld": True, "fresh_process": None,
        "ledger_task_id": task["id"],
        "challenge_nonce": challenge_nonce,
        "submission_path": str((directory / "subagent-result.json").relative_to(root)),
        "identity_assurance": "pending-primary-attested-visible-cli-thread",
    }
    write_json_atomic(directory / "record.json", record)
    event(root, "blind-review.prepared", blind_review_id=review_id, candidate_id=candidate_id, packet_sha256=packet_sha)
    return record




def record_in_session_review(
    root: Path,
    review_id: str,
    *,
    subagent_thread: str,
    result_path: Path,
    attest_visible_subagent: bool = False,
) -> dict[str, Any]:
    """Bind a rationale-withheld packet to a visible built-in subagent result.

    The runtime records and validates the result; it never invokes the subagent.
    """
    directory = root / "reviews" / review_id
    record = read_json(directory / "record.json")
    if record.get("status") != "prepared":
        raise ValidationError("blind review is not prepared")
    if not attest_visible_subagent:
        raise ValidationError("primary must explicitly attest that the named built-in subagent thread is visible in the current Codex CLI session")
    verify_seal(directory / "packet.json", directory / "packet.sha256")
    thread = str(subagent_thread or "").strip()
    if not thread or thread.lower() in {"primary", "main", "self"}:
        raise ValidationError("in-session review requires a distinct built-in subagent thread identity")
    expected_result_path = (directory / "subagent-result.json").resolve()
    if result_path.resolve() != expected_result_path:
        raise ValidationError(f"subagent result must be written to the prepared path: {expected_result_path}")
    result = read_json(expected_result_path)
    expected_bindings = {
        "review_id": review_id,
        "candidate_id": record["candidate_id"],
        "packet_sha256": record["packet_sha256"],
        "challenge_nonce": record["challenge_nonce"],
        "subagent_thread": thread,
    }
    for key, expected in expected_bindings.items():
        if result.get(key) != expected:
            raise IntegrityError(f"subagent reviewer output has invalid {key} binding")
    if result.get("verdict") not in {"confirmed", "rejected", "needs-work"}:
        raise IntegrityError("subagent reviewer output has invalid verdict")
    if not isinstance(result.get("reproduced"), bool):
        raise IntegrityError("subagent reviewer output requires a boolean reproduced field")
    for field in ("challenges", "reproduction_commands", "artifact_refs"):
        values = result.get(field)
        if not isinstance(values, list) or not values or any(not isinstance(item, str) or not item.strip() for item in values):
            raise IntegrityError(f"subagent reviewer output requires non-empty string array {field}")
    output = directory / "review-output.json"
    write_json_atomic(output, result, mode=0o444)
    output_sha = seal(output, directory / "review-output.sha256")
    from .ledger import show_record, update_record

    task_id = str(record.get("ledger_task_id") or "")
    task = show_record(root, task_id)
    task_data = dict(task.get("data", {}))
    task_data.update({"subagent_thread": thread, "review_output_sha256": output_sha, "verdict": result["verdict"]})
    update_record(
        root,
        task_id,
        expected_revision=int(task["revision"]),
        changes={"status": "closed", "owner": f"subagent:{thread}", "data": task_data, "next_action": "Review result bound to candidate evidence"},
        reason="visible built-in subagent review completed",
    )
    record.update({
        "status": "completed",
        "completed_at": utc_now(),
        "fresh_process": False,
        "visible_in_session": True,
        "primary_attested_visible_subagent": True,
        "identity_assurance": "primary-attested-visible-cli-thread; runtime-does-not-authenticate-Codex-UI-identity",
        "output_sha256": output_sha,
        "verdict": result["verdict"],
        "reproduced": result["reproduced"],
        "reviewer_identity": {"kind": "builtin-subagent", "thread": thread, "authentication": "primary-attested"},
    })
    write_json_atomic(directory / "record.json", record)
    candidate_path = root / "candidates" / f"{record['candidate_id']}.json"
    candidate = read_json(candidate_path)
    candidate.setdefault("blind_reviews", []).append(review_id)
    write_json_atomic(candidate_path, candidate)
    event(root, "blind-review.in-session-completed", blind_review_id=review_id, candidate_id=record["candidate_id"], subagent_thread=thread, verdict=result["verdict"])
    return record


def qualifies(root: Path, review_id: str, candidate_id: str) -> bool:
    path = root / "reviews" / review_id / "record.json"
    if not path.is_file():
        return False
    try:
        directory = path.parent
        verify_seal(directory / "packet.json", directory / "packet.sha256")
        verify_seal(directory / "review-output.json", directory / "review-output.sha256")
        record = read_json(path)
        packet = read_json(directory / "packet.json")
        output = read_json(directory / "review-output.json")
        candidate = read_json(root / "candidates" / f"{candidate_id}.json")
        replay = load_verified_replay(
            root,
            str(candidate.get("replay_id") or ""),
            expected_run_id=str(candidate.get("support_run") or ""),
        )
        identity = record.get("reviewer_identity", {})
        thread = str(identity.get("thread") or "")
        packet_sha = digest_bytes((directory / "packet.json").read_bytes())
        output_sha = digest_bytes((directory / "review-output.json").read_bytes())
        if not (
            record.get("candidate_id") == candidate_id
            and packet.get("review_id") == review_id
            and packet.get("candidate_id") == candidate_id
            and record.get("packet_sha256") == packet_sha
            and record.get("output_sha256") == output_sha
            and packet.get("support_run") == candidate.get("support_run") == replay.get("run_id")
            and packet.get("control_run") == candidate.get("control_run")
            and packet.get("replay") == replay
            and output.get("review_id") == review_id
            and output.get("candidate_id") == candidate_id
            and output.get("packet_sha256") == packet_sha
            and output.get("challenge_nonce") == record.get("challenge_nonce") == packet.get("challenge_nonce")
            and output.get("subagent_thread") == thread
            and output.get("verdict") == record.get("verdict")
            and output.get("reproduced") == record.get("reproduced")
            and all(
                isinstance(output.get(field), list)
                and bool(output[field])
                and all(isinstance(item, str) and item.strip() for item in output[field])
                for field in ("challenges", "reproduction_commands", "artifact_refs")
            )
        ):
            return False
        from .ledger import show_record

        task = show_record(root, str(record["ledger_task_id"]))
        visible_task_bound = bool(
            record.get("visible_in_session") is True
            and task.get("kind") == "TASK"
            and task.get("status") == "closed"
            and task.get("owner") == f"subagent:{thread}"
            and task.get("data", {}).get("review_id") == review_id
            and task.get("data", {}).get("review_output_sha256") == output_sha
            and task.get("data", {}).get("packet_sha256") == packet_sha
            and task.get("data", {}).get("challenge_nonce") == record.get("challenge_nonce")
        )
    except (IntegrityError, ValidationError, OSError, ValueError, KeyError):
        return False
    independent_transport = (
        visible_task_bound
        and record.get("primary_attested_visible_subagent") is True
        and identity.get("kind") == "builtin-subagent"
        and bool(str(identity.get("thread") or "").strip())
    )
    return bool(record.get("candidate_id") == candidate_id and record.get("status") == "completed" and independent_transport and record.get("rationale_withheld") is True and record.get("reproduced") is True and record.get("verdict") == "confirmed")
