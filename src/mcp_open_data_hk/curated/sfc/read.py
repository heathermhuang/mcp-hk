"""SELECT-only exact-CE reader; independent source/mode and retention gates."""

from datetime import datetime, timezone

from ..build import connect
from ..read import ReadError
from ..security import safe_reader_role
from .contracts import Corporation, Rejected, ce_reference, digest, encoded
from .policy import POLICY, Policy, configured_policy


def qualified_manifest(row):
    proof = row["restore_proof"] or {}
    if (
        not row["published_at"]
        or proof.get("manifestSha256") != digest(encoded(row["manifest"]))
        or proof.get("factsSha256") != row["facts_sha256"]
    ):
        raise ReadError(
            "SFC_SCHEMA_CHANGED",
            "Accepted source manifest differs from restore qualification",
        )


def source_reader_safe(conn):
    unsafe = conn.execute(
        "SELECT has_schema_privilege('curated_sfc','CREATE') AS creates, EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='curated_sfc' AND (tableowner=current_user OR has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'))) AS writes"
    ).fetchone()
    if any(unsafe.values()):
        raise ReadError("UNSAFE_READER", "SFC reader has write privileges")


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
    def __init__(self, reader, policy=None):
        self.reader, self.policy = reader, policy or configured_policy()

    def status(self):
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
                result = capability_status()
                if not conn.execute(
                    "SELECT to_regclass('curated_sfc.pointer') AS name"
                ).fetchone()["name"]:
                    return dict(
                        result,
                        state="not_installed",
                        reasonCode="SFC_SCHEMA_NOT_INSTALLED",
                    )
                result.update(
                    state="not_activated", reasonCode="SFC_POLICY_NOT_ACTIVATED"
                )
                source_reader_safe(conn)
                active = conn.execute(
                    "SELECT sha256,record FROM curated_sfc.policies WHERE active AND revoked_at IS NULL"
                ).fetchone()
                columns = "scheduled_for,started_at,state,requests"
                extended = conn.execute(
                    "SELECT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid='curated_sfc.runs'::regclass AND attname='job_outcomes' AND NOT attisdropped) AS installed"
                ).fetchone()["installed"]
                if (
                    extended
                    and conn.execute(
                        "SELECT has_column_privilege('curated_sfc.runs','job_outcomes','SELECT') AS allowed"
                    ).fetchone()["allowed"]
                ):
                    columns += ",provenance,source_release,job_outcomes,job_updated_at"
                last = conn.execute(
                    "SELECT "
                    + columns
                    + " FROM curated_sfc.runs ORDER BY started_at DESC,run_id DESC LIMIT 1"
                ).fetchone()
                unresolved = conn.execute(
                    "SELECT count(*) AS n FROM curated_sfc.attempts WHERE state='unknown'"
                ).fetchone()["n"]
                successful = conn.execute(
                    "SELECT max(settled_at) AS stamp FROM curated_sfc.attempts WHERE state='ok'"
                ).fetchone()["stamp"]
                result.update(
                    lastAttemptAt=last["started_at"] if last else None,
                    lastSuccessAt=successful,
                    lastRun=last,
                    unresolvedRequests=unresolved,
                )
                row = conn.execute(
                    "SELECT v.* FROM curated_sfc.versions v JOIN curated_sfc.pointer p USING(version)"
                ).fetchone()
                if row:
                    qualified_manifest(row)
                    result.update(
                        acceptedVersion=row["version"],
                        publishedAt=row["published_at"],
                        expiresAt=row["expires_at"],
                    )
                    result["cohort"]["accepted"] = len(row["manifest"]["cohort"])
                    result["freshnessBasis"] = "dated_observation_not_realtime"
                if not active:
                    if row:
                        result.update(
                            state="policy_unavailable", reasonCode="SFC_POLICY_REVOKED"
                        )
                    return result
                policy = Policy.model_validate(active["record"])
                if policy.sha256 != active["sha256"]:
                    raise ReadError("SFC_POLICY_CHANGED", "Policy identity changed")
                result.update(
                    policySha256=policy.sha256,
                    modes=policy.modes,
                    policyRecheckAt=policy.recheckAt,
                    cohort={
                        "accepted": 0,
                        "maximum": 25,
                        "tracked": len(policy.trackedCorporateReferences),
                        "scope": "tracked_corporate_subset",
                    },
                )
                adopted = policy.sha256 == self.policy.sha256
                try:
                    policy.require("automation", "retention", "backup")
                    valid = True
                except Rejected:
                    valid = False
                result.update(
                    state="not_published", reasonCode="SFC_NO_ACCEPTED_OBSERVATION"
                )
                if row:
                    if not row["published_at"] or not row["restore_proof"]:
                        raise ReadError(
                            "SFC_POINTER_UNQUALIFIED",
                            "Accepted pointer lacks qualification",
                        )
                    result.update(
                        acceptedVersion=row["version"],
                        publishedAt=row["published_at"],
                        expiresAt=row["expires_at"],
                        restoreQualified=True,
                    )
                    result["cohort"]["accepted"] = len(row["manifest"]["cohort"])
                    result["freshnessBasis"] = "dated_observation_not_realtime"
                    real_transport = (
                        row["manifest"].get("format") == "sfc-public-register-v1"
                    )
                    current = row["expires_at"] > datetime.now(timezone.utc)
                    result["qualifiedLiveTransport"] = (
                        real_transport and valid and adopted
                    )
                    same_policy = row["policy_sha256"] == policy.sha256
                    modes = (
                        [
                            m
                            for m in ("rest", "mcp", "browser")
                            if policy.modes[m] == "allowed"
                        ]
                        if valid
                        and adopted
                        and same_policy
                        and current
                        and real_transport
                        else []
                    )
                    result.update(
                        enabledModes=modes,
                        state="available" if modes else "observation_not_public",
                        reasonCode=None if modes else "SFC_OUTPUT_NOT_QUALIFIED",
                    )
                    if not current:
                        result.update(
                            state="expired",
                            reasonCode="SFC_RETENTION_EXPIRED",
                            enabledModes=[],
                        )
                    elif last and last["state"] in {"failed", "partial", "running"}:
                        result.update(
                            state="source_incomplete_data_retained",
                            reasonCode="SFC_LATEST_RUN_" + last["state"].upper(),
                        )
                if not valid or not adopted:
                    result.update(
                        state="policy_unavailable",
                        reasonCode=(
                            "SFC_POLICY_NOT_ADOPTED"
                            if not adopted
                            else "SFC_POLICY_UNQUALIFIED"
                        ),
                        enabledModes=[],
                    )
                hold = conn.execute(
                    "SELECT until_at,reason FROM curated_sfc.holds WHERE until_at>now()"
                ).fetchone()
                result["hold"] = hold
                return result
        finally:
            self.reader.slots.release()

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
                source_reader_safe(conn)
                row = conn.execute(
                    "SELECT v.*,p.record FROM curated_sfc.versions v JOIN curated_sfc.policies p ON p.sha256=v.policy_sha256 WHERE v.version=COALESCE(%s,(SELECT version FROM curated_sfc.pointer)) AND v.published_at IS NOT NULL AND p.active AND p.revoked_at IS NULL",
                    (version,),
                ).fetchone()
                if not row:
                    raise ReadError(
                        "SFC_VERSION_UNAVAILABLE", "No qualified SFC observation"
                    )
                qualified_manifest(row)
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
                        "captureFormat": row["manifest"].get("format"),
                        "sourceUrl": active.route.replace("{ce}", ce),
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
