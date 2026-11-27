from __future__ import annotations

import re
from typing import Any

from .errors import ValidationError

EVM_REVISIONS = (
    "frontier", "homestead", "byzantium", "constantinople", "istanbul", "berlin",
    "london", "paris", "shanghai", "cancun", "prague", "osaka", "amsterdam",
)
HEX_32 = re.compile(r"^0x[0-9a-fA-F]{64}$")
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def validate_execution_context(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValidationError("execution_context must be an object")
    revision = value.get("evm_revision")
    if revision not in EVM_REVISIONS:
        raise ValidationError(f"unknown evm_revision: {revision}")
    chain_id = value.get("chain_id")
    block = value.get("block_number")
    if not isinstance(chain_id, int) or chain_id <= 0:
        raise ValidationError("execution_context.chain_id must be positive")
    if not isinstance(block, int) or block < 0:
        raise ValidationError("execution_context.block_number cannot be negative")
    tx = value.get("transaction")
    if not isinstance(tx, dict) or not isinstance(tx.get("type"), int):
        raise ValidationError("execution_context.transaction.type is required")

    delegation = value.get("eip7702")
    if delegation is not None:
        if EVM_REVISIONS.index(revision) < EVM_REVISIONS.index("prague"):
            raise ValidationError("EIP-7702 context requires Prague or newer")
        if not isinstance(delegation, dict):
            raise ValidationError("eip7702 must be an object")
        starting = delegation.get("starting_delegations", [])
        if not isinstance(starting, list):
            raise ValidationError("eip7702.starting_delegations must be an array")
        for item in starting:
            if not isinstance(item, dict) or not ADDRESS.fullmatch(str(item.get("authority", ""))):
                raise ValidationError("each starting delegation needs an authority address")
            if not ADDRESS.fullmatch(str(item.get("delegate", ""))):
                raise ValidationError("each starting delegation needs a delegate address")
            if not HEX_32.fullmatch(str(item.get("delegate_code_hash", ""))):
                raise ValidationError("each starting delegation needs delegate_code_hash")
        auth = delegation.get("authorization_list")
        if auth is not None and not isinstance(auth, list):
            raise ValidationError("eip7702.authorization_list must be null or an array")

    transient = value.get("eip1153")
    if transient is not None:
        if EVM_REVISIONS.index(revision) < EVM_REVISIONS.index("cancun"):
            raise ValidationError("EIP-1153 context requires Cancun or newer")
        if not isinstance(transient, dict):
            raise ValidationError("eip1153 must be an object")
        required = {"transaction_scoped", "revert_aware", "call_ownership", "static_context_checked"}
        if set(transient) < required:
            raise ValidationError(f"eip1153 missing semantics: {sorted(required - set(transient))}")
        if transient["transaction_scoped"] is not True or transient["revert_aware"] is not True:
            raise ValidationError("EIP-1153 state must be transaction-scoped and revert-aware")
        if transient["call_ownership"] not in ("CALL-callee", "DELEGATECALL-caller"):
            raise ValidationError("invalid EIP-1153 call ownership")
        if transient["static_context_checked"] is not True:
            raise ValidationError("EIP-1153 static-context restrictions must be checked")
    return value


def context_template(*, chain_id: int, block_number: int, evm_revision: str) -> dict[str, Any]:
    return {
        "chain_id": chain_id,
        "block_number": block_number,
        "block_hash": None,
        "evm_revision": evm_revision,
        "transaction": {"type": 2, "sender": None, "origin": None, "authorization_list_present": False},
        "eip7702": None,
        "eip1153": None,
    }
