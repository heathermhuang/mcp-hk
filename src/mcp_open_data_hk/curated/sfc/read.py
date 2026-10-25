"""SELECT-only exact-CE reader; independent source/mode and retention gates."""

from datetime import datetime, timezone

from ..build import connect
from ..read import ReadError
from ..security import safe_reader_role
from .contracts import Corporation, Rejected, ce_reference, digest, encoded
from .policy import POLICY, Policy


def capability_status():
    return {
        "sourceId": "sfc_register",
        "state": "unqualified",
        "acceptedVersion": None,
        "qualifiedLiveTransport": False,
        "modes": {key: "unknown" for key in POLICY.modes},
        "enabledModes": [],
        "cohort": {"accepted": 0, "maximum": 25, "scope": "tracked_corporate_subset"},
        "lastAttemptAt": None,
        "lastSuccessAt": None,
        "sourceCutoff": None,
        "freshnessBasis": "no_qualified_observation",
        "completeRegulatoryHistory": False,
        "reasonCode": "SFC_SOURCE_UNQUALIFIED",
        "policySha256": POLICY.sha256,
    }


class SfcReader:
    def __init__(self, reader, policy=POLICY):
        self.reader, self.policy = reader, policy

    def status(self):
        # Current production contract is intentionally closed even without PG.
        return capability_status()

    def verify(self, ce, version=None, mode="rest"):
        try:
            ce = ce_reference(ce)
            self.policy.require(mode, "retention")
        except Rejected as exc:
            raise ReadError(
                str(exc), "Fresh SFC verification is not qualified"
            ) from exc
        if mode not in {"rest", "mcp", "browser"}:
            raise ReadError("SFC_MODE_UNQUALIFIED", "Unsupported SFC read mode")
        if version is not None and (not isinstance(version, str) or len(version) > 100):
            raise ReadError("INVALID_QUERY", "Invalid SFC version")
        from psycopg.rows import dict_row

        if not self.reader.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Shared read limit reached")
        try:
            with connect(
                self.reader.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250",
            ) as conn:
                if not safe_reader_role(conn):
                    raise ReadError(
                        "UNSAFE_READER", "Use a dedicated SELECT-only reader"
                    )
                unsafe = conn.execute(
                    "SELECT has_schema_privilege('curated_sfc','CREATE') AS creates, EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='curated_sfc' AND (tableowner=current_user OR has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'))) AS writes"
                ).fetchone()
                if any(unsafe.values()):
                    raise ReadError("UNSAFE_READER", "SFC reader has write privileges")
                row = conn.execute(
                    "SELECT v.*,p.record FROM curated_sfc.versions v JOIN curated_sfc.policies p ON p.sha256=v.policy_sha256 WHERE v.version=COALESCE(%s,(SELECT version FROM curated_sfc.pointer)) AND v.published_at IS NOT NULL AND p.active AND p.revoked_at IS NULL",
                    (version,),
                ).fetchone()
                if not row:
                    raise ReadError(
                        "SFC_VERSION_UNAVAILABLE", "No qualified SFC observation"
                    )
                active = Policy.model_validate(row["record"])
                if (
                    active.sha256 != self.policy.sha256
                    or active.sha256 != row["policy_sha256"]
                ):
                    raise ReadError("SFC_POLICY_CHANGED", "Policy identity changed")
                active.require(mode, "retention")
                current = conn.execute(
                    "SELECT version FROM curated_sfc.pointer"
                ).fetchone()
                historical = not current or row["version"] != current["version"]
                if historical:
                    active.require("history")
                if row["expires_at"] <= datetime.now(timezone.utc):
                    raise ReadError(
                        "VERSION_EXPIRED", "SFC permitted retention expired"
                    )
                fact = conn.execute(
                    "SELECT fact FROM curated_sfc.corporations WHERE version=%s AND ce=%s",
                    (row["version"], ce),
                ).fetchone()
                if not fact:
                    raise ReadError(
                        "NOT_FOUND",
                        "CE is outside this accepted cohort; no licence inference",
                    )
                record = Corporation.model_validate(fact["fact"])
                all_facts = [
                    r["fact"]
                    for r in conn.execute(
                        "SELECT fact FROM curated_sfc.corporations WHERE version=%s ORDER BY ce",
                        (row["version"],),
                    )
                ]
                if digest(encoded(all_facts)) != row["facts_sha256"]:
                    raise ReadError(
                        "SFC_SCHEMA_CHANGED", "Accepted facts differ from restore proof"
                    )
                result = {
                    "version": row["version"],
                    "data": record.model_dump(mode="json"),
                    "provenance": {
                        "sourceId": "sfc_register",
                        "view": "sfc_observation",
                        "policySha256": active.sha256,
                        "freshnessBasis": "dated_observation_not_realtime",
                        "scope": "tracked_corporate_subset",
                        "completeRegulatoryHistory": False,
                    },
                }
                # Recheck the pointer: a concurrent publication can turn this
                # selected version into history while its facts are read.
                current = conn.execute(
                    "SELECT version FROM curated_sfc.pointer"
                ).fetchone()
                if not current or row["version"] != current["version"]:
                    active.require("history")
                # Policy changes while a long read executes must not bypass a hold.
                active.require(mode, "retention")
                if not conn.execute(
                    "SELECT 1 FROM curated_sfc.policies WHERE sha256=%s AND active AND revoked_at IS NULL",
                    (active.sha256,),
                ).fetchone():
                    raise ReadError("SFC_POLICY_CHANGED", "Policy changed during read")
                return result
        except Rejected as exc:
            raise ReadError(str(exc), "SFC output policy is unavailable") from exc
        finally:
            self.reader.slots.release()
