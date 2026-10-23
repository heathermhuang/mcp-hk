"""Validation and independently restored backup gates for local publication."""

import hashlib
import json

from .build import connect
from .schema import TABLES, schema_name


def fingerprint(manifest):
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def inspect(dsn, version):
    from psycopg import sql
    from psycopg.rows import dict_row

    with connect(dsn, row_factory=dict_row) as conn:
        release = conn.execute(
            "SELECT * FROM curated.dataset_versions WHERE version=%s", (version,)
        ).fetchone()
        if release is None:
            raise ValueError("Candidate version does not exist")
        schema = schema_name(version)
        if release["schema_name"] != schema:
            raise ValueError("Candidate schema identity differs")
        conn.execute(
            sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(
                sql.Identifier(schema)
            )
        )
        counts, samples = {}, {}
        for table in TABLES:
            counts[table] = conn.execute(
                sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))
            ).fetchone()["n"]
            sample_keys = {
                "entity_identifiers": ["entity_id", "namespace", "value"],
                "source_references": ["family", "code"],
            }.get(table, [TABLES[table][0]])
            rows = conn.execute(
                sql.SQL("SELECT * FROM {} ORDER BY {} LIMIT 30").format(
                    sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, sample_keys)),
                )
            ).fetchall()
            samples[table] = hashlib.sha256(
                json.dumps(
                    rows, sort_keys=True, default=str, ensure_ascii=False
                ).encode()
            ).hexdigest()
            if counts[table] != release["manifest"]["counts"].get(table):
                raise ValueError(f"Candidate count differs: {table}")
        missing = {}
        for table, field, family in [
            ("entities", "domicile", "domiciles"),
            ("entities", "org_type", "orgtypes"),
            ("officer_appointments", "role_id", "positions"),
            ("licences", "activity_id", "activity"),
            ("licence_relationships", "activity_id", "activity"),
        ]:
            query = sql.SQL(
                "SELECT count(*) AS n FROM {} t LEFT JOIN source_references r ON r.family=%s AND r.code=t.{} WHERE t.{} IS NOT NULL AND r.code IS NULL"
            ).format(
                sql.Identifier(table), sql.Identifier(field), sql.Identifier(field)
            )
            missing[f"{table}.{field}"] = conn.execute(query, (family,)).fetchone()["n"]
        if any(missing.values()):
            raise ValueError(f"Unresolved source dictionaries: {missing}")
        temporal = {}
        for table in ("officer_appointments", "licences", "licence_relationships"):
            temporal[table] = conn.execute(
                sql.SQL(
                    "SELECT count(*) FILTER(WHERE start_precision <> 'day' OR end_precision <> 'day') AS uncertain_bounds, count(*) FILTER(WHERE start_date>end_date) AS reversed_bounds, count(*) FILTER(WHERE start_precision='invalid' OR end_precision='invalid') AS invalid_dates FROM {}"
                ).format(sql.Identifier(table))
            ).fetchone()
        validation = conn.execute(
            "SELECT count(*) AS n FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname=%s AND NOT convalidated",
            (schema,),
        ).fetchone()["n"]
        if validation:
            raise ValueError("Unvalidated read-model constraints")
        size = conn.execute(
            "SELECT sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename)))::bigint AS bytes FROM pg_tables WHERE schemaname=%s",
            (schema,),
        ).fetchone()["bytes"]
        identity = conn.execute(
            "SELECT system_identifier::text AS cluster, current_database() AS database FROM pg_control_system()"
        ).fetchone()
        return {
            "databaseIdentity": identity,
            "version": version,
            "manifestSha256": fingerprint(release["manifest"]),
            "counts": counts,
            "sampleHashes": samples,
            "unresolvedReferences": missing,
            "temporal": temporal,
            "databaseBytes": size,
            "validatedConstraints": True,
        }


