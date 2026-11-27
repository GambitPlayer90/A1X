from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from .errors import IntegrityError


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_bytes(value))


def read_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise IntegrityError(f"missing required artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise IntegrityError(f"invalid JSON artifact {path}: {exc}") from exc


def _fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_json_atomic_raw(path: Path, value: Any, *, mode: int = 0o600) -> None:
    """Write JSON atomically without producing an event-sourced materialization.

    Runtime callers should use ``write_json_atomic``.  The raw primitive exists
    for the event journal itself and for crash recovery, where recursively
    journaling the journal would be incorrect.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(canonical_bytes(value))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_dir(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


def write_json_atomic(path: Path, value: Any, *, mode: int = 0o600) -> None:
    # Import lazily to avoid an atomic <-> records import cycle.  Once a v4
    # campaign exists, authoritative JSON views are preceded by a hash-chained
    # materialization event and can therefore be recovered after interruption.
    from .records import materialize_json_if_campaign

    if materialize_json_if_campaign(path, value, mode=mode):
        return
    _write_json_atomic_raw(path, value, mode=mode)


def write_text_atomic(path: Path, text: str, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temporary)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_dir(path.parent)
    finally:
        temp_path.unlink(missing_ok=True)


_LOCK_STATE = threading.local()


@contextlib.contextmanager
def exclusive_lock(root: Path) -> Iterator[None]:
    """Take the campaign lock, allowing safe same-thread nesting.

    Event-sourced materialization can be invoked from code that already owns
    the campaign lock.  Plain ``flock`` on a separately opened descriptor is
    not reliably re-entrant, so retain one descriptor per root and thread.
    """
    root.mkdir(parents=True, exist_ok=True)
    resolved = str(root.resolve())
    held = getattr(_LOCK_STATE, "held", None)
    if held is None:
        held = {}
        _LOCK_STATE.held = held
    current = held.get(resolved)
    if current is not None:
        current[1] += 1
        try:
            yield
        finally:
            current[1] -= 1
        return
    lock_path = root / ".a1x.lock"
    handle = lock_path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        held[resolved] = [handle, 1]
        try:
            yield
        finally:
            held.pop(resolved, None)
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


@contextlib.contextmanager
def named_lock(root: Path, name: str) -> Iterator[None]:
    """Serialize one idempotent workflow without blocking unrelated work."""
    lock_dir = root / ".a1x-locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    safe_name = hashlib.sha256(name.encode()).hexdigest()
    with (lock_dir / safe_name).open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(canonical_bytes(value))
        handle.flush()
        os.fsync(handle.fileno())


def verify_seal(path: Path, seal_path: Path) -> None:
    expected = seal_path.read_text(encoding="utf-8").strip()
    actual = digest_bytes(path.read_bytes())
    if actual != expected:
        raise IntegrityError(f"artifact seal mismatch: {path}")


def seal(path: Path, seal_path: Path) -> str:
    value = digest_bytes(path.read_bytes())
    write_text_atomic(seal_path, value + "\n")
    return value
