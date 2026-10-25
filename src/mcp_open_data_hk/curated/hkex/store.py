"""Source-only writer, atomic release pointer and complete logical restore proof."""

import contextlib
import hashlib
import os
import shutil
from datetime import datetime, timedelta, timezone
from importlib.resources import files

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..build import connect
from ..normalize import search_key
from .contracts import Policy, canonical, digest, revision_closure

TABLES = (
    "policies",
    "control",
    "runs",
    "requests",
    "captures",
    "versions",
    "issuers",
    "securities",
    "filings",
    "revisions",
    "interests",
    "particulars",
    "parties",
    "codes",
    "accepted",
)
LOCK = 0x484B45584449
COLLECT_LOCK = LOCK + 1


def migrate(dsn):
    with connect(dsn) as c:
        ddl = (
            files("mcp_open_data_hk.curated")
            .joinpath("migrations/004_hkex.sql")
            .read_text()
        )
        if c.execute("SELECT 1 FROM pg_namespace WHERE nspname='hkex'").fetchone():
            ddl = ddl.replace("CREATE SCHEMA IF NOT EXISTS hkex;", "")
        c.execute(ddl)


def grant_reader(dsn, role):
    with connect(dsn) as c:
        c.execute(
            sql.SQL("GRANT USAGE ON SCHEMA hkex TO {}").format(sql.Identifier(role))
        )
        # No raw bytes, request journal or private policy evidence in serving grants.
        for table in (
            "control",
            "capture_metadata",
            "versions",
            "accepted",
            "issuers",
            "securities",
            "filings",
            "revisions",
            "interests",
            "particulars",
            "parties",
            "codes",
        ):
            c.execute(
                sql.SQL("GRANT SELECT ON hkex.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(role)
                )
            )
        c.execute(
            sql.SQL("GRANT SELECT(hash,document) ON hkex.policies TO {}").format(
                sql.Identifier(role)
            )
        )


def current_policy(c, pinned=None, modes=()):
    row = c.execute(
        "SELECT p.hash,p.document FROM hkex.control x JOIN hkex.policies p ON p.hash=x.policy_hash WHERE x.singleton"
    ).fetchone()
    if not row or (pinned is not None and row["hash"] != pinned):
        raise ValueError("HKEX_SOURCE_UNQUALIFIED")
    policy = Policy.model_validate(row["document"])
    if digest(policy) != row["hash"]:
        raise ValueError("POLICY_CHECKSUM_MISMATCH")
    policy.require(*modes)
    return policy


def activate_policy(dsn, document, expected_sha256):
    policy = Policy.model_validate(document)
    if digest(policy) != expected_sha256:
        raise ValueError("POLICY_CHECKSUM_MISMATCH")
    with connect(dsn, row_factory=dict_row) as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        c.execute(
            "INSERT INTO hkex.policies(hash,document) VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (expected_sha256, Jsonb(policy.model_dump(mode="json"))),
        )
        c.execute(
            "UPDATE hkex.control SET policy_hash=%s WHERE singleton", (expected_sha256,)
        )
    return expected_sha256


