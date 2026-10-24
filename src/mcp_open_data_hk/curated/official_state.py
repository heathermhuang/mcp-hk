"""Durable source-independent checkpoints. No network work holds a transaction."""

import hashlib
from datetime import datetime, timezone
from importlib.resources import files

from psycopg.types.json import Jsonb

from .official import DDL, SourceRejected, digest, encoded

TRANSFORM = "official-v2"
LOCK = 68002406


def migrate(conn):
    source = (
        files(__package__)
        .joinpath("migrations/001_official_maintenance.sql")
        .read_text()
    )
    sha = digest(source.encode())
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK + 1,))
        conn.execute("CREATE SCHEMA IF NOT EXISTS curated")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS curated.official_migrations(version text PRIMARY KEY,sha256 text NOT NULL,applied_at timestamptz NOT NULL DEFAULT now())"
        )
        applied = conn.execute(
            "SELECT sha256 FROM curated.official_migrations WHERE version='001'"
        ).fetchone()
        if applied:
            if applied["sha256"] != sha:
                raise SourceRejected("MIGRATION_SOURCE_CHANGED")
            return
        conn.execute(DDL)
        conn.execute(source)
        conn.execute(
            "INSERT INTO curated.official_migrations(version,sha256) VALUES('001',%s)",
            (sha,),
        )


def transform_hash():
    h = hashlib.sha256()
    for name in ("official.py", "official_ingest.py", "official_state.py"):
        h.update(files(__package__).joinpath(name).read_bytes())
    return h.hexdigest()


def pointer(conn):
    row = conn.execute("SELECT version FROM curated.official_pointer").fetchone()
    return row["version"] if row else None


def reserve(conn, max_bytes=8 * 1024 * 1024):
    # Reserve before sending. An unknown/crashed request consumes its entire bound.
    with conn.transaction():
        hold = conn.execute(
            "SELECT hold_until>now() AS held FROM curated.official_source_state WHERE family='cr'"
        ).fetchone()
        if hold and hold["held"]:
            raise SourceRejected("SOURCE_HOLD")
        row = conn.execute(
            "INSERT INTO curated.official_daily_budgets(provider,day,requests,bytes) VALUES('cr',(now() AT TIME ZONE 'UTC')::date,1,%s) ON CONFLICT(provider,day) DO UPDATE SET requests=official_daily_budgets.requests+1,bytes=official_daily_budgets.bytes+EXCLUDED.bytes WHERE official_daily_budgets.requests<500 AND official_daily_budgets.bytes+EXCLUDED.bytes<=1073741824 RETURNING requests,day",
            (max_bytes,),
        ).fetchone()
        if not row:
            raise SourceRejected("DAILY_SOURCE_BUDGET")
    return max_bytes, row["day"]


def settle_bytes(conn, reserved, actual):
    bound, day = reserved
    conn.execute(
        "UPDATE curated.official_daily_budgets SET bytes=bytes-%s+%s WHERE provider='cr' AND day=%s",
        (bound, actual, day),
    )


def hold(conn, seconds):
    conn.execute(
        "INSERT INTO curated.official_source_state(family,hold_until) VALUES('cr',now()+(%s*interval '1 second')) ON CONFLICT(family) DO UPDATE SET hold_until=greatest(official_source_state.hold_until,EXCLUDED.hold_until)",
        (max(60, min(seconds, 604800)),),
    )


def begin_job(conn, operation, scheduled_for, family="cr"):
    stamp = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Scheduled occurrence requires a timezone")
    stamp = stamp.astimezone(timezone.utc)
    job_id = digest(encoded([family, operation, stamp.isoformat()]))[:32]
    row = conn.execute(
        "INSERT INTO curated.official_jobs(job_id,family,operation,scheduled_for) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING job_id",
        (job_id, family, operation, stamp),
    ).fetchone()
    return job_id if row else None


def inventory(conn, links, sha):
    with conn.transaction():
        conn.execute(
            "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('inventory_baseline',now(),%s) ON CONFLICT DO NOTHING",
            (Jsonb({"sha256": sha, "sourceKeys": sorted(links)}),),
        )
        conn.execute("UPDATE curated.official_inventory SET present=false")
        for url in links:
            conn.execute(
                "INSERT INTO curated.official_inventory(source_key,week,register,verification_url,inventory_hash) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(source_key) DO UPDATE SET present=true,checked_at=now(),inventory_hash=EXCLUDED.inventory_hash",
                (
                    url,
                    url[-12:-4],
                    "local" if "RNC063L_" in url else "foreign",
                    url[:-3] + "xls",
                    sha,
                ),
            )
        conn.execute(
            "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('inventory',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
            (Jsonb({"sha256": sha, "files": len(links)}),),
        )


