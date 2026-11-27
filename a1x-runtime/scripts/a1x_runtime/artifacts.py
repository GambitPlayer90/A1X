from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .atomic import digest_bytes, read_json, write_json_atomic
from .errors import IntegrityError, ValidationError
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now


def _object_path(root: Path, digest: str) -> Path:
    return root / "evidence" / "objects" / "sha256" / digest[:2] / digest


def ingest_artifact(root: Path, source: Path, *, media_type: str, role: str, producer: str) -> dict[str, Any]:
    require_v4_campaign(root)
    source = source.resolve()
    if not source.is_file():
        raise ValidationError(f"artifact source is not a file: {source}")
    data = source.read_bytes()
    digest = digest_bytes(data)
    destination = _object_path(root, digest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and digest_bytes(destination.read_bytes()) != digest:
        raise IntegrityError(f"content-address collision at {destination}")
    if not destination.exists():
        descriptor, temporary = tempfile.mkstemp(prefix=".a1x-object.", dir=destination.parent)
        temporary_path = Path(temporary)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_path, 0o444)
            os.replace(temporary_path, destination)
        finally:
            temporary_path.unlink(missing_ok=True)
    artifact_id = allocate_id(root, "ART")
    record = {
        "schema": schema_for(root), "kind": "immutable-artifact", "id": artifact_id,
        "created_at": utc_now(), "sha256": digest, "size_bytes": len(data),
        "media_type": media_type, "role": role, "producer": producer,
        "original_name": source.name, "object": str(destination.relative_to(root)),
    }
    write_json_atomic(root / "evidence" / f"{artifact_id}.json", record)
    event(root, "artifact.ingested", artifact_id=artifact_id, sha256=digest, role=role)
    return record


def verify_artifact(root: Path, artifact_id: str) -> dict[str, Any]:
    record = read_json(root / "evidence" / f"{artifact_id}.json")
    path = root / record["object"]
    actual = digest_bytes(path.read_bytes()) if path.is_file() else None
    return {"artifact_id": artifact_id, "valid": actual == record["sha256"], "expected": record["sha256"], "actual": actual}


def materialize_artifact(root: Path, artifact_id: str, destination: Path) -> dict[str, Any]:
    verified = verify_artifact(root, artifact_id)
    if not verified["valid"]:
        raise IntegrityError(f"artifact failed verification: {artifact_id}")
    record = read_json(root / "evidence" / f"{artifact_id}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / record["object"], destination)
    os.chmod(destination, 0o444)
    return {"artifact_id": artifact_id, "destination": str(destination), "read_only": True}
