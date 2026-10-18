"""Exact approved public sources through the existing authenticated Worker."""

import json
import os
from importlib.resources import files
from urllib.parse import urlsplit

REGISTRY = json.loads(
    files("mcp_open_data_hk").joinpath("source-relay-targets.json").read_text()
)
TARGETS = REGISTRY["targets"]
ORIGINS = {"https://mcp.hk", "https://mcp-hk.measurable.workers.dev"}


def relay_request(url, headers=None, payload=None):
    if payload is not None or any(
        k.lower() in {"authorization", "cookie"} for k in (headers or {})
    ):
        return None
    source_id = next((key for key, target in TARGETS.items() if target == url), None)
    if not source_id:
        return None
    bootstrap = urlsplit(os.environ.get("MCP_HK_BOOTSTRAP_URL", ""))
    origin = f"{bootstrap.scheme}://{bootstrap.netloc}"
    token = os.environ.get("MCP_HK_OPS_TOKEN", "")
    if (
        origin not in ORIGINS
        or bootstrap.path != "/__ops/snapshot"
        or bootstrap.query
        or bootstrap.fragment
        or not token
    ):
        return None
    return origin + "/__ops/source-relay?resourceId=" + source_id, {
        "Authorization": "Bearer " + token
    }
