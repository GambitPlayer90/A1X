from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any


_BWRAP_CACHE: dict[str, Any] | None = None


def bubblewrap_preflight(*, refresh: bool = False) -> dict[str, Any]:
    """Test the namespace operation Codex lanes need without reading credentials."""
    global _BWRAP_CACHE
    if _BWRAP_CACHE is not None and not refresh:
        return dict(_BWRAP_CACHE)
    executable = shutil.which("bwrap")
    if not executable:
        result = {"available": False, "usable": None, "path": None, "exit_code": None, "error": "bubblewrap not found; Codex may use another sandbox backend"}
        _BWRAP_CACHE = result
        return dict(result)
    command = [
        executable,
        "--unshare-user-try",
        "--unshare-net",
        "--ro-bind",
        "/",
        "/",
        "--dev-bind",
        "/dev",
        "/dev",
        "--proc",
        "/proc",
        "--new-session",
        "--",
        "/bin/true",
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            env={"PATH": os.environ.get("PATH", "")},
        )
        error_lines = (completed.stderr or completed.stdout).strip().splitlines()
        result = {
            "available": True,
            "usable": completed.returncode == 0,
            "path": executable,
            "exit_code": completed.returncode,
            "error": error_lines[0][:500] if error_lines and completed.returncode != 0 else None,
        }
    except (OSError, subprocess.SubprocessError) as exc:
        result = {"available": True, "usable": False, "path": executable, "exit_code": None, "error": type(exc).__name__}
    _BWRAP_CACHE = result
    return dict(result)
