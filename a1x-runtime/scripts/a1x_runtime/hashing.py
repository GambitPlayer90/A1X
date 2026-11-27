from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .errors import ValidationError


ROOT_EXCLUDES = {".git", ".a1x", "out", "cache", "node_modules"}
TREE_EXCLUDES = {".git", "node_modules"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def path_digest(path: Path, *, excludes: set[str] | None = None) -> dict[str, object]:
    path = path.resolve()
    if not path.exists():
        raise ValidationError(f"input does not exist: {path}")
    root_excluded = ROOT_EXCLUDES if excludes is None else excludes
    tree_excluded = TREE_EXCLUDES if excludes is None else excludes
    if path.is_file():
        return {"kind": "file", "sha256": file_sha256(path), "files": 1, "bytes": path.stat().st_size}
    if not path.is_dir():
        raise ValidationError(f"input is neither file nor directory: {path}")
    digest = hashlib.sha256()
    count = 0
    size = 0
    for current, dirs, files in os.walk(path):
        base = Path(current)
        denied = root_excluded if base == path else tree_excluded
        dirs[:] = sorted(d for d in dirs if d not in denied)
        for name in sorted(files):
            candidate = base / name
            if candidate.is_symlink():
                try:
                    candidate.resolve().relative_to(path)
                except (ValueError, RuntimeError) as exc:
                    raise ValidationError(f"input directory contains escaping or cyclic symlink: {candidate}") from exc
                target = os.readlink(candidate)
                payload = f"L\0{candidate.relative_to(path).as_posix()}\0{target}\0".encode()
            elif candidate.is_file():
                relative = candidate.relative_to(path).as_posix()
                child_hash = file_sha256(candidate)
                child_size = candidate.stat().st_size
                payload = f"F\0{relative}\0{child_size}\0{child_hash}\0".encode()
                size += child_size
            else:
                continue
            digest.update(payload)
            count += 1
    return {"kind": "directory", "sha256": digest.hexdigest(), "files": count, "bytes": size}


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_relative(path: Path, parent: Path) -> str:
    try:
        return path.resolve().relative_to(parent.resolve()).as_posix()
    except ValueError as exc:
        raise ValidationError(f"{path} is outside allowed root {parent}") from exc
