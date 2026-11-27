from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from .atomic import write_json_atomic
from .errors import A1XError, ValidationError
from .features import enabled
from .hashing import file_sha256, is_relative_to
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now
from .rpc import rpc_call


ADDRESS_RE = re.compile(r"0x[a-fA-F0-9]{40}")
IMPORT_RE = re.compile(r"\bimport\s+(?:[^\"']*from\s+)?[\"']([^\"']+)[\"']")
EXTERNAL_CALL_RE = re.compile(r"\.\s*(call|delegatecall|staticcall|transfer|send)\b")

EIP1967_SLOTS = {
    "implementation": "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc",
    "admin": "0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103",
    "beacon": "0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50",
}

STANDARD_PROBES = {
    "name": ("0x06fdde03", "string"),
    "symbol": ("0x95d89b41", "string"),
    "decimals": ("0x313ce567", "uint"),
    "totalSupply": ("0x18160ddd", "uint"),
    "asset": ("0x38d52e0f", "address"),
    "totalAssets": ("0x01e1d114", "uint"),
    "permitNonceZero": ("0x7ecebe00" + "00" * 32, "uint"),
    "domainSeparator": ("0x3644e515", "bytes32"),
    "paused": ("0x5c975abb", "uint"),
    "latestRoundData": ("0xfeaf968c", "raw"),
    "latestAnswer": ("0x50d25bcd", "uint"),
    "latestTimestamp": ("0x8205bf6a", "uint"),
    "convertOneAssetToShares": ("0xc6e6f592" + "0" * 63 + "1", "uint"),
    "convertOneShareToAssets": ("0x07a2d13a" + "0" * 63 + "1", "uint"),
    "maxWithdrawZero": ("0xce96cb77" + "00" * 32, "uint"),
    "getReserves": ("0x0902f1ac", "raw"),
}


def _address(value: Any, field: str) -> str:
    result = str(value or "").lower()
    if not re.fullmatch(r"0x[a-f0-9]{40}", result):
        raise ValidationError(f"{field} must be a 20-byte hex address")
    return result


def _decode(data: str, kind: str) -> Any:
    if not isinstance(data, str) or not data.startswith("0x"):
        raise ValueError("non-hex return data")
    raw = bytes.fromhex(data[2:])
    if kind == "uint":
        if len(raw) < 32:
            raise ValueError("short uint return")
        return str(int.from_bytes(raw[-32:], "big"))
    if kind == "address":
        if len(raw) < 32:
            raise ValueError("short address return")
        return "0x" + raw[-20:].hex()
    if kind == "bytes32":
        if len(raw) < 32:
            raise ValueError("short bytes32 return")
        return "0x" + raw[:32].hex()
    if kind == "string":
        if len(raw) == 32:
            return raw.rstrip(b"\0").decode("utf-8", errors="replace")
        if len(raw) < 64:
            raise ValueError("short string return")
        offset = int.from_bytes(raw[:32], "big")
        if offset + 32 > len(raw):
            raise ValueError("invalid string offset")
        length = int.from_bytes(raw[offset : offset + 32], "big")
        start = offset + 32
        if start + length > len(raw):
            raise ValueError("invalid string length")
        return raw[start : start + length].decode("utf-8", errors="replace")
    if kind == "raw":
        return data
    raise ValidationError(f"unsupported probe decoder: {kind}")


def _slot_address(value: str) -> str | None:
    if not isinstance(value, str) or not value.startswith("0x"):
        return None
    raw = value[2:].rjust(64, "0")
    address = "0x" + raw[-40:]
    return None if int(address, 16) == 0 else address.lower()


