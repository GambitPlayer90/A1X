from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .atomic import write_json_atomic
from .campaign import doctor
from .errors import ValidationError
from .hashing import path_digest
from .records import event, require_v4_campaign, schema_for, utc_now


@dataclass(frozen=True)
class Adapter:
    name: str
    executable: str
    role: str
    campaign_control: bool = False
    fork: bool = False
    corpus: bool = False
    symbolic: bool = False


ADAPTERS = {
    "foundry": Adapter("foundry", "forge", "replay-and-final-evidence", fork=True, corpus=True),
    "wake": Adapter("wake", "wake", "semantic-python-models", fork=True, corpus=True),
    "echidna": Adapter("echidna", "echidna", "interactive-coverage-guided", campaign_control=True, fork=True, corpus=True, symbolic=True),
    "medusa": Adapter("medusa", "medusa", "multiworker-mutation", fork=True, corpus=True),
    "halmos": Adapter("halmos", "halmos", "symbolic-solving", symbolic=True),
    "ityfuzz": Adapter("ityfuzz", "ityfuzz", "deployed-state-exploration", fork=True, corpus=True, symbolic=True),
}


def _run_probe(argv: list[str], cwd: Path, timeout: int = 180, *, home: Path | None = None) -> dict[str, Any]:
    try:
        probe_home = home or cwd / ".a1x-probe-home"
        probe_home.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            env={"PATH": __import__("os").environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": str(probe_home), "XDG_CACHE_HOME": str(probe_home / ".cache"), "CI": "1", "FOUNDRY_FFI": "false"},
        )
        output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
        return {"ready": completed.returncode == 0, "exit_code": completed.returncode, "diagnostic": output[-8000:]}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ready": False, "exit_code": None, "diagnostic": f"{type(exc).__name__}: {exc}"}


def probe_target(root: Path) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    source = Path(campaign["source"]["path"])
    inventory = doctor()
    results: dict[str, Any] = {}
    probe_parent = root / "capabilities"
    for candidate in source.rglob("*"):
        if candidate.is_symlink() and not candidate.resolve().is_relative_to(source.resolve()):
            raise ValidationError(f"target probe refused a symlink escaping the source root: {candidate}")
    with tempfile.TemporaryDirectory(prefix="target-probe-", dir=probe_parent) as temporary:
        workspace = Path(temporary) / "target"
        shutil.copytree(source, workspace, symlinks=False, ignore=shutil.ignore_patterns(".git", "out", "cache", "node_modules", ".a1x"))
        home = Path(temporary) / "home"
        foundry_ready = inventory["tools"]["forge"]["available"]
        results["foundry"] = _run_probe(["forge", "build", "--force", "--out", str(Path(temporary) / "foundry-out"), "--cache-path", str(Path(temporary) / "foundry-cache")], workspace, home=home) if foundry_ready else {"ready": False, "diagnostic": "forge unavailable"}
        wake_available = inventory["tools"]["wake"]["available"]
        results["wake"] = _run_probe(["wake", "compile", "--no-artifacts"], workspace, home=home) if wake_available else {"ready": False, "diagnostic": "wake unavailable"}
        crytic = shutil.which("crytic-compile")
        results["echidna"] = _run_probe([crytic, ".", "--skip-clean", "--export-dir", str(Path(temporary) / "crytic-export")], workspace, home=home) if crytic and inventory["tools"]["echidna"]["available"] else {"ready": False, "diagnostic": "echidna or crytic-compile unavailable"}
        results["echidna"]["live_campaign_control"] = inventory["capabilities"]["echidna_live_campaign"]
        for name in ("medusa", "halmos", "ityfuzz"):
            adapter = ADAPTERS[name]
            available = inventory["tools"].get(adapter.executable, {}).get("available", False)
            results[name] = {"ready": bool(available and results["foundry"]["ready"]), "diagnostic": "installed; target-specific harness required" if available else f"{adapter.executable} unavailable", "harness_required": True}
        if home.is_dir() and any(home.iterdir()):
            cached_home = root / "capabilities" / "toolchains" / "home"
            if cached_home.exists():
                shutil.rmtree(cached_home)
            shutil.copytree(home, cached_home)
            for value in results.values():
                if value.get("ready"):
                    value["toolchain_home"] = str(cached_home.relative_to(root))
    record = {
        "schema": schema_for(root), "kind": "target-capability-probe", "created_at": utc_now(),
        "source_sha256": path_digest(source), "machine": inventory, "backends": results,
        "routing_rule": "never route to a backend whose target probe is false",
        "isolation_rule": "backend toolchains fetched during probing are copied into campaign-scoped caches",
    }
    write_json_atomic(root / "capabilities" / "capabilities.json", record)
    event(root, "capabilities.probed", ready=[name for name, value in results.items() if value["ready"]])
    return record


def capability_matrix(root: Path) -> dict[str, Any]:
    path = root / "capabilities" / "capabilities.json"
    if not path.is_file():
        raise ValidationError("target capabilities have not been probed")
    return {name: asdict(adapter) for name, adapter in ADAPTERS.items()} | {"probe": __import__("json").loads(path.read_text())}
