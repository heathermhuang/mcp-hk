"""Check a retrieved logical restore, then measure the effective staged read model."""

import argparse
import hashlib
import json
import os
import time
import sys
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from .build import connect
from .official_recovery import snapshot, membership_hash
from .official_read import OfficialReader
from .read import Reader, prefix_end
from .normalize import search_key
from .official_queries import EFFECTIVE_MEMBERS, prefix_rows


def verify(dsn, expected, upload):
    with connect(
        dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on -c statement_timeout=120000",
    ) as conn:
        actual = snapshot(conn)
        for key in ["tables", "rawCapturesVerified", "officialVersion"]:
            if actual[key] != expected[key]:
                raise ValueError("Restored checkpoint mismatch")
        member_hash = membership_hash(conn)
        migrations = {
            r["version"]: r["sha256"]
            for r in conn.execute(
                "SELECT version,sha256 FROM curated.official_migrations"
            )
        }
        entity = conn.execute(
            "SELECT r.entity_id FROM curated.official_records r JOIN curated.official_members m USING(capture_id) JOIN curated.official_pointer p USING(version) WHERE r.record->>'kind'='address_observation' LIMIT 1"
        ).fetchone()
    reader = OfficialReader(
        Reader(dsn, b"restore-verification-only-secret-at-least-32")
    )
    if entity:
        reader.get(entity["entity_id"])
        reader.address_history(entity["entity_id"])
    samples = []
    # Fixed internal qualification queries, not a public arbitrary-SQL surface.
    membership = "WITH members AS (" + EFFECTIVE_MEMBERS + ") "
    with connect(
        dsn,
        row_factory=dict_row,
        options="-c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250",
    ) as conn:
        for i in range(25):
            key = search_key(["10", "香港", "CHINA", "香港", "10"][i % 5])
            start = time.monotonic()
            rows = conn.execute(
                prefix_rows(EFFECTIVE_MEMBERS),
                (
                    key,
                    prefix_end(key),
                    key,
                    prefix_end(key),
                    "",
                    21,
                    key,
                    prefix_end(key),
                    key,
                    prefix_end(key),
                ),
            ).fetchall()
            samples.append((time.monotonic() - start) * 1000)
            if i % 5 == 0:
                started_id = time.monotonic()
                conn.execute(
                    membership
                    + "SELECT r.record FROM curated.official_records r JOIN members m USING(capture_id) WHERE r.entity_id=%s LIMIT 21",
                    ("cr:local:05243897",),
                ).fetchall()
                samples.append((time.monotonic() - started_id) * 1000)
            if rows:
                start = time.monotonic()
                conn.execute(
                    membership
                    + "SELECT r.record FROM curated.official_records r JOIN members m USING(capture_id) WHERE r.entity_id=%s ORDER BY r.record->>'coverageEnd' DESC NULLS LAST,r.fact_id LIMIT 101",
                    (rows[0]["entity_id"],),
                ).fetchall()
                samples.append((time.monotonic() - start) * 1000)
                start = time.monotonic()
                conn.execute(
                    prefix_rows(EFFECTIVE_MEMBERS),
                    (
                        key,
                        prefix_end(key),
                        key,
                        prefix_end(key),
                        rows[-1]["entity_id"],
                        21,
                        key,
                        prefix_end(key),
                        key,
                        prefix_end(key),
                    ),
                ).fetchall()
            samples.append((time.monotonic() - start) * 1000)
        pairs = conn.execute(
            "SELECT count(*) AS n FROM (SELECT i.week FROM curated.official_inventory i LEFT JOIN curated.official_staged s USING(source_key) LEFT JOIN curated.official_pointer p ON true LEFT JOIN curated.official_members m ON m.version=p.version AND m.source_key=i.source_key WHERE i.present AND (s.capture_id IS NOT NULL OR m.capture_id IS NOT NULL) GROUP BY i.week HAVING count(*)=2) t"
        ).fetchone()["n"]
    p95 = sorted(samples)[max(0, int(len(samples) * 0.95) - 1)]
    if p95 >= 1000:
        raise ValueError("Staged read latency exceeds qualified target")
    return {
        "freshOffsiteRestoreVerified": True,
        "backupSha256": upload["artifacts"]["official.dump"]["sha256"],
        "prefix": upload["prefix"],
        "allTableFingerprintsMatch": True,
        "rawCaptureChecksumsVerified": actual["rawCapturesVerified"],
        "officialVersion": actual["officialVersion"],
        "readOnlyRestoredQueries": True,
        "stagedReadP95Ms": p95,
        "stagedReadMaxMs": max(samples),
        "qualifiedWeekPairs": pairs,
        "performancePassed": True,
        "effectiveMembershipSha256": member_hash,
        "readQuerySha256": hashlib.sha256(
            Path(sys.modules[prefix_rows.__module__].__file__).read_bytes()
        ).hexdigest(),
        "migrations": migrations,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    if (
        not args.database.startswith("official_maintenance_restore_")
        or len(args.database) != 61
    ):
        parser.error("Use the owning restore database")
    dsn = make_conninfo(
        **dict(conninfo_to_dict(os.environ["CURATED_DSN"]), dbname=args.database)
    )
    try:
        proof = verify(dsn, json.load(open(args.source)), json.load(open(args.receipt)))
        print(json.dumps(proof))
    except Exception:
        print(
            json.dumps(
                {
                    "freshOffsiteRestoreVerified": False,
                    "errorCode": "RESTORE_OR_PERFORMANCE_VERIFICATION_FAILED",
                }
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
