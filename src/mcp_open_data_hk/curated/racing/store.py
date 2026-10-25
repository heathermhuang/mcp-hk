"""Source-isolated version storage, full-fact restore comparison and atomic publication."""

from pathlib import Path

from .db import connect
from .policy import RacingRejected, canonical, checksum, require, validate_policy

TABLES = (
    "captures",
    "meetings",
    "races",
    "participants",
    "runners",
    "results",
    "profile_observations",
    "sectionals",
    "dividends",
    "family_facts",
    "observations",
    "coverage",
)


def migrate(dsn):
    import hashlib

    source = (Path(__file__).parent.parent / "migrations/002_racing.sql").read_text()
    digest = hashlib.sha256(source.encode()).hexdigest()
    with connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7242525)")
        conn.execute("CREATE SCHEMA IF NOT EXISTS racing")
        conn.execute("REVOKE ALL ON SCHEMA racing FROM PUBLIC")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS racing.migrations(version text PRIMARY KEY, sha256 text NOT NULL)"
        )
        current = conn.execute(
            "SELECT sha256 FROM racing.migrations WHERE version='002'"
        ).fetchone()
        if current:
            if current["sha256"] != digest:
                raise RacingRejected("MIGRATION_SOURCE_CHANGED")
            return
        conn.execute(source)
        conn.execute(
            "INSERT INTO racing.migrations(version,sha256) VALUES('002',%s)", (digest,)
        )


def install_policy(dsn, record, *, activate=False):
    from psycopg.types.json import Jsonb

    validate_policy(record)
    digest = checksum(record)
    with connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7242525)")
        conn.execute(
            "INSERT INTO racing.policies(digest,record,active) VALUES(%s,%s,%s) ON CONFLICT(digest) DO NOTHING",
            (digest, Jsonb(record), activate),
        )
    return digest


def policy(conn, digest, family, mode, **kwargs):
    row = conn.execute(
        "SELECT record,active FROM racing.policies WHERE digest=%s", (digest,)
    ).fetchone()
    if row is None or not row["active"]:
        raise RacingRejected("SOURCE_POLICY_INACTIVE")
    return require(row["record"], digest, family, mode, **kwargs)


def revoke(dsn, digest):
    with connect(dsn) as conn:
        conn.execute(
            "UPDATE racing.policies SET active=false WHERE digest=%s", (digest,)
        )


def snapshot(conn, version, *, whole_source=False):
    """Hash every fact with an order independent canonical representation, not a sample."""
    from psycopg import sql

    import hashlib
    import uuid

    result = {}
    selected_tables = TABLES + (
        (
            "migrations",
            "policies",
            "versions",
            "accepted",
            "jobs",
            "budgets",
            "requests",
            "source_state",
            "capture_buffer",
        )
        if whole_source
        else ()
    )
    for table in selected_tables:
        digest = hashlib.sha256()
        count = 0
        with conn.cursor(name="racing_hash_" + uuid.uuid4().hex) as cursor:
            predicate = "" if whole_source else " WHERE version=%s"
            cursor.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) AS row FROM racing.{} t"
                    + predicate
                    + ' ORDER BY to_jsonb(t)::text COLLATE "C"'
                ).format(sql.Identifier(table)),
                () if whole_source else (version,),
            )
            for row in cursor:
                value = canonical(row["row"])
                digest.update(len(value).to_bytes(8, "big"))
                digest.update(value)
                count += 1
        result[table] = {"rows": count, "sha256": digest.hexdigest()}
    return result


