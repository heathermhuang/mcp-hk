"""Compact non-collecting comparison for existing qualification owners.

Invoke from the existing follow-up; never install another timer/model loop. Four
bounded public status reads produce a changed checkpoint only. No acceptance gate
passes through this comparison and no failed source operation is retried.
"""

import argparse
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import httpx

from .acceptance import Journal, canonical, sha

PATHS = {
    "company": "/api/v1/companies/updates/status",
    "racing": "/api/v1/racing/status",
    "sfc": "/api/v1/sfc/status",
    "hkex": "/api/v1/hkex/latest/status",
}


def bounded_get(client, path):
    body = bytearray()
    with client.stream("GET", "https://mcp.hk" + path) as response:
        if response.status_code != 200:
            return {
                "httpStatus": response.status_code,
                "retryAfter": response.headers.get("retry-after"),
            }
        for block in response.iter_bytes(32768):
            if len(body) + len(block) > 1024 * 1024:
                raise ValueError("QUALIFICATION_STATUS_LIMIT")
            body.extend(block)
    return json.loads(body)


def project(source, value):
    """Exclude heartbeat clocks/resources; retain changed facts and failures."""
    if "httpStatus" in value:
        return value
    if source == "hkex":
        return {k: value.get(k) for k in ("state", "version", "coverage", "updater")}
    data = value["data"]
    if source == "company":
        maintenance = data["maintenance"]
        return {
            "version": value["meta"]["version"],
            "weeklyFiles": data["coverage"]["acceptedWeeklyFiles"],
            "missingWeeks": data["coverage"]["missingWeeks"],
            "jobs": maintenance["jobs"],
            "recoveryGateOpen": maintenance["backfillRecoveryGateOpen"],
            "offsite": maintenance["offsite"],
            "rpoQualified": maintenance["offsiteRpoQualified"],
            "nextDue": maintenance["nextConfiguredDueAt"],
        }
    if source == "racing":
        return {
            "version": data["acceptedVersion"],
            "state": data["state"],
            "coverage": data["coverage"],
            "seasons": data["seasonCoverage"],
            "dividends": data["dividendCoverage"],
            "profiles": {
                k: data["profileObservations"][k] for k in ("accepted", "queue")
            },
            "hold": data.get("hold"),
            "collection": {
                k: v
                for k, v in (data.get("durableIngestion") or {}).items()
                if k not in {"checkedAt", "now"}
            },
        }
    return {
        k: data.get(k)
        for k in (
            "state",
            "acceptedVersion",
            "reasonCode",
            "cohort",
            "lastRun",
            "unresolvedRequests",
            "modes",
            "hold",
        )
    }


def compare(folder, values):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = folder / "checkpoint.json"
    current = {k: project(k, v) for k, v in values.items()}
    digest = sha(canonical(current))
    previous = json.loads(path.read_text()) if path.exists() else None
    if previous and previous["sha256"] == digest:
        return None
    receipt = {
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "sha256": digest,
        "previousSha256": previous["sha256"] if previous else None,
        "sources": current,
        "providerRequests": 0,
        "acceptancePassed": False,
        "owner": "existing_source_and_company_qualification_owners",
    }
    immutable = folder / (digest + ".json")
    if not immutable.exists():
        with immutable.open("xb") as out:
            out.write(canonical(receipt) + b"\n")
    temporary = folder / (".checkpoint-" + str(os.getpid()))
    with temporary.open("xb") as out:
        out.write(canonical(receipt) + b"\n")
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--source", choices=list(PATHS), action="append")
    args = parser.parse_args()
    guard = Journal(
        Path(args.folder) / "compare.sqlite3", {"version": "comparison-v1", "cases": []}
    )
    with (
        guard.owner(),
        httpx.Client(timeout=20, trust_env=False, follow_redirects=False) as client,
    ):
        receipt = compare(
            args.folder,
            {
                k: bounded_get(client, v)
                for k, v in PATHS.items()
                if not args.source or k in args.source
            },
        )
    if receipt:
        print(
            json.dumps(
                {
                    k: receipt[k]
                    for k in (
                        "observedAt",
                        "sha256",
                        "previousSha256",
                        "acceptancePassed",
                    )
                }
            )
        )


if __name__ == "__main__":
    main()
