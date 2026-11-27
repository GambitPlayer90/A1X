from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .artifacts import ingest_artifact
from .atomic import (
    canonical_bytes,
    digest_json,
    named_lock,
    read_json,
    write_json_atomic,
)
from .errors import ValidationError
from .recon import create_recon_pack
from .records import allocate_id, event, require_v4_campaign, schema_for, utc_now

DEFAULT_ENDPOINT = "https://api.etherscan.io/v2/api"
MAX_RESPONSE_BYTES = 32 * 1024 * 1024


def _fetch(endpoint: str, query: dict[str, str], *, retries: int = 3) -> dict[str, Any]:
    url = endpoint + "?" + urllib.parse.urlencode(query)
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "A1X/4.2"})
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise ValidationError("explorer response exceeds 32 MiB")
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValidationError("explorer response is not an object")
            return value
        except ValidationError:
            raise
        except Exception:
            if attempt + 1 == retries:
                # Do not include exception text: HTTP errors can embed the URL/API key.
                raise ValidationError("explorer retrieval failed after bounded retries") from None
            time.sleep(0.25 * (2 ** attempt))
    raise AssertionError("unreachable")


def retrieve_verified_contract(
    root: Path, *, address: str, api_env: str = "ETHERSCAN_API_KEY",
    endpoint: str = DEFAULT_ENDPOINT, campaign_epoch: int | None = None,
    idempotency_key: str,
) -> dict[str, Any]:
    if not idempotency_key.strip():
        raise ValidationError("explorer retrieval requires a non-empty idempotency key")
    with named_lock(root, "explorer:" + idempotency_key):
        return _retrieve_verified_contract_locked(
            root,
            address=address,
            api_env=api_env,
            endpoint=endpoint,
            campaign_epoch=campaign_epoch,
            idempotency_key=idempotency_key,
        )


def _retrieve_verified_contract_locked(
    root: Path, *, address: str, api_env: str,
    endpoint: str, campaign_epoch: int | None, idempotency_key: str,
) -> dict[str, Any]:
    campaign = require_v4_campaign(root)
    epoch = int(campaign.get("epoch", 0))
    if campaign_epoch is not None and campaign_epoch != epoch:
        raise ValidationError(f"campaign epoch mismatch: requested {campaign_epoch}, current {epoch}")
    if not re.fullmatch(r"0x[0-9a-fA-F]{40}", address):
        raise ValidationError("explorer address must be a 20-byte hexadecimal EVM address")
    if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", api_env):
        raise ValidationError("explorer API environment variable must be an uppercase identifier")
    api_key = os.environ.get(api_env)
    if not api_key:
        raise ValidationError(f"explorer API environment variable is unset: {api_env}")
    chain_id = campaign["chain"].get("chain_id")
    if not isinstance(chain_id, int) or chain_id <= 0:
        raise ValidationError("explorer retrieval requires a campaign chain ID")
    request_hash = digest_json({"provider": "etherscan-v2", "chain_id": chain_id, "address": address.lower(), "endpoint": endpoint})
    retrievals = root / "recon" / "retrievals"
    retrievals.mkdir(parents=True, exist_ok=True)
    for path in retrievals.glob("RET-*.json"):
        existing = read_json(path)
        if existing.get("idempotency_key") == idempotency_key:
            if existing.get("request_sha256") != request_hash:
                raise ValidationError("idempotency key was already used for a different explorer request")
            return existing

    response = _fetch(endpoint, {
        "chainid": str(chain_id), "module": "contract", "action": "getsourcecode",
        "address": address, "apikey": api_key,
    })
    result = response.get("result")
    if response.get("status") != "1" or not isinstance(result, list) or not result or not isinstance(result[0], dict):
        raise ValidationError("explorer did not return verified-contract metadata")
    metadata = result[0]
    source_available = bool(str(metadata.get("SourceCode", "")).strip())
    abi_available = str(metadata.get("ABI", "")).strip() not in {"", "Contract source code not verified"}
    raw = canonical_bytes(response)
    with tempfile.NamedTemporaryFile(prefix="a1x-explorer-", suffix=".json", dir=root, delete=False) as handle:
        temporary = Path(handle.name)
        handle.write(raw)
    try:
        artifact = ingest_artifact(root, temporary, media_type="application/json", role="explorer-provider-response", producer="etherscan-v2")
    finally:
        temporary.unlink(missing_ok=True)

    proxy = str(metadata.get("Proxy", "0")) == "1"
    implementation = str(metadata.get("Implementation", "")).strip()
    facts = [{
        "statement": f"Etherscan V2 returned {'verified source and ' if source_available else ''}{'ABI' if abi_available else 'contract metadata'} for {address.lower()} on chain {chain_id}",
        "source": artifact["id"], "confidence": "provider-observed-unpinned",
    }]
    unknowns = []
    if proxy:
        unknowns.append({
            "question": f"Which implementation governed {address.lower()} at pinned block {campaign['chain'].get('block_number')}?",
            "why_it_matters": "explorer proxy metadata may describe current state rather than the campaign block",
            "next_probe": "resolve implementation storage/beacon at the pinned block through the credential-free prestate service",
        })
    recon = create_recon_pack(root, facts=facts, unknowns=unknowns, artifact_ids=[artifact["id"]])
    retrieval_id = allocate_id(root, "RET")
    record = {
        "schema": schema_for(root), "kind": "explorer-retrieval", "id": retrieval_id,
        "created_at": utc_now(), "campaign_epoch": epoch, "idempotency_key": idempotency_key,
        "request_sha256": request_hash, "provider": "etherscan-v2", "api_env": api_env,
        "chain_id": chain_id, "block_number": campaign["chain"].get("block_number"),
        "address": address.lower(), "artifact_id": artifact["id"], "artifact_sha256": artifact["sha256"],
        "recon_version": recon["version"], "source_available": source_available, "abi_available": abi_available,
        "contract_name": str(metadata.get("ContractName", "")), "compiler_version": str(metadata.get("CompilerVersion", "")),
        "proxy": proxy, "provider_current_implementation": implementation or None,
        "pinned_implementation_verified": False if proxy else None,
        "warning": "Explorer metadata is provider-observed and not proof of deployment state at the pinned campaign block.",
        "upstream_secret_exposed": False,
    }
    write_json_atomic(retrievals / f"{retrieval_id}.json", record)
    event(root, "explorer.retrieved", retrieval_id=retrieval_id, provider="etherscan-v2", address=address.lower(), artifact_id=artifact["id"], recon_version=recon["version"])
    return record


def show_retrieval(root: Path, retrieval_id: str) -> dict[str, Any]:
    return read_json(root / "recon" / "retrievals" / f"{retrieval_id}.json")
