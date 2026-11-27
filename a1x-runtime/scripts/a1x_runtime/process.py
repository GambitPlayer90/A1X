from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

from .errors import ValidationError
from .hashing import file_sha256
from .records import utc_now

ENV_TOKEN = re.compile(r"^@env:([A-Z_][A-Z0-9_]*)$")
SAFE_ENV = ("PATH", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TMPDIR", "USER", "LOGNAME", "SHELL")


@dataclass
class ProcessResult:
    started_at: str
    finished_at: str
    duration_ms: int
    exit_code: int | None
    timed_out: bool
    terminated_by: str | None
    stdout_sha256: str
    stderr_sha256: str
    stdout_bytes: int
    stderr_bytes: int
    stdout_truncated: bool
    stderr_truncated: bool
    executable: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def secret_names(argv: Iterable[str], pass_env: Iterable[str]) -> set[str]:
    names = set(pass_env)
    for argument in argv:
        match = ENV_TOKEN.fullmatch(argument)
        if match:
            names.add(match.group(1))
    return names


def resolve_argv(argv: list[str], source_env: dict[str, str]) -> tuple[list[str], list[bytes]]:
    if not argv:
        raise ValidationError("empty command")
    resolved: list[str] = []
    secrets: list[bytes] = []
    for argument in argv:
        match = ENV_TOKEN.fullmatch(argument)
        if not match:
            if "@env:" in argument:
                raise ValidationError("environment tokens must occupy an entire argument")
            resolved.append(argument)
            continue
        name = match.group(1)
        value = source_env.get(name)
        if not value:
            raise ValidationError(f"required environment variable is unset: {name}")
        resolved.append(value)
        secrets.append(value.encode())
    executable = shutil.which(resolved[0], path=source_env.get("PATH"))
    if not executable:
        raise ValidationError(f"executable not found: {argv[0]}")
    resolved[0] = executable
    return resolved, secrets


def build_environment(
    source_env: dict[str, str],
    *,
    home: Path,
    pass_env: Iterable[str],
    inherit_env: Iterable[str],
) -> tuple[dict[str, str], list[bytes]]:
    home.mkdir(parents=True, exist_ok=True)
    env = {name: source_env[name] for name in SAFE_ENV if source_env.get(name)}
    env.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            "XDG_DATA_HOME": str(home / ".local" / "share"),
            "FOUNDRY_FFI": "false",
            "CI": "1",
        }
    )
    redactions: list[bytes] = []
    for name in sorted(set(pass_env) | set(inherit_env)):
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", name):
            raise ValidationError(f"invalid environment variable name: {name}")
        if name not in source_env:
            raise ValidationError(f"requested environment variable is unset: {name}")
        env[name] = source_env[name]
        if source_env[name]:
            redactions.append(source_env[name].encode())
    return env, redactions


class RedactingWriter:
    def __init__(self, destination: BinaryIO, secrets: Iterable[bytes], limit: int) -> None:
        self.destination = destination
        self.secrets = sorted({s for s in secrets if s}, key=len, reverse=True)
        self.max_secret = max((len(s) for s in self.secrets), default=1)
        self.limit = limit
        self.pending = b""
        self.written = 0
        self.truncated = False

    def feed(self, data: bytes) -> None:
        self.pending += data
        self._drain(final=False)

    def finish(self) -> None:
        self._drain(final=True)
        if self.truncated:
            marker = b"\n<A1X output truncated after configured byte limit>\n"
            self.destination.write(marker)
            self.written += len(marker)

    def _drain(self, *, final: bool) -> None:
        safe = len(self.pending) if final else max(0, len(self.pending) - self.max_secret + 1)
        consumed = 0
        output = bytearray()
        while consumed < safe:
            match = next((secret for secret in self.secrets if self.pending.startswith(secret, consumed)), None)
            if match is not None:
                output.extend(b"<redacted>")
                consumed += len(match)
            else:
                output.append(self.pending[consumed])
                consumed += 1
        if final and consumed < len(self.pending):
            while consumed < len(self.pending):
                match = next((secret for secret in self.secrets if self.pending.startswith(secret, consumed)), None)
                if match is not None:
                    output.extend(b"<redacted>")
                    consumed += len(match)
                else:
                    output.append(self.pending[consumed])
                    consumed += 1
        self.pending = self.pending[consumed:]
        self._write(bytes(output))

    def _write(self, data: bytes) -> None:
        if self.written >= self.limit:
            self.truncated = self.truncated or bool(data)
            return
        remaining = self.limit - self.written
        chunk = data[:remaining]
        self.destination.write(chunk)
        self.written += len(chunk)
        if len(chunk) != len(data):
            self.truncated = True


