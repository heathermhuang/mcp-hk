"""Independent ordinary-scheduler recovery jobs and fail-closed catch-up gate."""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .build import connect
from .official_state import begin_job


def finish(conn, job_id, receipt, outcome, schedule_kind):
    if outcome == "offsite_verified":
        if not re.fullmatch(
            r"curated/official/daily/\d{8}T\d{6}Z-[a-f0-9]{8}",
            receipt.get("prefix", ""),
        ) or set(receipt.get("artifacts", {})) != {
            "official.dump",
            "source.json",
            "manifest.json",
        }:
            raise ValueError("Unqualified offsite receipt")
        for artifact in receipt["artifacts"].values():
            if (
                not re.fullmatch(r"[a-f0-9]{64}", artifact.get("sha256", ""))
                or type(artifact.get("bytes")) is not int
                or artifact["bytes"] <= 0
            ):
                raise ValueError("Unqualified offsite artifact")
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(68002408)")
        row = conn.execute(
            "UPDATE curated.official_jobs SET status=%s,collection_status='not_applicable',publication_status='not_applicable',backup_status=%s,finished_at=CASE WHEN %s THEN NULL ELSE now() END,receipt=%s WHERE job_id=%s AND family='recovery' AND status='running' AND backup_status='not_observed' RETURNING job_id,started_at",
            (
                "running" if outcome == "offsite_verified" else "failed",
                (
                    "offsite_verified_restore_pending"
                    if outcome == "offsite_verified"
                    else outcome
                ),
                outcome == "offsite_verified",
                Jsonb(dict(receipt, scheduleKind=schedule_kind)),
                job_id,
            ),
        ).fetchone()
        if not row:
            raise ValueError("No owning running recovery job")
        attempt = {
            "jobId": job_id,
            "status": outcome,
            "scheduleKind": schedule_kind,
            "finishedAt": datetime.now(timezone.utc).isoformat(),
            "startedAt": row["started_at"].isoformat(),
        }
        old = conn.execute(
            "SELECT state FROM curated.official_source_state WHERE family='offsite' FOR UPDATE"
        ).fetchone()
        value = dict(old["state"]) if old else {}
        if attempt["startedAt"] >= value.get("lastAttempt", {}).get("startedAt", ""):
            value["lastAttempt"] = attempt
        if outcome == "offsite_verified" and attempt["startedAt"] >= value.get(
            "lastSuccess", {}
        ).get("startedAt", ""):
            value["lastSuccess"] = dict(receipt, **attempt)
        conn.execute(
            "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('offsite',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
            (Jsonb(value),),
        )


def qualify_restore(conn, proof):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(68002408)")
        latest = conn.execute(
            "SELECT state->'lastSuccess' AS success FROM curated.official_source_state WHERE family='offsite' FOR UPDATE"
        ).fetchone()
        if (
            not latest
            or not proof.get("freshOffsiteRestoreVerified")
            or proof.get("backupSha256")
            != latest["success"]["artifacts"]["official.dump"]["sha256"]
            or proof.get("prefix") != latest["success"]["prefix"]
        ):
            raise ValueError("Restore proof must match latest exact offsite dump")
        migrations = {
            r["version"]: r["sha256"]
            for r in conn.execute(
                "SELECT version,sha256 FROM curated.official_migrations"
            )
        }
        if proof.get("migrations") != migrations or not proof.get("performancePassed"):
            raise ValueError("Restored schema or performance qualification differs")
        settled = conn.execute(
            "UPDATE curated.official_jobs SET status='success',backup_status='offsite_verified',finished_at=now(),receipt=receipt||%s WHERE job_id=%s AND status='running' AND backup_status='offsite_verified_restore_pending' RETURNING job_id",
            (Jsonb({"restore": proof}), latest["success"]["jobId"]),
        ).fetchone()
        if not settled:
            raise ValueError("No owning pending restore job")
        state = {
            "verified": True,
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
            "backupSha256": proof["backupSha256"],
            "migrations": migrations,
            "prefix": latest["success"]["prefix"],
            "qualifiedWeekPairs": proof.get("qualifiedWeekPairs"),
            "stagedReadP95Ms": proof.get("stagedReadP95Ms"),
        }
        conn.execute(
            "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('offsite_restore',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
            (Jsonb(state),),
        )
        conn.execute(
            "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('performance',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
            (
                Jsonb(
                    {
                        "status": "passed",
                        "qualifiedWeekPairs": proof.get("qualifiedWeekPairs"),
                        "stagedReadP95Ms": proof.get("stagedReadP95Ms"),
                    }
                ),
            ),
        )