def stage_group(conn, group, captures):
    with conn.transaction():
        valid = conn.execute(
            "SELECT count(*) AS n FROM curated.official_captures WHERE capture_id=ANY(%s) AND valid",
            (list(set(captures.values())),),
        ).fetchone()["n"]
        if valid != len(set(captures.values())):
            raise SourceRejected("UNVALIDATED_STAGING")
        conn.execute(
            "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES(%s,now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
            (group, Jsonb({"status": "verified", "captures": len(captures)})),
        )
        for key, capture in captures.items():
            conn.execute(
                "INSERT INTO curated.official_staged(source_key,capture_id,group_key) VALUES(%s,%s,%s) ON CONFLICT(source_key) DO UPDATE SET capture_id=EXCLUDED.capture_id,group_key=EXCLUDED.group_key,staged_at=now()",
                (key, capture, group),
            )
            conn.execute(
                "UPDATE curated.official_inventory SET state='verified' WHERE source_key=%s",
                (key,),
            )


def seed_queue(conn):
    # Only exact identities with qualified company-event evidence are eligible.
    conn.execute(
        "INSERT INTO curated.official_address_queue(entity_id) SELECT DISTINCT r.entity_id FROM curated.official_records r JOIN curated.official_members m USING(capture_id) JOIN curated.official_pointer p USING(version) WHERE r.record->>'kind'='company_event' ON CONFLICT DO NOTHING"
    )

    conn.execute(
        "UPDATE curated.official_address_queue q SET last_success=(c.receipt->>'fetchedAt')::timestamptz,latest_capture=c.capture_id,next_due=(c.receipt->>'fetchedAt')::timestamptz+interval '90 days',outcome='success' FROM curated.official_records r JOIN curated.official_members m USING(capture_id) JOIN curated.official_pointer p USING(version) JOIN curated.official_captures c USING(capture_id) WHERE q.entity_id=r.entity_id AND q.last_attempt IS NULL AND q.last_success IS NULL AND r.record->>'kind'='address_observation'"
    )


def plan(conn):
    rows = conn.execute(
        "SELECT i.week,count(*) AS files,count(s.capture_id) AS staged,count(m.capture_id) AS published FROM curated.official_inventory i LEFT JOIN curated.official_staged s USING(source_key) LEFT JOIN curated.official_pointer p ON true LEFT JOIN curated.official_members m ON m.version=p.version AND m.source_key=i.source_key WHERE i.present GROUP BY i.week ORDER BY i.week"
    ).fetchall()
    return {
        "weeks": rows,
        "missingPairs": sum(r["published"] < 2 for r in rows),
        "pendingPairs": sum(r["staged"] < 2 and r["published"] < 2 for r in rows),
        "discoveredFiles": sum(r["files"] for r in rows),
        "downloadedFiles": conn.execute(
            "SELECT count(*) AS n FROM curated.official_inventory i WHERE i.present AND EXISTS(SELECT 1 FROM curated.official_captures c WHERE c.source_key=i.source_key)"
        ).fetchone()["n"],
        "rejectedFiles": conn.execute(
            "SELECT count(*) AS n FROM curated.official_inventory WHERE present AND state='rejected'"
        ).fetchone()["n"],
        "sourceHoldUntil": (
            conn.execute(
                "SELECT hold_until::text AS hold_until FROM curated.official_source_state WHERE family='cr' AND hold_until>now()"
            ).fetchone()
            or {}
        ).get("hold_until"),
        "stagedFiles": sum(r["staged"] for r in rows),
        "publishedFiles": sum(r["published"] for r in rows),
        "missingInventoryFiles": conn.execute(
            "SELECT count(*) AS n FROM curated.official_inventory WHERE NOT present"
        ).fetchone()["n"],
    }


def finish_job(conn, job_id, receipt):
    conn.execute(
        "UPDATE curated.official_jobs SET status=%s,collection_status=%s,publication_status=%s,published_at=CASE WHEN %s THEN now() ELSE published_at END,finished_at=now(),receipt=%s WHERE job_id=%s",
        (
            receipt["status"],
            receipt["status"],
            receipt.get("publicationStatus", "not_attempted"),
            receipt.get("published", False),
            Jsonb(receipt),
            job_id,
        ),
    )
    conn.execute(
        "UPDATE curated.official_runs SET status=%s,finished_at=now(),receipt=%s WHERE run_id=%s",
        (receipt["status"], Jsonb(receipt), job_id),
    )


def collect_group(conn, group, scheduled_for, collect):
    job = begin_job(conn, "collect", scheduled_for, family=group)
    if not job:
        return
    try:
        collect()
    except Exception:
        conn.execute(
            "UPDATE curated.official_jobs SET status='failed',collection_status='failed',finished_at=now() WHERE job_id=%s",
            (job,),
        )
        raise
    conn.execute(
        "UPDATE curated.official_jobs SET status='success',collection_status='success',publication_status='staged_only',finished_at=now() WHERE job_id=%s",
        (job,),
    )