def accept_restore(dsn, restore_dsn, version, backup_sha256):
    if dsn == restore_dsn:
        raise ValueError("Restore verification must use an independent database")
    if len(backup_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in backup_sha256
    ):
        raise ValueError("An immutable backup SHA-256 is required")
    original = inspect(dsn, version)
    restored = inspect(restore_dsn, version)
    proof = compare_restore(original, restored, backup_sha256)
    record_validation(dsn, version, proof)
    return proof


def compare_restore(original, restored, backup_sha256):
    if original["databaseIdentity"] == restored["databaseIdentity"]:
        raise ValueError("Restore verification must use an independent database")
    if len(backup_sha256) != 64 or any(
        c not in "0123456789abcdef" for c in backup_sha256
    ):
        raise ValueError("An immutable backup SHA-256 is required")
    for key in (
        "version",
        "manifestSha256",
        "counts",
        "sampleHashes",
        "unresolvedReferences",
        "temporal",
    ):
        if original[key] != restored[key]:
            raise ValueError(f"Restored candidate differs: {key}")
    return dict(
        restored,
        originalDatabaseIdentity=original["databaseIdentity"],
        backupSha256=backup_sha256,
        independentlyRestored=True,
    )


def record_validation(dsn, version, proof):
    with connect(dsn) as conn:
        conn.execute(
            "UPDATE curated.dataset_versions SET state='validated',validated_at=now(),restore_proof=%s::jsonb WHERE version=%s AND state='staging'",
            (json.dumps(proof), version),
        )


def accept_restore_receipt(restore_dsn, original_receipt, backup_path):
    """Disaster-recovery path when the original disposable database is offline.

    Operator evidence is aggregate-only. The artifact checksum and distinct
    database identity must match; this is not a remote attestation service.
    """
    from .backup import file_hash

    if file_hash(backup_path) != original_receipt["backupSha256"]:
        raise ValueError("Backup checksum differs from the retained original receipt")
    restored = inspect(restore_dsn, original_receipt["version"])
    proof = compare_restore(
        original_receipt, restored, original_receipt["backupSha256"]
    )
    record_validation(restore_dsn, original_receipt["version"], proof)
    return proof


def publish(dsn, version):
    from psycopg.rows import dict_row

    with connect(dsn, row_factory=dict_row) as conn:
        # Serialize all publishers, including the first release with no pointer.
        conn.execute("SELECT pg_advisory_xact_lock(7290483251)")
        row = conn.execute(
            "SELECT * FROM curated.dataset_versions WHERE version=%s FOR UPDATE",
            (version,),
        ).fetchone()
        if row is None or row["state"] not in {"validated", "published"}:
            raise ValueError(
                "Candidate must pass validation and independent restore before publication"
            )
        proof = row["restore_proof"]
        if (
            not proof
            or not proof.get("independentlyRestored")
            or proof["manifestSha256"] != fingerprint(row["manifest"])
        ):
            raise ValueError("Restore proof does not cover this candidate manifest")
        conn.execute(
            "UPDATE curated.dataset_versions SET state='published' WHERE version=%s",
            (version,),
        )
        conn.execute(
            "INSERT INTO curated.published_releases(pack,version) VALUES ('enigma_hk',%s) ON CONFLICT(pack) DO UPDATE SET version=excluded.version,published_at=now()",
            (version,),
        )


def grant_reader(dsn, role):
    """Role creation/password management belongs to the operator, not reader code."""
    from psycopg import sql
    from psycopg.rows import dict_row

    with connect(dsn, row_factory=dict_row) as conn:
        info = conn.execute(
            "SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=%s",
            (role,),
        ).fetchone()
        if info is None or any(info.values()):
            raise ValueError("Provision a dedicated unprivileged serving role first")
        schemas = ["curated"] + [
            r["schema_name"]
            for r in conn.execute(
                "SELECT schema_name FROM curated.dataset_versions"
            ).fetchall()
        ]
        for schema in schemas:
            conn.execute(
                sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
            conn.execute(
                sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA {} TO {}").format(
                    sql.Identifier(schema), sql.Identifier(role)
                )
            )
        conn.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(
                sql.Identifier(role)
            )
        )
