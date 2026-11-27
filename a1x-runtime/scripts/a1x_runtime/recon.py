from __future__ import annotations

from pathlib import Path
from typing import Any

from .atomic import (
    digest_json,
    exclusive_lock,
    read_json,
    write_json_atomic,
    write_text_atomic,
)
from .errors import ValidationError
from .records import event, require_v4_campaign, schema_for, utc_now


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