def _source_facts(source_root: Path, paths: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    facts = []
    unknowns = []
    for value in paths:
        relative = Path(value)
        path = (source_root / relative).resolve()
        if not is_relative_to(path, source_root) or not path.is_file():
            raise ValidationError(f"surface source path is outside the target or missing: {value}")
        content = path.read_text(encoding="utf-8", errors="replace")
        addresses = []
        imports = []
        calls = []
        for line_number, line in enumerate(content.splitlines(), start=1):
            addresses.extend({"address": item.lower(), "line": line_number} for item in ADDRESS_RE.findall(line))
            imports.extend({"path": item, "line": line_number} for item in IMPORT_RE.findall(line))
            calls.extend({"kind": item, "line": line_number} for item in EXTERNAL_CALL_RE.findall(line))
        facts.append(
            {
                "path": relative.as_posix(),
                "sha256": file_sha256(path),
                "address_references": addresses,
                "imports": imports,
                "low_level_call_sites": calls,
            }
        )
        if calls:
            unknowns.append(
                {
                    "kind": "dynamic-dispatch",
                    "source": relative.as_posix(),
                    "question": "resolve every low-level call target and calldata under attacker-controlled inputs",
                }
            )
    return facts, unknowns


def _probe_contract(url: str, block_tag: str, contract: dict[str, Any], additional: list[dict[str, Any]]) -> dict[str, Any]:
    address = contract["address"]
    code = rpc_call(url, "eth_getCode", [address, block_tag], timeout=10)
    code_bytes = bytes.fromhex(code[2:]) if isinstance(code, str) and code.startswith("0x") else b""
    proxy_slots = {}
    for name, slot in EIP1967_SLOTS.items():
        try:
            raw = rpc_call(url, "eth_getStorageAt", [address, slot, block_tag], timeout=10)
            proxy_slots[name] = {"raw": raw, "address": _slot_address(raw)}
        except A1XError as exc:
            proxy_slots[name] = {"raw": None, "address": None, "error": str(exc)}
    probes = []
    specs = [
        {"name": name, "calldata": calldata, "decoder": decoder}
        for name, (calldata, decoder) in STANDARD_PROBES.items()
    ] + additional
    for probe in specs:
        name = str(probe.get("name") or "").strip()
        calldata = str(probe.get("calldata") or "").lower()
        decoder = str(probe.get("decoder") or "raw")
        if not name or not re.fullmatch(r"0x[a-f0-9]+", calldata) or len(calldata) % 2:
            raise ValidationError(f"invalid fork probe for {address}: {name}")
        try:
            raw = rpc_call(url, "eth_call", [{"to": address, "data": calldata}, block_tag], timeout=10)
            decoded = _decode(raw, decoder)
            probes.append({"name": name, "calldata": calldata, "decoder": decoder, "status": "observed", "raw": raw, "value": decoded})
        except (A1XError, ValueError) as exc:
            probes.append({"name": name, "calldata": calldata, "decoder": decoder, "status": "unknown", "raw": None, "value": None, "diagnostic": str(exc)})
    return {
        "label": contract["label"],
        "address": address,
        "kind": contract["kind"],
        "code_bytes": len(code_bytes),
        "code_sha256": hashlib.sha256(code_bytes).hexdigest(),
        "has_code": bool(code_bytes),
        "proxy_slots": proxy_slots,
        "probes": probes,
    }


def build_surface_graph(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    if not enabled(root, "fork_surface_graph"):
        raise ValidationError("fork surface graph is disabled by runtime feature policy")
    if not isinstance(payload, dict):
        raise ValidationError("surface graph payload must be an object")
    raw_contracts = payload.get("contracts")
    if not isinstance(raw_contracts, list) or not raw_contracts or any(not isinstance(item, dict) for item in raw_contracts):
        raise ValidationError("surface graph requires a non-empty contracts array")
    contracts = []
    labels: set[str] = set()
    for raw in raw_contracts:
        label = str(raw.get("label") or "").strip()
        if not label or label in labels:
            raise ValidationError("surface contract labels must be non-empty and unique")
        labels.add(label)
        contracts.append(
            {
                "label": label,
                "address": _address(raw.get("address"), f"contract {label} address"),
                "kind": str(raw.get("kind") or "unknown").strip(),
                "source_paths": [str(item) for item in raw.get("source_paths", [])],
            }
        )
    source_root = Path(campaign["source"]["path"])
    source_facts, unknowns = _source_facts(source_root, sorted({path for item in contracts for path in item["source_paths"]}))
    dependencies = []
    for raw in payload.get("dependencies", []):
        if not isinstance(raw, dict):
            raise ValidationError("surface dependencies must contain objects")
        left = str(raw.get("from") or "")
        right = str(raw.get("to") or "")
        if left not in labels or right not in labels:
            raise ValidationError("surface dependency references an unknown contract label")
        dependencies.append(
            {
                "from": left,
                "to": right,
                "relationship": str(raw.get("relationship") or "unknown").strip(),
                "basis": str(raw.get("basis") or "declared").strip(),
                "evidence": str(raw.get("evidence") or "").strip(),
            }
        )
    additional_by_label: dict[str, list[dict[str, Any]]] = {label: [] for label in labels}
    for probe in payload.get("probes", []):
        if not isinstance(probe, dict) or str(probe.get("contract")) not in labels:
            raise ValidationError("surface probe references an unknown contract")
        additional_by_label[str(probe["contract"])].append(
            {key: probe.get(key) for key in ("name", "calldata", "decoder")}
        )
    rpc_env = campaign.get("chain", {}).get("rpc_env")
    rpc_observations = []
    block_number = campaign.get("chain", {}).get("block_number")
    block_tag = hex(int(block_number)) if block_number is not None else "latest"
    if rpc_env and os.environ.get(str(rpc_env)):
        url = os.environ[str(rpc_env)]
        for contract in contracts:
            rpc_observations.append(_probe_contract(url, block_tag, contract, additional_by_label[contract["label"]]))
    else:
        unknowns.append(
            {
                "kind": "fork-state",
                "question": "RPC environment is unavailable; deployed bytecode, proxy slots, and interface probes were not observed",
            }
        )
    for observation in rpc_observations:
        for slot, value in observation["proxy_slots"].items():
            if value.get("address"):
                dependencies.append(
                    {
                        "from": observation["label"],
                        "to_address": value["address"],
                        "relationship": f"eip1967-{slot}",
                        "basis": "pinned-storage",
                        "evidence": value["raw"],
                    }
                )
        unknown_probes = [item["name"] for item in observation["probes"] if item["status"] == "unknown"]
        if unknown_probes:
            unknowns.append(
                {
                    "kind": "interface-probe",
                    "contract": observation["label"],
                    "question": "unresolved or unsupported probes: " + ", ".join(unknown_probes),
                }
            )
    observed_probes = {
        (observation["label"], probe["name"]): probe
        for observation in rpc_observations
        for probe in observation["probes"]
    }
    ecosystem_traits = []
    for observation in rpc_observations:
        probe_map = {item["name"]: item for item in observation["probes"]}
        kind = str(observation.get("kind", "unknown")).lower()
        traits = []
        if any(token in kind for token in ("token", "erc20", "erc-20", "vault", "erc4626", "erc-4626")):
            traits.extend([
                {"trait": "permit", "status": "observed" if probe_map.get("permitNonceZero", {}).get("status") == "observed" and probe_map.get("domainSeparator", {}).get("status") == "observed" else "unknown", "basis": "read-only interface probes"},
                {"trait": "pausable", "status": "observed" if probe_map.get("paused", {}).get("status") == "observed" else "unknown", "basis": "read-only interface probe"},
                {"trait": "erc4626-conversion", "status": "observed" if probe_map.get("convertOneAssetToShares", {}).get("status") == "observed" and probe_map.get("convertOneShareToAssets", {}).get("status") == "observed" else "unknown", "basis": "one-unit conversion probes"},
                {"trait": "fee-on-transfer", "status": "unknown", "basis": "requires an executable balance-delta probe"},
                {"trait": "rebasing", "status": "unknown", "basis": "requires observations across a state transition"},
                {"trait": "token-hooks", "status": "unknown", "basis": "requires bytecode/call-trace inspection or an executable transfer probe"},
                {"trait": "approval-quirks", "status": "unknown", "basis": "requires an executable approval state machine"},
                {"trait": "blacklist-or-transfer-policy", "status": "unknown", "basis": "requires source or executable actor probes"},
            ])
        if any(token in kind for token in ("oracle", "feed", "price")):
            traits.extend([
                {"trait": "round-data", "status": "observed" if probe_map.get("latestRoundData", {}).get("status") == "observed" else "unknown", "basis": "pinned latestRoundData probe"},
                {"trait": "staleness-timestamp", "status": "observed" if probe_map.get("latestTimestamp", {}).get("status") == "observed" or probe_map.get("latestRoundData", {}).get("status") == "observed" else "unknown", "basis": "pinned timestamp-bearing probe"},
                {"trait": "l2-sequencer-guard", "status": "unknown", "basis": "requires consumer-path source and deployment analysis"},
                {"trait": "spot-vs-twap", "status": "unknown", "basis": "requires semantic source and dependency analysis"},
            ])
        if any(token in kind for token in ("pool", "amm", "dex")):
            traits.extend([
                {"trait": "reserve-interface", "status": "observed" if probe_map.get("getReserves", {}).get("status") == "observed" else "unknown", "basis": "pinned getReserves probe"},
                {"trait": "callback-or-hook-window", "status": "unknown", "basis": "requires executed call-trace analysis"},
            ])
        ecosystem_traits.append({"contract": observation["label"], "traits": traits})
        for trait in traits:
            if trait["status"] == "unknown":
                unknowns.append({"kind": "ecosystem-trait", "contract": observation["label"], "question": f"resolve {trait['trait']}: {trait['basis']}"})
    capital_primitives = []
    for raw in payload.get("capital_primitives", []):
        if not isinstance(raw, dict):
            raise ValidationError("capital primitives must contain objects")
        provider = str(raw.get("provider") or "")
        probe_name = str(raw.get("capacity_probe") or "")
        if provider not in labels or not probe_name:
            raise ValidationError("capital primitive requires a known provider and capacity_probe name")
        probe = observed_probes.get((provider, probe_name))
        status = "observed" if probe and probe.get("status") == "observed" else "unknown"
        primitive = {
            "label": str(raw.get("label") or "").strip(),
            "provider": provider,
            "asset": _address(raw.get("asset"), "capital primitive asset"),
            "capacity_probe": probe_name,
            "capacity": probe.get("value") if status == "observed" else None,
            "unit": str(raw.get("unit") or "").strip(),
            "fee_model": str(raw.get("fee_model") or "").strip(),
            "status": status,
            "block_number": block_number,
        }
        if not primitive["label"] or not primitive["unit"] or not primitive["fee_model"]:
            raise ValidationError("capital primitive label, unit, and fee_model must be explicit")
        capital_primitives.append(primitive)
        if status == "unknown":
            unknowns.append(
                {
                    "kind": "capital-capacity",
                    "provider": provider,
                    "question": f"capacity probe {probe_name} was not observed at the pinned block",
                }
            )
    graph_id = allocate_id(root, "SURFACE")
    record = {
        "schema": schema_for(root),
        "kind": "cross-contract-fork-surface",
        "id": graph_id,
        "created_at": utc_now(),
        "chain_id": campaign.get("chain", {}).get("chain_id"),
        "block_number": block_number,
        "contracts": contracts,
        "source_facts": source_facts,
        "fork_observations": rpc_observations,
        "dependencies": dependencies,
        "capital_primitives": capital_primitives,
        "ecosystem_traits": ecosystem_traits,
        "unknowns": unknowns,
        "completeness": "bounded to supplied contracts, source paths, probes, and the pinned block",
    }
    write_json_atomic(root / "surfaces" / f"{graph_id}.json", record)
    event(root, "surface.created", surface_id=graph_id, contracts=len(contracts), dependencies=len(dependencies), unknowns=len(unknowns))
    return record