class Store:
    def __init__(self, dsn, policy_hash):
        self.dsn, self.policy_hash = dsn, policy_hash

    @contextlib.contextmanager
    def connection(self, *modes):
        with connect(self.dsn, row_factory=dict_row) as c:
            policy = current_policy(c, self.policy_hash, modes)
            yield c, policy

    @contextlib.contextmanager
    def session(self):
        # A session lock spans durable request reservations and network calls.
        with connect(self.dsn, row_factory=dict_row, autocommit=True) as c:
            if not c.execute(
                "SELECT pg_try_advisory_lock(%s) AS locked", (COLLECT_LOCK,)
            ).fetchone()["locked"]:
                raise ValueError("HKEX_COLLECTOR_BUSY")
            try:
                yield
            finally:
                c.execute("SELECT pg_advisory_unlock(%s)", (COLLECT_LOCK,))

    def check_capacity(self):
        path = os.environ.get("HKEX_STORAGE_ROOT")
        if not path:
            raise ValueError("SOURCE_CAPACITY_UNQUALIFIED")
        with self.connection("collect", "retain") as (c, _):
            size = c.execute(
                "SELECT COALESCE(sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))),0) AS bytes FROM pg_tables WHERE schemaname='hkex'"
            ).fetchone()["bytes"]
            if size >= 1024**3 or shutil.disk_usage(path).free < 20 * 1024**3:
                raise ValueError("HKEX_GROWTH_RESERVE_REQUIRED")

    def stage(self, run_id, filings, captures, coverage):
        closure = revision_closure(filings)
        if closure["missing"] or not coverage["complete"]:
            raise ValueError("INCOMPLETE_WINDOW")
        version = (
            "hkex-"
            + digest(
                {
                    "coverage": coverage,
                    "filings": [x.model_dump(mode="json") for x in filings],
                    "captures": captures,
                }
            )[:32]
        )
        with self.connection("normalize", "retain", "history", "backup") as (c, policy):
            c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            # Lock the policy pointer through commit; activation cannot race admission.
            c.execute("SELECT * FROM hkex.control WHERE singleton FOR SHARE")
            current_policy(
                c, self.policy_hash, ("normalize", "retain", "history", "backup")
            )
            run = c.execute(
                "SELECT * FROM hkex.runs WHERE id=%s FOR UPDATE", (run_id,)
            ).fetchone()
            if (
                not run
                or run["policy_hash"] != self.policy_hash
                or run["state"] != "running"
            ):
                raise ValueError("RUN_NOT_ADMITTED")
            observed = c.execute(
                "SELECT min(observed_at) AS oldest FROM hkex.captures WHERE id=ANY(%s)",
                (list(captures.values()),),
            ).fetchone()["oldest"]
            # Republishing or resuming must not renew a source retention window.
            oldest = observed or run["started_at"]
            retained_until = min(
                oldest + timedelta(seconds=policy.retention_seconds), policy.expires_at
            )
            if retained_until <= datetime.now(timezone.utc):
                raise ValueError("SOURCE_RETENTION_EXPIRED")
            manifest = {
                "retainedUntil": retained_until.isoformat(),
                "source": "hkex_di",
                "policyHash": self.policy_hash,
                "coverage": coverage,
                "notice": "Dated disclosures; no inferred aggregate ownership or executed trades",
                "serials": sorted(x.serial for x in filings),
                "captureIds": sorted(captures.values()),
            }
            c.execute(
                "INSERT INTO hkex.versions(version,run_id,policy_hash,state,manifest) VALUES(%s,%s,%s,'staging',%s)",
                (version, run_id, self.policy_hash, Jsonb(manifest)),
            )
            from .contracts import Security

            issuer_contract = coverage["issuer"]
            issuers = {issuer_contract["id"]: issuer_contract["name"]}
            securities = {
                (issuer_contract["id"], s["source_id"]): Security.model_validate(s)
                for s in issuer_contract["securities"]
            }
            for row in filings:
                if (
                    row.issuer_id in issuers
                    and issuers[row.issuer_id] != row.issuer_name
                ):
                    raise ValueError("ISSUER_NAME_CONFLICT")
                issuers[row.issuer_id] = row.issuer_name
                for sec in row.securities:
                    key = row.issuer_id, sec.source_id
                    if key in securities and securities[key] != sec:
                        raise ValueError("SECURITY_IDENTITY_CONFLICT")
                    securities[key] = sec
            for issuer, name in issuers.items():
                c.execute(
                    "INSERT INTO hkex.issuers VALUES(%s,%s,%s,%s)",
                    (version, issuer, name, search_key(name)),
                )
            for (issuer, sid), sec in securities.items():
                c.execute(
                    "INSERT INTO hkex.securities VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        version,
                        issuer,
                        sid,
                        sec.stock_code,
                        sec.share_class,
                        sec.name,
                        Jsonb(sec.name_date.model_dump(mode="json")),
                    ),
                )
            for row in filings:
                capture = c.execute(
                    "SELECT x.* FROM hkex.captures x JOIN hkex.runs r ON r.id=x.run_id WHERE x.id=%s AND r.scope_window=(SELECT scope_window FROM hkex.runs WHERE id=%s) AND x.policy_hash=%s AND x.kind='detail' AND x.validation='validated'",
                    (captures[row.serial], run_id, self.policy_hash),
                ).fetchone()
                if not capture:
                    raise ValueError("MISSING_VALIDATED_CAPTURE")
                c.execute(
                    "INSERT INTO hkex.filings VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        version,
                        row.serial,
                        row.issuer_id,
                        capture["id"],
                        row.form,
                        row.channel,
                        row.state,
                        row.event_date.value,
                        row.filed_date.value,
                        row.published_date.value,
                        Jsonb(row.model_dump(mode="json")),
                    ),
                )
                for line in row.interests:
                    c.execute(
                        "INSERT INTO hkex.interests VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            version,
                            row.serial,
                            line.section,
                            line.line,
                            line.security_id,
                            line.capacity_code,
                            line.nature,
                            line.position,
                            line.phase,
                            line.instrument,
                            line.shares,
                            line.shares,
                            line.percentage,
                            line.percentage,
                            line.unit,
                            line.party_ref,
                        ),
                    )
                for line in row.particulars:
                    c.execute(
                        "INSERT INTO hkex.particulars VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (
                            version,
                            row.serial,
                            line.line,
                            line.reason_code,
                            line.shares,
                            line.shares,
                            line.price,
                            line.price,
                            line.currency,
                            line.unit,
                        ),
                    )
                for party in row.parties:
                    c.execute(
                        "INSERT INTO hkex.parties VALUES(%s,%s,%s,%s,%s,%s)",
                        (
                            version,
                            row.serial,
                            party.ref,
                            party.disclosed_name,
                            party.source_global_id,
                            party.association,
                        ),
                    )
            for older, newer in closure["edges"]:
                c.execute(
                    "INSERT INTO hkex.revisions VALUES(%s,%s,%s,true)",
                    (version, older, newer),
                )
            for family, codes in policy.codes.items():
                for code, label in codes.items():
                    c.execute(
                        "INSERT INTO hkex.codes VALUES(%s,%s,%s,%s,%s)",
                        (version, family, code, label, self.policy_hash),
                    )
            c.execute(
                "UPDATE hkex.versions SET state='validated' WHERE version=%s",
                (version,),
            )
            c.execute(
                "UPDATE hkex.runs SET state='validated',finished_at=now() WHERE id=%s",
                (run_id,),
            )
        return version

    def publish(self, version, expected_version):
        with self.connection("retain", "history", "backup") as (c, policy):
            c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            c.execute("SELECT * FROM hkex.control WHERE singleton FOR SHARE")
            current_policy(c, self.policy_hash, ("retain", "history", "backup"))
            row = c.execute(
                "SELECT * FROM hkex.versions WHERE version=%s FOR UPDATE", (version,)
            ).fetchone()
            old = c.execute(
                "SELECT version FROM hkex.accepted WHERE singleton"
            ).fetchone()
            if (old["version"] if old else None) != expected_version:
                raise ValueError("PUBLICATION_CONFLICT")
            if (
                not row
                or row["policy_hash"] != self.policy_hash
                or row["state"] not in {"restore-qualified", "published"}
                or not row["restore_proof"]
            ):
                raise ValueError("RESTORE_PROOF_REQUIRED")
            policy.require("retain", "history", "backup")
            if datetime.fromisoformat(row["manifest"]["retainedUntil"]) <= datetime.now(
                timezone.utc
            ):
                raise ValueError("SOURCE_RETENTION_EXPIRED")
            c.execute(
                "UPDATE hkex.versions SET state='published',published_at=COALESCE(published_at,now()) WHERE version=%s",
                (version,),
            )
            c.execute(
                "INSERT INTO hkex.accepted(singleton,version) VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET version=excluded.version,accepted_at=now()",
                (version,),
            )
        return version


