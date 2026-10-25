"""Source-scoped operator state. Reservations commit before external work.

No live transport is provided. All callers own an isolated SFC writer DSN; every
mutation opens its own bounded transaction and rechecks the current pinned policy.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from importlib.resources import files
import uuid

from ..build import connect
from ..security import safe_reader_role
from .contracts import Rejected, ce_reference, digest, encoded, parse_normalized
from .policy import Policy

LOCK = 68002503
TABLES = (
    "migrations",
    "policies",
    "runs",
    "budgets",
    "holds",
    "attempts",
    "versions",
    "captures",
    "corporations",
    "pointer",
)


class State:
    def __init__(self, dsn):
        self.dsn = dsn

    def connection(self):
        from psycopg.rows import dict_row

        return connect(
            self.dsn,
            autocommit=True,
            row_factory=dict_row,
            options="-c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
        )

    def migrate(self):
        ddl = (
            files("mcp_open_data_hk.curated")
            .joinpath("migrations/003_sfc.sql")
            .read_text()
        )
        sha = digest(ddl.encode())
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            exists = conn.execute(
                "SELECT to_regclass('curated_sfc.migrations') AS name"
            ).fetchone()["name"]
            if exists:
                row = conn.execute(
                    "SELECT sha256 FROM curated_sfc.migrations WHERE version='003'"
                ).fetchone()
                if not row or row["sha256"] != sha:
                    raise Rejected("SFC_MIGRATION_CHANGED")
                return sha
            conn.execute(ddl)
            conn.execute("INSERT INTO curated_sfc.migrations VALUES('003',%s)", (sha,))
        return sha

    def activate(self, policy, expected_sha256):
        # Operator action only; there is no HTTP/MCP/configuration activation route.
        if policy.sha256 != expected_sha256:
            raise Rejected("SFC_POLICY_CHECKSUM")
        policy.require("automation", "retention", "backup")
        from psycopg.types.json import Jsonb

        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            if conn.execute(
                "SELECT 1 FROM curated_sfc.policies WHERE sha256=%s", (expected_sha256,)
            ).fetchone():
                raise Rejected("SFC_POLICY_ALREADY_RECORDED")
            conn.execute(
                "UPDATE curated_sfc.policies SET active=false,revoked_at=now() WHERE active"
            )
            conn.execute(
                "INSERT INTO curated_sfc.policies(sha256,record,active,activated_at) VALUES(%s,%s,true,now())",
                (expected_sha256, Jsonb(policy.model_dump(mode="json"))),
            )

    def revoke(self, expected_sha256):
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            row = conn.execute(
                "UPDATE curated_sfc.policies SET active=false,revoked_at=now() WHERE active AND sha256=%s RETURNING sha256",
                (expected_sha256,),
            ).fetchone()
            if not row:
                raise Rejected("SFC_POLICY_CHANGED")

    @staticmethod
    def policy(conn, expected_sha256, *modes):
        row = conn.execute(
            "SELECT record FROM curated_sfc.policies WHERE sha256=%s AND active AND revoked_at IS NULL FOR SHARE",
            (expected_sha256,),
        ).fetchone()
        if not row:
            raise Rejected("SFC_POLICY_CHANGED")
        policy = Policy.model_validate(row["record"])
        if policy.sha256 != expected_sha256:
            raise Rejected("SFC_POLICY_CHECKSUM")
        policy.require(
            *modes, now=conn.execute("SELECT clock_timestamp() AS at").fetchone()["at"]
        )
        return policy

    @contextmanager
    def session(self):
        # Session advisory lock, released by connection death, spans source I/O.
        with self.connection() as conn:
            if not conn.execute(
                "SELECT pg_try_advisory_lock(%s) AS held", (LOCK + 1,)
            ).fetchone()["held"]:
                raise Rejected("SFC_SESSION_BUSY")
            try:
                yield self
            finally:
                conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK + 1,))

    def start(self, scheduled_for, cohort, policy_sha256):
        cohort = [ce_reference(ce) for ce in cohort]
        if not 1 <= len(cohort) <= 25 or len(set(cohort)) != len(cohort):
            raise Rejected("SFC_INVALID_COHORT")
        if scheduled_for.tzinfo is None or scheduled_for.utcoffset() is None:
            raise Rejected("SFC_INVALID_OCCURRENCE")
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            policy = self.policy(conn, policy_sha256, "automation")
            if not set(cohort) <= set(policy.trackedCorporateReferences):
                raise Rejected("SFC_COHORT_UNQUALIFIED")
            existing = conn.execute(
                "SELECT * FROM curated_sfc.runs WHERE scheduled_for=%s",
                (scheduled_for,),
            ).fetchone()
            if existing:
                if (
                    existing["cohort"] != sorted(cohort)
                    or existing["policy_sha256"] != policy_sha256
                ):
                    raise Rejected("SFC_OCCURRENCE_CONFLICT")
                return existing["run_id"], False
            if conn.execute(
                "SELECT 1 FROM curated_sfc.runs WHERE state='running'"
            ).fetchone():
                raise Rejected("SFC_UNSETTLED_RUN")
            run_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO curated_sfc.runs(run_id,scheduled_for,policy_sha256,cohort,state) VALUES(%s,%s,%s,%s,'running')",
                (run_id, scheduled_for, policy_sha256, sorted(cohort)),
            )
            return run_id, True

    def reserve(self, run_id, ce, kind, max_bytes=262144):
        ce = ce_reference(ce)
        if (
            kind not in {"session", "detail", "retry"}
            or type(max_bytes) is not int
            or not 1 <= max_bytes <= 8388608
        ):
            raise Rejected("SFC_INVALID_RESERVATION")
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            run = conn.execute(
                "SELECT * FROM curated_sfc.runs WHERE run_id=%s FOR UPDATE", (run_id,)
            ).fetchone()
            if not run or run["state"] != "running" or ce not in run["cohort"]:
                raise Rejected("SFC_RUN_UNAVAILABLE")
            policy = self.policy(conn, run["policy_sha256"], "automation")
            now = conn.execute("SELECT clock_timestamp() AS at").fetchone()["at"]
            if now - run["started_at"] > timedelta(minutes=10):
                raise Rejected("SFC_RUN_TIMEOUT")
            if conn.execute(
                "SELECT 1 FROM curated_sfc.holds WHERE until_at>%s", (now,)
            ).fetchone():
                raise Rejected("SFC_SOURCE_HOLD")
            # A crash/uncertain response cannot be retried for free or ignored.
            if conn.execute(
                "SELECT 1 FROM curated_sfc.attempts WHERE state='unknown'"
            ).fetchone():
                raise Rejected("SFC_UNCERTAIN_REQUEST")
            if (
                run["requests"] >= policy.readsPerRun
                or run["reserved_bytes"] + max_bytes > policy.bytesPerRun
            ):
                raise Rejected("SFC_RUN_BUDGET")
            budget = conn.execute(
                "INSERT INTO curated_sfc.budgets(day,requests,bytes) VALUES(%s,1,%s) ON CONFLICT(day) DO UPDATE SET requests=budgets.requests+1,bytes=budgets.bytes+EXCLUDED.bytes WHERE budgets.requests<%s AND budgets.bytes+EXCLUDED.bytes<=%s RETURNING requests",
                (
                    now.astimezone(timezone.utc).date(),
                    max_bytes,
                    policy.readsPerDay,
                    policy.bytesPerDay,
                ),
            ).fetchone()
            if not budget:
                raise Rejected("SFC_DAY_BUDGET")
            conn.execute(
                "UPDATE curated_sfc.runs SET requests=requests+1,reserved_bytes=reserved_bytes+%s WHERE run_id=%s",
                (max_bytes, run_id),
            )
            return conn.execute(
                "INSERT INTO curated_sfc.attempts(run_id,ce,kind,reserved_bytes,state) VALUES(%s,%s,%s,%s,'unknown') RETURNING attempt_id",
                (run_id, ce, kind, max_bytes),
            ).fetchone()["attempt_id"]

    def settle(self, attempt_id, outcome, *, hold_until=None):
        if outcome not in {"ok", "not_modified", "missing", "rejected", "failed"}:
            raise Rejected("SFC_INVALID_OUTCOME")
        if hold_until and (hold_until.tzinfo is None or hold_until.utcoffset() is None):
            raise Rejected("SFC_INVALID_HOLD")
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            row = conn.execute(
                "UPDATE curated_sfc.attempts SET state=%s,settled_at=now() WHERE attempt_id=%s AND state='unknown' RETURNING attempt_id",
                (outcome, attempt_id),
            ).fetchone()
            if not row:
                raise Rejected("SFC_ATTEMPT_SETTLED")
            if hold_until:
                conn.execute(
                    "INSERT INTO curated_sfc.holds(singleton,until_at,reason) VALUES(true,%s,'rate_limited') ON CONFLICT(singleton) DO UPDATE SET until_at=GREATEST(holds.until_at,EXCLUDED.until_at),reason=EXCLUDED.reason",
                    (hold_until,),
                )

    def finish(self, run_id, state="partial"):
        if state not in {"partial", "failed"}:
            raise Rejected("SFC_INVALID_OUTCOME")
        with self.connection() as conn:
            conn.execute(
                "UPDATE curated_sfc.runs SET state=%s WHERE run_id=%s AND state='running'",
                (state, run_id),
            )

    def stage(self, run_id, payloads):
        """payloads: CE -> (normalised bytes, settled attempt ID). No raw retained.

        This is the offline normalised-input boundary, not an official-page parser.
        It deliberately cannot accept partial cohorts or infer missing statuses.
        """
        from psycopg.types.json import Jsonb

        parsed = {
            ce_reference(ce): (
                parse_normalized(raw, ce),
                digest(raw),
                attempt,
                len(raw),
            )
            for ce, (raw, attempt) in payloads.items()
        }
        if len(parsed) != len(payloads):
            raise Rejected("SFC_DUPLICATE_CE")
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            run = conn.execute(
                "SELECT * FROM curated_sfc.runs WHERE run_id=%s FOR UPDATE", (run_id,)
            ).fetchone()
            if (
                not run
                or run["state"] != "running"
                or set(run["cohort"]) != set(parsed)
            ):
                raise Rejected("SFC_INCOMPLETE_COHORT")
            policy = self.policy(
                conn, run["policy_sha256"], "automation", "retention", "backup"
            )
            if conn.execute(
                "SELECT 1 FROM curated_sfc.attempts WHERE run_id=%s AND state='unknown'",
                (run_id,),
            ).fetchone():
                raise Rejected("SFC_UNCERTAIN_REQUEST")
            facts = [
                record.model_dump(mode="json")
                for ce, (record, _, _, _) in sorted(parsed.items())
            ]
            sha = digest(encoded(facts))
            version = "sfc-" + uuid.uuid4().hex
            transform = digest(files(__package__).joinpath("contracts.py").read_bytes())
            expires = min(
                r.observedAt + timedelta(seconds=policy.retentionSeconds)
                for r, _, _, _ in parsed.values()
            )
            manifest = {
                "sourceId": "sfc_register",
                "cohort": sorted(parsed),
                "scope": "tracked_corporate_subset",
                "policySha256": policy.sha256,
                "transformSha256": transform,
                "format": "normalised-offline-v1",
                "completeRegulatoryHistory": False,
            }
            conn.execute(
                "INSERT INTO curated_sfc.versions(version,run_id,policy_sha256,manifest,facts_sha256,expires_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (version, run_id, policy.sha256, Jsonb(manifest), sha, expires),
            )
            for ce, (record, payload_sha, attempt, payload_size) in parsed.items():
                accepted = conn.execute(
                    "SELECT reserved_bytes FROM curated_sfc.attempts WHERE attempt_id=%s AND run_id=%s AND ce=%s AND state='ok' AND kind IN ('detail','retry')",
                    (attempt, run_id, ce),
                ).fetchone()
                if not accepted:
                    raise Rejected("SFC_CAPTURE_ATTEMPT_MISMATCH")
                if payload_size > accepted["reserved_bytes"]:
                    raise Rejected("SFC_RESERVED_BYTES_EXCEEDED")
                now = conn.execute("SELECT clock_timestamp() AS at").fetchone()["at"]
                if not run["started_at"] <= record.observedAt <= now or expires <= now:
                    raise Rejected("SFC_OBSERVATION_TIME")
                capture = digest(
                    encoded(
                        [
                            version,
                            ce,
                            payload_sha,
                            transform,
                            record.observedAt.isoformat(),
                        ]
                    )
                )
                conn.execute(
                    "INSERT INTO curated_sfc.captures VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        capture,
                        version,
                        ce,
                        attempt,
                        policy.route,
                        record.observedAt,
                        payload_sha,
                        transform,
                    ),
                )
                conn.execute(
                    "INSERT INTO curated_sfc.corporations VALUES(%s,%s,%s,%s)",
                    (version, ce, capture, Jsonb(record.model_dump(mode="json"))),
                )
            conn.execute(
                "UPDATE curated_sfc.runs SET state='validated' WHERE run_id=%s",
                (run_id,),
            )
            return version, sha

    def facts(self, version):
        with self.connection() as conn:
            return [
                row["fact"]
                for row in conn.execute(
                    "SELECT fact FROM curated_sfc.corporations WHERE version=%s ORDER BY ce",
                    (version,),
                )
            ]

    def qualify_restore(self, version, restored, artifact, artifact_sha256):
        # Operator must supply the actual retrieved backup, not an asserted hash.
        from pathlib import Path
        from ..backup import file_hash

        artifact = Path(artifact)
        if artifact.is_symlink() or file_hash(artifact) != artifact_sha256:
            raise Rejected("SFC_RESTORE_ARTIFACT_DIFFERS")
        # Compare every fact and every control/capture row in independent DBs.
        with self.connection() as source, restored.connection() as target:
            a = source.execute(
                "SELECT system_identifier::text AS cluster,current_database() AS db FROM pg_control_system()"
            ).fetchone()
            b = target.execute(
                "SELECT system_identifier::text AS cluster,current_database() AS db FROM pg_control_system()"
            ).fetchone()
            if (
                a == b
                or len(artifact_sha256) != 64
                or any(c not in "0123456789abcdef" for c in artifact_sha256)
            ):
                raise Rejected("SFC_RESTORE_NOT_INDEPENDENT")
            expected = self.snapshot(source)
            if expected != self.snapshot(target):
                raise Rejected("SFC_RESTORE_DIFFERS")
            row = source.execute(
                "SELECT facts_sha256 FROM curated_sfc.versions WHERE version=%s",
                (version,),
            ).fetchone()
            if not row or digest(encoded(self.facts(version))) != row["facts_sha256"]:
                raise Rejected("SFC_FACT_HASH_DIFFERS")
            from psycopg.types.json import Jsonb

            proof = {
                "artifactSha256": artifact_sha256,
                "factsSha256": row["facts_sha256"],
                "allSourceTablesSha256": digest(encoded(expected)),
                "independentDatabase": True,
            }
            source.execute(
                "UPDATE curated_sfc.versions SET restore_proof=%s WHERE version=%s",
                (Jsonb(proof), version),
            )
            return proof

    @staticmethod
    def snapshot(conn):
        from psycopg import sql

        return {
            table: conn.execute(
                sql.SQL(
                    "SELECT to_jsonb(t) AS row FROM curated_sfc.{} t ORDER BY to_jsonb(t)::text"
                ).format(sql.Identifier(table))
            ).fetchall()
            for table in TABLES
        }

    def publish(self, version, expected_old):
        with self.connection() as conn, conn.transaction():
            conn.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
            row = conn.execute(
                "SELECT * FROM curated_sfc.versions WHERE version=%s FOR UPDATE",
                (version,),
            ).fetchone()
            if not row:
                raise Rejected("SFC_VERSION_UNAVAILABLE")
            self.policy(conn, row["policy_sha256"], "retention", "backup")
            proof = row["restore_proof"] or {}
            if (
                not proof.get("independentDatabase")
                or proof.get("factsSha256") != row["facts_sha256"]
                or row["expires_at"] <= datetime.now(timezone.utc)
                or digest(
                    encoded(
                        [
                            r["fact"]
                            for r in conn.execute(
                                "SELECT fact FROM curated_sfc.corporations WHERE version=%s ORDER BY ce",
                                (version,),
                            )
                        ]
                    )
                )
                != row["facts_sha256"]
            ):
                raise Rejected("SFC_RESTORE_REQUIRED")
            actual = conn.execute("SELECT version FROM curated_sfc.pointer").fetchone()
            if (actual["version"] if actual else None) != expected_old:
                raise Rejected("SFC_POINTER_CHANGED")
            conn.execute(
                "INSERT INTO curated_sfc.pointer VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET version=EXCLUDED.version",
                (version,),
            )
            conn.execute(
                "UPDATE curated_sfc.versions SET published_at=COALESCE(published_at,now()) WHERE version=%s",
                (version,),
            )
            conn.execute(
                "UPDATE curated_sfc.runs SET state='published' WHERE run_id=%s",
                (row["run_id"],),
            )


def grant_reader(dsn, role):
    from psycopg import sql

    with State(dsn).connection() as conn, conn.transaction():
        if not safe_reader_role(conn, role):
            raise Rejected("SFC_UNSAFE_READER")
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA curated_sfc TO {}").format(
                sql.Identifier(role)
            )
        )
        for table in ("policies", "versions", "corporations", "pointer"):
            conn.execute(
                sql.SQL("GRANT SELECT ON curated_sfc.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(role)
                )
            )
        conn.execute(
            sql.SQL("ALTER ROLE {} SET default_transaction_read_only=on").format(
                sql.Identifier(role)
            )
        )
