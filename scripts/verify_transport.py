"""Bounded live checks of public HTTP/MCP arrival semantics and freshness.

Example: python scripts/verify_transport.py --base-url https://mcp.hk --mcp
No credentials. Receipts contain public provider data only. No automatic retries.
"""

import argparse
import json
import subprocess
import time
from pathlib import Path

CASES = [
    ("MTR", "4b51588763e1b021e5252500f88e5833", {"line": "TWL", "sta": "CEN"}),
    (
        "MTR-East-Rail",
        "4b51588763e1b021e5252500f88e5833",
        {"line": "EAL", "sta": "HUH"},
    ),
    ("Light-Rail", "32de1cc093c94945abccd4f4f5da0b78", {"station_id": "001"}),
    (
        "MTR-Bus",
        "91a85d4046b496b9c5a1116ab2653a81",
        {"routeName": "K12", "language": "en"},
    ),
    ("KMB", "284a055c48fd543d67208377727e7226", {"route": "1", "service_type": "1"}),
    ("LWB", "284a055c48fd543d67208377727e7226", {"route": "E32", "service_type": "1"}),
    (
        "Citybus",
        "2b1b8d6b425bf3ddd1e1ddb811d54ba4",
        {"stop_id": "001145", "route": "11"},
    ),
    (
        "NLB",
        "6364bb25c65c4f24f73b9b9a982c05a3",
        {"routeId": "1", "stopId": "1", "languageCode": "en"},
    ),
    (
        "Green-Minibus",
        "b9361a1598c2265a3992a54e4cabdf35",
        {"route_id": "2006408", "route_seq": "1", "stop_seq": "1"},
    ),
    (
        "Fortune-Ferry",
        "e34a14f5c386e36b39bdbcadfa1dda15",
        {"route_code": "NPKT"},
    ),
    (
        "Water-Taxi",
        "6b9abfae6619ecbd96c06b48a8a1bcdf",
        {"route_code": "WATERTAXI"},
    ),
    ("Sun-Ferry", "479f49ec6b78e5a94e4d176227488d95", {"routecode": "CECC"}),
    (
        "HKKF",
        "340cd0efe47f2162049e823b3beb9d77",
        {"route_id": "3", "direction": "inbound"},
    ),
]


def read(url, body=None, mcp=False):
    args = [
        "curl",
        "--noproxy",
        "*",
        "-sS",
        "--max-time",
        "90",
        "-D",
        "/dev/stderr",
        url,
    ]
    if body is not None:
        args += ["-H", "Content-Type: application/json", "--data-binary", "@-"]
    if mcp:
        args += ["-H", "Accept: application/json, text/event-stream"]
    result = subprocess.run(
        args,
        input=json.dumps(body).encode() if body is not None else None,
        capture_output=True,
        check=True,
    )
    raw = result.stdout.decode()
    if raw.startswith("event:") or raw.startswith("data:"):
        raw = next(line[6:] for line in raw.splitlines() if line.startswith("data: "))
    return json.loads(raw), result.stderr.decode()


def check(payload):
    assert "error" not in payload, payload
    live = payload["schema"]["transport"]
    assert live["operation"] == "arrivals" and live["cacheTTLSeconds"] <= 20, live
    assert live["freshUntil"] >= time.time(), live
    assert live["sourceAgeSeconds"] <= live["maxSourceAgeSeconds"], live
    assert not payload["provenance"][0]["stale"]
    return dict(
        state=live["arrivalState"],
        returned=len(payload["data"]["items"]),
        total=payload["meta"]["total"],
        sourceTimestamp=live["sourceTimestamp"],
        sourceAgeSeconds=live["sourceAgeSeconds"],
        ttl=live["cacheTTLSeconds"],
        source=payload["provenance"][0]["sourceUrl"],
        warnings=payload["warnings"],
        policy=live["policyVersion"],
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://mcp.hk")
    parser.add_argument("--mcp", action="store_true")
    parser.add_argument("--only", help="Comma-separated operator case names")
    parser.add_argument("--out", default="/tmp/mcp-transport-live.json")
    args = parser.parse_args()
    origin = args.base_url.rstrip("/")
    receipts = []
    for name, rid, parameters in CASES:
        if args.only and name not in args.only.split(","):
            continue
        entry = {"operator": name, "resourceId": rid, "parameters": parameters}
        for protocol in (["http", "mcp"] if args.mcp else ["http"]):
            # A failed HTTP query must not suppress the independent MCP probe.
            started = time.time()
            try:
                if protocol == "http":
                    payload, headers = read(
                        origin + "/api/v1/resources/" + rid + "/query",
                        {"parameters": parameters, "limit": 2, "requireFresh": True},
                    )
                    assert "cache-control: no-store" in headers.lower(), headers
                else:
                    rpc, _ = read(
                        origin + "/mcp",
                        {
                            "jsonrpc": "2.0",
                            "id": 1,
                            "method": "tools/call",
                            "params": {
                                "name": "hk_resource_query",
                                "arguments": {
                                    "resourceId": rid,
                                    "parameters": parameters,
                                    "limit": 2,
                                    "requireFresh": True,
                                },
                            },
                        },
                        True,
                    )
                    result = rpc["result"]
                    assert not result.get("isError"), result
                    payload = result.get("structuredContent") or json.loads(
                        result["content"][0]["text"]
                    )
                entry[protocol] = dict(
                    status="pass", checkedAt=started, **check(payload)
                )
                if protocol == "mcp" and entry["http"]["status"] == "pass":
                    assert entry["mcp"]["source"] == entry["http"]["source"]
            except Exception as exc:
                entry[protocol] = dict(
                    status="failed", checkedAt=started, error=str(exc)[:1500]
                )
        entry["status"] = (
            "pass"
            if all(entry[p]["status"] == "pass" for p in ["http", "mcp"] if p in entry)
            else "failed"
        )
        receipts.append(entry)
        print(json.dumps(entry, ensure_ascii=False), flush=True)
        Path(args.out).write_text(
            json.dumps(
                {"origin": origin, "checkedAt": time.time(), "results": receipts},
                ensure_ascii=False,
                indent=2,
            )
        )
    raise SystemExit(1 if any(r["status"] != "pass" for r in receipts) else 0)


if __name__ == "__main__":
    main()