@contextlib.contextmanager
def quiescent(dsn):
    """Coordinate source collection, policy activation and pointer mutation."""
    with connect(dsn, row_factory=dict_row, autocommit=True) as c:
        locks = []
        try:
            for lock in (COLLECT_LOCK, LOCK):
                if not c.execute(
                    "SELECT pg_try_advisory_lock(%s) AS locked", (lock,)
                ).fetchone()["locked"]:
                    raise ValueError("HKEX_SOURCE_BUSY")
                locks.append(lock)
            yield c
        finally:
            for lock in reversed(locks):
                c.execute("SELECT pg_advisory_unlock(%s)", (lock,))


def fingerprint(dsn):
    """All source tables, including bytes, policy, journals and accepted pointer.

    Stream individual records and sort only fixed-size leaf hashes. Raw capture
    history is never buffered wholesale by the verifier.
    """
    result = {}
    with connect(dsn, row_factory=dict_row) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL TIME ZONE 'UTC'")
        for table in TABLES:
            encoded = []
            with c.cursor(name="hkex_fingerprint") as cursor:
                cursor.itersize = 1
                cursor.execute(
                    sql.SQL("SELECT to_jsonb(t) AS row FROM hkex.{} t").format(
                        sql.Identifier(table)
                    )
                )
                for row in cursor:
                    encoded.append(hashlib.sha256(canonical(row["row"])).hexdigest())
            result[table] = {
                "rows": len(encoded),
                "sha256": hashlib.sha256(
                    "\n".join(sorted(encoded)).encode()
                ).hexdigest(),
            }
    return result


def accept_restore(dsn, restored_dsn, version, archive_sha256):
    if (
        not isinstance(archive_sha256, str)
        or len(archive_sha256) != 64
        or any(c not in "0123456789abcdef" for c in archive_sha256)
    ):
        raise ValueError("INVALID_ARCHIVE_SHA256")
    identities = []
    for target in (dsn, restored_dsn):
        with connect(target) as c:
            identities.append(
                c.execute(
                    "SELECT current_database(),inet_server_addr(),inet_server_port(),(SELECT oid FROM pg_database WHERE datname=current_database())"
                ).fetchone()
            )
    if identities[0] == identities[1]:
        raise ValueError("INDEPENDENT_RESTORE_REQUIRED")
    with quiescent(dsn):
        original, restored = fingerprint(dsn), fingerprint(restored_dsn)
        if original != restored:
            raise ValueError("RESTORE_CONTENT_MISMATCH")
        with connect(dsn, row_factory=dict_row) as c:
            row = c.execute(
                "SELECT * FROM hkex.versions WHERE version=%s", (version,)
            ).fetchone()
            if not row or row["state"] != "validated":
                raise ValueError("VALIDATED_VERSION_REQUIRED")
            current_policy(c, row["policy_hash"], ("backup", "retain"))
            proof = {
                "archiveSha256": archive_sha256,
                "tables": original,
                "verifiedAt": datetime.now(timezone.utc).isoformat(),
            }
            c.execute(
                "UPDATE hkex.versions SET state='restore-qualified',restore_proof=%s WHERE version=%s",
                (Jsonb(proof), version),
            )
        return proof
