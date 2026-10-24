"""Deterministic checkpoint comparison and independent backup outcome recording."""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .build import connect
from .official import digest, encoded
from .official_ingest import verify_run


def check(conn, scheduled_for):
    receipt = verify_run(conn, scheduled_for)
    job = receipt["job"]
    if job:
        if job["status"] == "running":
            status = (
                "running"
                if datetime.now(timezone.utc) - job["started_at"]
                < timedelta(minutes=16)
                else "interrupted"
            )
        elif job["collection_status"] not in {"success", "partial"}:
            status = "ingestion_failure"
        elif job["publication_status"] not in {
            "published",
            "unchanged_or_daily_staged",
        }:
            status = "publication_failure"
        elif job["backup_status"] != "local_verified":
            status = "backup_failure"
        elif job["collection_status"] == "partial":
            status = "partial_source_coverage"
        else:
            status = "success"
    else:
        status = "missed"
    from .official_offsite_job import gate

    recovery_current = gate(conn)
    if status in {"success", "partial_source_coverage"} and not recovery_current:
        active = conn.execute(
            "SELECT 1 FROM curated.official_jobs WHERE family='recovery' AND status='running' AND started_at>now()-interval '16 minutes' LIMIT 1"
        ).fetchone()
        status = "recovery_running" if active else "offsite_recovery_unqualified"
    performance = conn.execute(
        "SELECT state->>'status' AS status FROM curated.official_source_state WHERE family='performance'"
    ).fetchone()
    if performance and performance["status"] == "failed":
        status = "performance_or_restore_failure"
    summary = json.loads(json.dumps(receipt, default=str))
    summary.update(
        status=status,
        offsiteStatus="coverage_current" if recovery_current else "not_qualified",
    )
    fingerprint = digest(encoded(summary))
    previous = conn.execute(
        "SELECT state FROM curated.official_source_state WHERE family='health'"
    ).fetchone()
    unchanged = bool(previous and previous["state"].get("sha256") == fingerprint)
    conn.execute(
        "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('health',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
        (Jsonb({"sha256": fingerprint, "summary": summary}),),
    )
    return dict(summary, unchanged=unchanged)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["verify", "backup"])
    parser.add_argument("--scheduled-for")
    parser.add_argument("--job-id")
    parser.add_argument("--outcome", choices=["local_verified", "local_failed"])
    parser.add_argument("--sha256")
    args = parser.parse_args()
    with connect(
        os.environ["CURATED_DSN"], autocommit=True, row_factory=dict_row
    ) as conn:
        if args.operation == "backup":
            if not args.job_id or not args.outcome:
                parser.error("Backup requires job ID and independent outcome")
            if args.outcome == "local_verified" and (
                not args.sha256
                or len(args.sha256) != 64
                or any(c not in "0123456789abcdef" for c in args.sha256)
            ):
                parser.error("Verified backup requires SHA-256")
            result = conn.execute(
                "UPDATE curated.official_jobs SET backup_status=%s,receipt=receipt||%s WHERE job_id=%s RETURNING job_id",
                (
                    args.outcome,
                    Jsonb({"backupStatus": args.outcome, "backupSha256": args.sha256}),
                    args.job_id,
                ),
            ).fetchone()
            if not result:
                raise SystemExit("Unknown backup job")
            print(json.dumps({"jobId": args.job_id, "backupStatus": args.outcome}))
        else:
            if not args.scheduled_for:
                parser.error("Verifier requires expected scheduled occurrence")
            receipt = check(conn, args.scheduled_for)
            print(json.dumps(receipt, default=str))
            if receipt["status"] != "success":
                raise SystemExit(1)


if __name__ == "__main__":
    main()
