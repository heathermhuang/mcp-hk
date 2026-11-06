"""Bounded, resumable HTTP qualification of an explicit frozen candidate cohort.

No retries, source defaults, credential handling or semantic approvals. Preserve
every response checkpoint; --requests is an invocation ceiling, not a new quota.
Use --read-options only after marginal storage/recovery qualification.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

from mcp_open_data_hk.census_reports import location


def candidates(manifest):
    """Prioritize uncovered selection cohorts without dropping other candidates."""
    rows = [
        c
        for c in manifest["familyCandidates"]
        if c["lastStatus"] == "needs_selection"
        or (c["lastStatus"] == "needs_adapter" and location(c["sourceUrl"]))
    ]
    return sorted(
        rows,
        key=lambda c: (
            bool(c["acceptedSameDatasetAlternatives"]),
            c["family"],
            c["datasetId"],
            c["resourceId"],
        ),
    )


def main(args):
    manifest = json.load(gzip.open(args.manifest, "rt"))
    args.receipts.mkdir(parents=True, exist_ok=True)
    used = 0
    for candidate in candidates(manifest):
        if args.family and candidate["family"] != args.family:
            continue
        rid = candidate["resourceId"]
        discovery = args.receipts / (rid + "-options.json.gz")
        tasks = [(discovery, "schema", {})]
        scheduled = {("schema", "{}")}

        def schedule(operation, selection, *, immediate=False):
            canonical = json.dumps(selection, sort_keys=True)
            identity = (operation, canonical)
            if identity in scheduled:
                return
            scheduled.add(identity)
            key = hashlib.sha256(canonical.encode()).hexdigest()[:16]
            task = (
                args.receipts / (rid + "-" + key + "-" + operation + ".json.gz"),
                operation,
                selection,
            )
            if operation == "schema" and selection and not task[0].exists():
                query = args.receipts / (rid + "-" + key + "-query.json.gz")
                # A prior query already attempted this exact selection. Reuse
                # failures too, rather than retrying through another endpoint.
                leaf = (
                    "layer" in selection
                    or "sheet" in selection
                    or (
                        "recordPath" in selection
                        and (
                            not location(candidate["sourceUrl"])
                            or len(selection["recordPath"].split("/")) == 3
                        )
                    )
                )
                if query.exists() or (getattr(args, "query_options", False) and leaf):
                    task = (query, "query", selection)
            if immediate:
                tasks.insert(0, task)
            else:
                tasks.append(task)

        while tasks:
            target, operation, selection = tasks.pop(0)
            if target.exists():
                receipt = json.load(gzip.open(target, "rt"))
            else:
                if used >= args.requests:
                    print(
                        json.dumps(
                            {
                                "requests": used,
                                "nextResourceId": rid,
                                "state": "invocation_bound",
                            }
                        ),
                        flush=True,
                    )
                    return
                started = time.monotonic()
                request = urllib.request.Request(
                    "https://mcp.hk/api/v1/resources/" + rid + "/" + operation,
                    data=json.dumps(
                        {
                            **selection,
                            **(
                                {"limit": 1, "requireFresh": True}
                                if operation == "query"
                                else {}
                            ),
                        }
                    ).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "mcp.hk-backlog-qualification/1",
                    },
                )
                used += 1
                status, body = None, b""
                try:
                    try:
                        response = urllib.request.urlopen(request, timeout=135)
                    except urllib.error.HTTPError as exc:
                        response = exc
                    with response:
                        status = response.code
                        body = response.read(3_000_001)
                    if len(body) > 3_000_000:
                        raise ValueError("Qualification response exceeds receipt bound")
                    value = json.loads(body)
                except (OSError, ValueError) as exc:
                    value = {
                        "probeFailure": type(exc).__name__,
                        "responseBytes": len(body),
                        "responseSha256": hashlib.sha256(body).hexdigest(),
                    }
                receipt = {
                    "resourceId": rid,
                    "datasetId": candidate["datasetId"],
                    "operation": operation,
                    "selection": selection,
                    "checkedAt": time.time(),
                    "httpStatus": status,
                    "seconds": round(time.monotonic() - started, 4),
                    "response": value,
                }
                target.write_bytes(
                    gzip.compress(
                        json.dumps(receipt, ensure_ascii=False).encode(), mtime=0
                    )
                )
                print(
                    json.dumps(
                        {
                            "resourceId": rid,
                            "operation": operation,
                            "selection": selection,
                            "status": status,
                            "records": value.get(
                                "recordCount", value.get("meta", {}).get("total")
                            ),
                            "error": value.get("error", value.get("probeFailure")),
                            "requests": used,
                        }
                    ),
                    flush=True,
                )
                time.sleep(1.1)
            value = receipt["response"]
            if operation == "query" and receipt["httpStatus"] == 200:
                if not (
                    value.get("schema", {}).get("sourceResponseComplete") is True
                    and type(value.get("meta", {}).get("total")) is int
                    and value["meta"]["total"] >= 0
                    and isinstance(value.get("data", {}).get("items"), list)
                    and len(value["data"]["items"]) == min(value["meta"]["total"], 1)
                ):
                    raise ValueError(
                        "Query receipt lacks selected schema/count evidence"
                    )
            if (
                operation == "schema"
                and args.read_options
                and receipt["httpStatus"] == 200
            ):
                if value.get("structuredQueryable") or (
                    value.get("recordCount") is not None
                    and value.get("schema", {}).get("sourceResponseComplete") is True
                ):
                    # Qualify before sibling selections evict this accepted
                    # variant from the existing 50-variant/4 MB caches.
                    schedule("query", selection, immediate=True)
                    continue
                for group in value.get("selections", []):
                    for option in group["options"]:
                        # Only the generated local tool argument contract is used.
                        arguments = option.get("nextAction", {}).get("arguments", {})
                        argument = group["argument"]
                        if argument not in {
                            "layer",
                            "sheet",
                            "recordPath",
                        } or arguments != {
                            "resourceId": rid,
                            argument: option["value"],
                        }:
                            raise ValueError("Unexpected option contract")
                        selected = {argument: option["value"]}
                        schedule("schema", selected)
    print(
        json.dumps({"requests": used, "state": "frozen_selection_candidates_visited"}),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("receipts", type=Path)
    parser.add_argument("--requests", type=int, default=12)
    parser.add_argument("--family", choices=["arcgis", "wfs", "workbook"])
    parser.add_argument("--read-options", action="store_true")
    parser.add_argument(
        "--query-options",
        action="store_true",
        help="Qualify published leaf choices with query's schema/count/data response, avoiding a duplicate full read",
    )
    args = parser.parse_args()
    if not 1 <= args.requests <= 1000:
        parser.error("--requests must be 1..1000")
    main(args)
