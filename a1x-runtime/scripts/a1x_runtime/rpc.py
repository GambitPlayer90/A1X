from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .errors import A1XError


def rpc_call(url: str, method: str, params: list[Any] | None = None, *, timeout: float = 3.0) -> Any:
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or []}).encode()
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise A1XError(f"JSON-RPC call failed ({method}): {type(exc).__name__}") from exc
    if body.get("error"):
        raise A1XError(f"JSON-RPC error ({method}): {body['error']}")
    return body.get("result")


def hex_int(value: str) -> int:
    return int(value, 16)