def restore_failed(conn, job_id):
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(68002408)")
        conn.execute(
            "UPDATE curated.official_jobs SET status='failed',backup_status='restore_failed',finished_at=now() WHERE job_id=%s AND family='recovery' AND status='running'",
            (job_id,),
        )
        latest = conn.execute(
            "SELECT state->'lastSuccess'->>'jobId' AS job FROM curated.official_source_state WHERE family='offsite'"
        ).fetchone()
        if latest and latest["job"] == job_id:
            conn.execute(
                "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('performance',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
                (
                    Jsonb(
                        {
                            "status": "failed",
                            "jobId": job_id,
                            "errorCode": "RESTORE_OR_PERFORMANCE_VERIFICATION_FAILED",
                        }
                    ),
                ),
            )


def gate(conn):
    rows = {
        r["family"]: r["state"]
        for r in conn.execute(
            "SELECT family,state FROM curated.official_source_state WHERE family IN ('offsite','offsite_restore','performance')"
        )
    }
    success = rows.get("offsite", {}).get("lastSuccess", {})
    restored = rows.get("offsite_restore", {})
    try:
        fresh = datetime.fromisoformat(success["finishedAt"]) >= datetime.now(
            timezone.utc
        ) - timedelta(hours=24)
    except (KeyError, ValueError, TypeError):
        fresh = False
    latest = conn.execute(
        "SELECT status,started_at FROM curated.official_jobs WHERE family='recovery' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if (
        latest
        and latest["status"] == "running"
        and latest["started_at"].isoformat() >= success.get("startedAt", "")
    ):
        fresh = False
    migrations = {
        r["version"]: r["sha256"]
        for r in conn.execute("SELECT version,sha256 FROM curated.official_migrations")
    }
    return bool(
        fresh
        and rows.get("performance", {}).get("status") != "failed"
        and rows.get("offsite", {}).get("lastAttempt", {}).get("status")
        == "offsite_verified"
        and restored.get("verified")
        and restored.get("migrations") == migrations
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=["begin", "finish", "gate", "qualify-restore", "restore-failed"],
    )
    parser.add_argument("--scheduled-for")
    parser.add_argument("--job-id")
    parser.add_argument("--receipt")
    parser.add_argument("--outcome", choices=["offsite_verified", "offsite_failed"])
    parser.add_argument(
        "--schedule-kind", choices=["daily", "qualification"], default="daily"
    )
    args = parser.parse_args()
    with connect(
        os.environ["CURATED_DSN"], autocommit=True, row_factory=dict_row
    ) as conn:
        if args.operation == "begin":
            if not args.scheduled_for:
                parser.error("Expected scheduled occurrence required")
            job = begin_job(conn, "offsite", args.scheduled_for, family="recovery")
            print(
                json.dumps({"jobId": job, "status": "running" if job else "duplicate"})
            )
        elif args.operation == "finish":
            if not args.job_id or not args.outcome:
                parser.error("Job and outcome required")
            receipt = (
                json.loads(Path(args.receipt).read_text())
                if args.receipt
                else {"errorCode": "OFFSITE_UPLOAD_OR_BACKUP_FAILED"}
            )
            finish(conn, args.job_id, receipt, args.outcome, args.schedule_kind)
            print(
                json.dumps(
                    {
                        "jobId": args.job_id,
                        "backupStatus": (
                            "offsite_verified_restore_pending"
                            if args.outcome == "offsite_verified"
                            else args.outcome
                        ),
                    }
                )
            )
        elif args.operation == "qualify-restore":
            qualify_restore(conn, json.loads(Path(args.receipt).read_text()))
            print(json.dumps({"restoreQualified": True, "catchupGateOpen": gate(conn)}))
        elif args.operation == "restore-failed":
            if not args.job_id:
                parser.error("Owning job required")
            restore_failed(conn, args.job_id)
            print(json.dumps({"restoreQualified": False, "catchupGateOpen": False}))
        else:
            allowed = gate(conn)
            print(
                json.dumps(
                    {
                        "catchupAllowed": allowed,
                        "requires": "verified upload within 24h and independent restore of current schema",
                    }
                )
            )
            if not allowed:
                raise SystemExit(1)


if __name__ == "__main__":
    main()
