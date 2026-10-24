"""Harmless local HTTP/MCP checks; no real source requests."""

import json
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
url = "http://localhost:18787/mcp"
headers = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": "2025-11-25",
}
results = {}
for name, payload in [
    (
        "initialize",
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "security-local-reference", "version": "1"},
            },
        },
    ),
    ("tools/list", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
    (
        "tools/call",
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "hk_data_packs", "arguments": {}},
        },
    ),
]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers
    )
    with opener.open(req, timeout=5) as response:
        body = response.read(262144).decode()
        assert response.status == 200
        assert '"result"' in body and '"isError":true' not in body
        results[name] = response.status
for method in ["PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]:
    req = urllib.request.Request(url, method=method)
    try:
        with opener.open(req, timeout=5) as response:
            status = response.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == (204 if method == "OPTIONS" else 405)
    results[method] = status
with opener.open(
    urllib.request.Request(
        url,
        headers={"Accept": "text/event-stream", "MCP-Protocol-Version": "2025-11-25"},
    ),
    timeout=5,
) as response:
    assert response.status == 200
    results["GET-SSE-headers"] = 200
print(
    json.dumps(
        {
            "test": "local-protocol",
            "statuses": results,
            "result": "pass",
            "client": "Python urllib HTTP fixture; protocol 2025-11-25; no model",
        }
    )
)