def stage(dsn, version, digest, manifest, tables):
    """Import a validated offline bundle. Live provider parsers remain independently gated."""
    from psycopg import sql
    from psycopg.types.json import Jsonb
    from .normalize import exact

    from .validate import validate_bundle

    exact(version)
    validate_bundle(manifest, tables)
    if set(tables) - set(TABLES) or not manifest.get("families"):
        raise RacingRejected("INVALID_BUNDLE")
    if not manifest.get("inventoryRef") or not manifest.get("transformSha256"):
        raise RacingRejected("INDEPENDENT_INVENTORY_REQUIRED")
    if not tables.get("coverage") or any(
        not row["complete"]
        or sorted(row["expected_ids"]) != sorted(row["observed_ids"])
        for row in tables["coverage"]
    ):
        raise RacingRejected("INCOMPLETE_BUNDLE")
    with connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7242525)")
        for family in manifest["families"]:
            policy(conn, digest, family, "cache")
            if manifest.get("historical"):
                policy(conn, digest, family, "history")
        conn.execute(
            "INSERT INTO racing.versions(version,state,policy_digest,manifest) VALUES(%s,'staging',%s,%s)",
            (version, digest, Jsonb(manifest)),
        )
        for capture in tables.get("captures", []):
            if capture["policy_digest"] != digest:
                raise RacingRejected("CAPTURE_POLICY_MISMATCH")
            policy(
                conn,
                digest,
                capture["family"],
                "cache",
                route=capture["canonical_location"],
            )
        for result in tables.get("results", []):
            if result.get("supersedes"):
                previous = conn.execute(
                    "SELECT 1 FROM racing.results WHERE fact_id=%s AND revision=%s",
                    (result["fact_id"], result["supersedes"]),
                ).fetchone()
                if not previous or result["revision"] == result["supersedes"]:
                    raise RacingRejected("REVISION_CHAIN_REJECTED")
        for table in TABLES:
            for row in tables.get(table, []):
                if "version" in row:
                    raise RacingRejected("CALLER_VERSION_REJECTED")
                columns = ["version", *row]
                values = [
                    version,
                    *(Jsonb(v) if isinstance(v, dict) else v for v in row.values()),
                ]
                # Identifiers are quoted and table names come from the closed TABLES tuple.
                conn.execute(
                    sql.SQL("INSERT INTO racing.{} ({}) VALUES ({})").format(
                        sql.Identifier(table),
                        sql.SQL(",").join(map(sql.Identifier, columns)),
                        sql.SQL(",").join(sql.Placeholder() for _ in columns),
                    ),
                    values,
                )
        # Every declared race/runner must be represented, independently of row counts.
        missing = conn.execute(
            "SELECT 1 FROM racing.runners r WHERE r.version=%s AND NOT EXISTS(SELECT 1 FROM racing.results f WHERE f.version=r.version AND f.race_id=r.race_id AND f.participant_id=r.participant_id) LIMIT 1",
            (version,),
        ).fetchone()
        if missing:
            raise RacingRejected("DECLARED_RUNNER_GAP")
        for family in manifest["families"]:
            policy(conn, digest, family, "cache")
        conn.execute(
            "UPDATE racing.versions SET state='validated' WHERE version=%s", (version,)
        )
        return snapshot(conn, version)


def identity(conn):
    return conn.execute(
        "SELECT system_identifier::text AS cluster, current_database() AS database FROM pg_control_system()"
    ).fetchone()


def qualify_restore(dsn, restored_dsn, version, backup_sha256):
    from psycopg.types.json import Jsonb
    from .normalize import exact

    exact(backup_sha256, r"[a-f0-9]{64}")
    with connect(dsn) as source, connect(restored_dsn) as restored:
        if identity(source) == identity(restored):
            raise RacingRejected("INDEPENDENT_RESTORE_REQUIRED")
        source.execute("SELECT pg_advisory_xact_lock(7242525)")
        source.execute("SELECT pg_advisory_xact_lock(7242526)")
        left, right = snapshot(source, version), snapshot(restored, version)
        source_tables, restored_tables = snapshot(
            source, version, whole_source=True
        ), snapshot(restored, version, whole_source=True)
        if source_tables != restored_tables:
            raise RacingRejected("RESTORE_SOURCE_STATE_MISMATCH")
        metadata = source.execute(
            "SELECT policy_digest,manifest FROM racing.versions WHERE version=%s",
            (version,),
        ).fetchone()
        other = restored.execute(
            "SELECT policy_digest,manifest FROM racing.versions WHERE version=%s",
            (version,),
        ).fetchone()
        if left != right or metadata is None or metadata != other:
            raise RacingRejected("RESTORE_FACT_MISMATCH")
        left_policy = source.execute(
            "SELECT record FROM racing.policies WHERE digest=%s",
            (metadata["policy_digest"],),
        ).fetchone()
        right_policy = restored.execute(
            "SELECT record FROM racing.policies WHERE digest=%s",
            (metadata["policy_digest"],),
        ).fetchone()
        if left_policy != right_policy:
            raise RacingRejected("RESTORE_POLICY_MISMATCH")
        proof = {
            "backupSha256": backup_sha256,
            "tables": left,
            "sourceTables": source_tables,
            "restoredIdentity": identity(restored),
            "scope": "full_source_version",
        }
        source.execute(
            "UPDATE racing.versions SET state='restore-qualified',restore_proof=%s WHERE version=%s AND state='validated'",
            (Jsonb(proof), version),
        )
        return proof


def publish(dsn, version, *, expected, modes=("rest", "mcp", "browser")):
    if not modes or set(modes) - {"rest", "mcp", "browser", "export"}:
        raise RacingRejected("PUBLICATION_MODES_REJECTED")
    with connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7242525)")
        row = conn.execute(
            "SELECT * FROM racing.versions WHERE version=%s AND state IN ('restore-qualified','published')",
            (version,),
        ).fetchone()
        if row is None or not row["restore_proof"]:
            raise RacingRejected("RESTORE_REQUIRED")
        for family in row["manifest"]["families"]:
            for mode in modes:
                policy(conn, row["policy_digest"], family, mode)
        current = conn.execute(
            "SELECT version FROM racing.accepted WHERE pack='hkjc_racing' FOR UPDATE"
        ).fetchone()
        if (current["version"] if current else None) != expected:
            raise RacingRejected("PUBLICATION_CONFLICT")
        conn.execute(
            "UPDATE racing.versions SET state='published' WHERE version=%s", (version,)
        )
        conn.execute(
            "INSERT INTO racing.accepted(pack,version) VALUES('hkjc_racing',%s) ON CONFLICT(pack) DO UPDATE SET version=excluded.version,published_at=now()",
            (version,),
        )
