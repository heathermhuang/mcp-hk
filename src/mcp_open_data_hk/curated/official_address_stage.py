"""Durable measured 20 -> 100 -> 250 address admission under shared CR limits."""

import argparse
from datetime import datetime, timezone
import json
import os

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .build import connect
from .official import SourceRejected
from .official_offsite_job import gate


def usage(conn):
    checks = conn.execute(
        "SELECT outcome,checked_at FROM curated.official_address_checks WHERE checked_at>=(now() AT TIME ZONE 'UTC')::date"
    ).fetchall()
    old = conn.execute(
        "SELECT r.receipt FROM curated.official_runs r LEFT JOIN curated.official_jobs j ON j.job_id=r.run_id WHERE j.job_id IS NULL AND r.started_at>=(now() AT TIME ZONE 'UTC')::date"
    ).fetchall()
    legacy_reads = sum(
        sum(
            str(c.get("sourceUrl", "")).startswith(
                "https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/"
            )
            for c in r["receipt"].get("sourceChecks", [])
        )
        for r in old
    )
    errors = [r["outcome"] for r in checks if r["outcome"] != "success"] + [
        e.get("code", "unknown")
        for r in old
        for e in r["receipt"].get("addressFailures", [])
    ]
    policy = conn.execute(
        "SELECT state FROM curated.official_source_state WHERE family='address_policy'"
    ).fetchone()
    limit = int(policy["state"]["dailyLimit"]) if policy else 20
    used = len(checks) + legacy_reads
    return {
        "dailyLimit": limit,
        "attempts": used,
        "remaining": max(0, limit - used),
        "failures": len(errors),
        "failureCodes": errors,
        "latestCheckAt": max((r["checked_at"] for r in checks), default=None),
    }


def set_stage(conn, target):
    if target not in {20, 100, 250}:
        raise ValueError("Qualified address stages are 20, 100 and 250")
    if target > 20 and not gate(conn):
        raise SourceRejected("ADDRESS_RECOVERY_GATE")
    before = usage(conn)
    hold = conn.execute(
        "SELECT 1 FROM curated.official_source_state WHERE family='cr' AND hold_until>now()"
    ).fetchone()
    if hold and target > 20:
        raise SourceRejected("SOURCE_HOLD")
    evidence = {
        "dailyLimit": target,
        "qualifiedAt": datetime.now(timezone.utc).isoformat(),
    }
    if target == 250:
        if (
            before["dailyLimit"] < 100
            or before["attempts"] < 100
            or before["failures"] / before["attempts"] > 0.05
            or any(code != "SOURCE_NO_MATCH" for code in before["failureCodes"])
        ):
            raise SourceRejected("ADDRESS_100_PILOT_NOT_QUALIFIED")
        jobs = conn.execute(
            "SELECT receipt FROM curated.official_jobs WHERE family='cr' AND operation IN ('addresses','freshness') AND started_at>=(now() AT TIME ZONE 'UTC')::date AND status IN ('success','partial')"
        ).fetchall()
        durations = [
            c["durationSeconds"]
            for j in jobs
            for c in j["receipt"].get("sourceChecks", [])
            if str(c.get("sourceUrl", "")).startswith(
                "https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/"
            )
            and isinstance(c.get("durationSeconds"), (int, float))
        ]
        if (
            len(durations) < 50
            or sum(durations) / len(durations) > 7.5
            or sorted(durations)[int(len(durations) * 0.95) - 1] > 20
            or any(j["receipt"].get("maxRssKiB", 0) > 512 * 1024 for j in jobs)
        ):
            raise SourceRejected("ADDRESS_LATENCY_OR_MEMORY_GATE")
        restored = conn.execute(
            "SELECT state FROM curated.official_source_state WHERE family='offsite_restore'"
        ).fetchone()
        if (
            not restored
            or not restored["state"].get("verifiedAt")
            or not before["latestCheckAt"]
            or datetime.fromisoformat(restored["state"]["verifiedAt"])
            < before["latestCheckAt"]
        ):
            raise SourceRejected("ADDRESS_ENLARGED_RESTORE_REQUIRED")
        evidence.update(
            pilotAttempts=before["attempts"],
            pilotFailures=before["failures"],
            timedSamples=len(durations),
            meanSourceSeconds=sum(durations) / len(durations),
        )
    conn.execute(
        "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('address_policy',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
        (Jsonb(evidence),),
    )
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", type=int, choices=[20, 100, 250])
    args = parser.parse_args()
    with connect(
        os.environ["CURATED_DSN"], autocommit=True, row_factory=dict_row
    ) as conn:
        result = set_stage(conn, args.set) if args.set else usage(conn)
    print(json.dumps(result, default=str))


if __name__ == "__main__":
    main()
