"""Recoverable state fingerprints and raw checksums, independent of publication."""

import argparse
import json
import os

from psycopg import sql
from psycopg.rows import dict_row

from .build import connect
from .official import digest
from .official_state import pointer, transform_hash


def snapshot(conn):
    tables = conn.execute(
        "SELECT tablename FROM pg_tables WHERE schemaname='curated' ORDER BY tablename"
    ).fetchall()
    fingerprints = {}
    for row in tables:
        query = sql.SQL(
            "SELECT count(*) AS rows,md5(coalesce(string_agg(md5(row_to_json(t)::text),'' ORDER BY md5(row_to_json(t)::text)),'')) AS fingerprint FROM curated.{} t"
        ).format(sql.Identifier(row["tablename"]))
        fingerprints[row["tablename"]] = conn.execute(query).fetchone()
    checked = 0
    # A server cursor prevents the enlarged raw-byte inventory being buffered by
    # libpq. Each source object remains bounded independently of backlog size.
    with conn.transaction():
        with conn.cursor(name="official_recovery_raw") as captures:
            captures.itersize = 1
            captures.execute(
                "SELECT sha256,body,verification_body,receipt FROM curated.official_captures"
            )
            for capture in captures:
                if digest(bytes(capture["body"])) != capture["sha256"]:
                    raise ValueError("Raw capture checksum mismatch")
                if (
                    capture["receipt"].get("verificationSha256")
                    and digest(bytes(capture["verification_body"]))
                    != capture["receipt"]["verificationSha256"]
                ):
                    raise ValueError("Verification capture checksum mismatch")
                checked += 1
    return {
        "tables": fingerprints,
        "rawCapturesVerified": checked,
        "officialVersion": pointer(conn),
        "currentTransformSha256": transform_hash(),
    }


def membership_hash(conn):
    from .official_queries import EFFECTIVE_MEMBERS
    from .official import encoded

    rows = conn.execute(
        "WITH members AS ("
        + EFFECTIVE_MEMBERS
        + ") SELECT source_key,capture_id FROM members ORDER BY source_key"
    ).fetchall()
    return digest(encoded(rows))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    with connect(os.environ["CURATED_DSN"], row_factory=dict_row) as conn:
        receipt = snapshot(conn)
    print(json.dumps(dict(receipt, sourceCommit=args.commit), default=str))


if __name__ == "__main__":
    main()