def _pump(stream: BinaryIO, writer: RedactingWriter) -> None:
    try:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            writer.feed(chunk)
    finally:
        writer.finish()
        stream.close()


def terminate_process_group(process: subprocess.Popen[bytes], grace_seconds: float = 5.0) -> str:
    if process.poll() is not None:
        return "already-exited"
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return "already-exited"
    try:
        process.wait(timeout=grace_seconds)
        return "SIGTERM"
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        return "SIGKILL"


def execute(
    argv_template: list[str],
    *,
    cwd: Path,
    artifact_dir: Path,
    timeout_seconds: int,
    max_output_bytes: int,
    pass_env: Iterable[str] = (),
    inherit_env: Iterable[str] = (),
    source_env: dict[str, str] | None = None,
    cancel_event: threading.Event | None = None,
) -> ProcessResult:
    source = dict(os.environ if source_env is None else source_env)
    cwd = cwd.resolve()
    if not cwd.is_dir():
        raise ValidationError(f"working directory does not exist: {cwd}")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    argv, argv_secrets = resolve_argv(argv_template, source)
    env, env_secrets = build_environment(
        source,
        home=artifact_dir / "home",
        pass_env=pass_env,
        inherit_env=inherit_env,
    )
    secrets = argv_secrets + env_secrets
    stdout_path = artifact_dir / "stdout.log"
    stderr_path = artifact_dir / "stderr.log"
    started_at = utc_now()
    monotonic_start = time.monotonic()
    timed_out = False
    terminated_by: str | None = None
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        assert process.stdout is not None and process.stderr is not None
        stdout_writer = RedactingWriter(stdout_handle, secrets, max_output_bytes)
        stderr_writer = RedactingWriter(stderr_handle, secrets, max_output_bytes)
        threads = [
            threading.Thread(target=_pump, args=(process.stdout, stdout_writer), daemon=True),
            threading.Thread(target=_pump, args=(process.stderr, stderr_writer), daemon=True),
        ]
        for thread in threads:
            thread.start()
        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                terminated_by = f"cancelled:{terminate_process_group(process)}"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                terminated_by = terminate_process_group(process)
                break
            try:
                process.wait(timeout=min(0.2, remaining))
            except subprocess.TimeoutExpired:
                continue
        for thread in threads:
            thread.join(timeout=10)
        stdout_handle.flush()
        stderr_handle.flush()
        os.fsync(stdout_handle.fileno())
        os.fsync(stderr_handle.fileno())
    duration_ms = int((time.monotonic() - monotonic_start) * 1000)
    return ProcessResult(
        started_at=started_at,
        finished_at=utc_now(),
        duration_ms=duration_ms,
        exit_code=process.returncode,
        timed_out=timed_out,
        terminated_by=terminated_by,
        stdout_sha256=file_sha256(stdout_path),
        stderr_sha256=file_sha256(stderr_path),
        stdout_bytes=stdout_path.stat().st_size,
        stderr_bytes=stderr_path.stat().st_size,
        stdout_truncated=stdout_writer.truncated,
        stderr_truncated=stderr_writer.truncated,
        executable=argv[0],
    )
