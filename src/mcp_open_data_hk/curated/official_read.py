"""Version-pinned official read view with no implied archive identity crosswalk."""

import contextlib
import re
import time

from datetime import datetime, timedelta, timezone

from .official import ATTRIBUTION, CATALOGUE, TERMS, LIMITATIONS
from .read import ReadError, prefix_end
from .normalize import search_key


class OfficialReader:
    def __init__(self, archive):
        self.archive = archive

    @contextlib.contextmanager
    def request(self):
        from psycopg.rows import dict_row
        from .build import connect
        from .security import safe_reader_role

        if not self.archive.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Read concurrency limit reached")
        try:
            with connect(
                self.archive.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as conn:
                if not safe_reader_role(conn):
                    raise ReadError(
                        "UNSAFE_READER", "Serving requires a dedicated SELECT-only role"
                    )
                unsafe = conn.execute(
                    "SELECT has_schema_privilege('curated','CREATE') AS creates, EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='curated' AND (has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR tableowner=current_user)) AS writes"
                ).fetchone()
                if any(unsafe.values()):
                    raise ReadError(
                        "UNSAFE_READER", "Official reader has write privileges"
                    )
                yield conn
        except Exception as exc:
            from psycopg.errors import LockNotAvailable, QueryCanceled

            if isinstance(exc, (LockNotAvailable, QueryCanceled)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Official query exceeded its bound"
                ) from exc
            raise
        finally:
            self.archive.slots.release()

    def version(self, conn, version=None):
        if version:
            row = conn.execute(
                "SELECT * FROM curated.official_versions WHERE version=%s", (version,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT v.* FROM curated.official_versions v JOIN curated.official_pointer p USING(version)"
            ).fetchone()
        if not row:
            raise ReadError(
                "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                "No accepted official observation version",
            )
        return row

    def result(self, release, data, cursor=None):
        return {
            "version": release["version"],
            "data": data,
            "nextCursor": cursor,
            "provenance": {
                "view": "latest_observed",
                "attribution": ATTRIBUTION,
                "termsUrl": TERMS,
                "sourceUrl": CATALOGUE,
                "currentVerification": False,
                "coverage": release["manifest"],
                "limitations": LIMITATIONS,
            },
        }

    def search(self, name=None, namespace=None, value=None, limit=20, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadError("INVALID_LIMIT", "Limit must be 1 through 100")
        if name is not None:
            key = search_key(name)
            if (
                namespace is not None
                or value is not None
                or not 2 <= len(key) <= 200
                or "\0" in key
            ):
                raise ReadError(
                    "INVALID_QUERY", "Choose a name prefix or exact official identifier"
                )
            filters = {"name": key}
            condition = "((r.name_key >= %s AND r.name_key < %s) OR (r.name2_key >= %s AND r.name2_key < %s))"
            params = (key, prefix_end(key), key, prefix_end(key))
        else:
            if (
                namespace not in {"cr:local:brn", "cr:foreign:brn", "cr:mlr"}
                or not isinstance(value, str)
                or not re.fullmatch(r"[A-Za-z0-9]{1,20}", value)
            ):
                raise ReadError(
                    "INVALID_QUERY",
                    "Use cr:local:brn, cr:foreign:brn or cr:mlr with the exact source value",
                )
            filters = {"namespace": namespace, "value": value}
            condition = "r.entity_id=%s"
            params = (namespace.replace(":brn", "") + ":" + value,)
        state = (
            self.archive.unseal(cursor, "official_search", filters) if cursor else None
        )
        with self.request() as conn:
            release = self.version(conn, state["version"] if state else None)
            rows = conn.execute(
                "SELECT DISTINCT ON(r.entity_id) r.entity_id,r.record FROM curated.official_records r JOIN curated.official_members m USING(capture_id) WHERE m.version=%s AND "
                + condition
                + " AND r.entity_id>%s ORDER BY r.entity_id, r.record->>'coverageEnd' DESC NULLS LAST,r.fact_id LIMIT %s",
                (
                    release["version"],
                    *params,
                    state["last"] if state else "",
                    limit + 1,
                ),
            ).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            token = (
                self.archive.seal(
                    {
                        "op": "official_search",
                        "filters": filters,
                        "version": release["version"],
                        "last": rows[-1]["entity_id"],
                        "expires": (
                            state["expires"] if state else int(time.time()) + 172800
                        ),
                    }
                )
                if more
                else None
            )
            data = [
                {
                    k: row["record"].get(k)
                    for k in (
                        "entity_id",
                        "kind",
                        "name1",
                        "chinese_name",
                        "identifier",
                        "coverageStart",
                        "coverageEnd",
                        "register",
                    )
                }
                for row in rows
            ]
            return self.result(release, data, token)

    def get(self, entity_id, version=None):
        if not re.fullmatch(
            r"cr:(?:local|foreign|mlr):[A-Za-z0-9]{1,20}", str(entity_id)
        ):
            raise ReadError(
                "INVALID_ID", "Use the exact official entity_id returned by search"
            )
        with self.request() as conn:
            release = self.version(conn, version)
            rows = conn.execute(
                "SELECT r.record || CASE WHEN o.observation_id IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('observedAt',o.observed_at,'observationId',o.observation_id) END AS record FROM curated.official_records r JOIN curated.official_members m USING(capture_id) LEFT JOIN curated.official_address_observations o ON o.capture_id=m.capture_id AND o.source_key=m.source_key WHERE m.version=%s AND r.entity_id=%s ORDER BY r.record->>'coverageEnd' DESC NULLS LAST,o.observed_at DESC NULLS LAST,r.fact_id LIMIT 101",
                (release["version"], entity_id),
            ).fetchall()
            if not rows:
                raise ReadError(
                    "NOT_FOUND",
                    "No accepted observation for this exact source identity",
                )
            records = [r["record"] for r in rows[:100]]
            address_row = conn.execute(
                "SELECT r.record || jsonb_build_object('observedAt',o.observed_at,'observationId',o.observation_id) AS record FROM curated.official_records r JOIN curated.official_members m USING(capture_id) LEFT JOIN curated.official_address_observations o ON o.capture_id=m.capture_id AND o.source_key=m.source_key WHERE m.version=%s AND r.entity_id=%s AND r.record->>'kind'='address_observation' ORDER BY coalesce(o.observed_at,(r.record->'source'->>'fetchedAt')::timestamptz) DESC,r.fact_id LIMIT 1",
                (release["version"], entity_id),
            ).fetchone()
            latest = records[0]
            return self.result(
                release,
                {
                    "entity_id": entity_id,
                    "kind": latest["kind"],
                    "name1": latest["name1"],
                    "chinese_name": latest.get("chinese_name"),
                    "identifier": latest["identifier"],
                    "observations": records,
                    "latestAddress": address_row["record"] if address_row else None,
                    "observationCountScope": "at_most_100_in_selected_version",
                    "observationsTruncated": len(rows) > 100,
                },
            )

    def address_history(
        self, entity_id, limit=20, cursor=None, version=None, asOf=None
    ):
        if not re.fullmatch(r"cr:(?:local|foreign):[A-Za-z0-9]{1,20}", str(entity_id)):
            raise ReadError("INVALID_ID", "Use an exact company source identity")
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadError("INVALID_LIMIT", "Limit must be 1 through 100")
        if asOf is not None:
            raise ReadError(
                "AS_OF_UNSUPPORTED",
                "Observation dates do not establish an effective address interval",
            )
        filters = {"entityId": entity_id}
        state = (
            self.archive.unseal(cursor, "official_addresses", filters)
            if cursor
            else None
        )
        if state and version and state["version"] != version:
            raise ReadError("INVALID_CURSOR", "Cursor version differs")
        with self.request() as conn:
            release = self.version(conn, state["version"] if state else version)
            rows = conn.execute(
                "SELECT o.observation_id,o.observed_at,r.record FROM curated.official_address_observations o JOIN curated.official_members m ON m.source_key=o.source_key AND m.capture_id=o.capture_id JOIN curated.official_records r ON r.capture_id=o.capture_id AND r.entity_id=o.entity_id WHERE m.version=%s AND o.entity_id=%s AND (o.observed_at,o.observation_id)<(%s::timestamptz,%s) ORDER BY o.observed_at DESC,o.observation_id DESC LIMIT %s",
                (
                    release["version"],
                    entity_id,
                    state["last"][0] if state else "infinity",
                    state["last"][1] if state else "",
                    limit + 1,
                ),
            ).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            token = (
                self.archive.seal(
                    {
                        "op": "official_addresses",
                        "filters": filters,
                        "version": release["version"],
                        "last": [
                            rows[-1]["observed_at"].isoformat(),
                            rows[-1]["observation_id"],
                        ],
                        "expires": (
                            state["expires"] if state else int(time.time()) + 172800
                        ),
                    }
                )
                if more
                else None
            )
            return self.result(
                release,
                [
                    dict(
                        r["record"],
                        observedAt=r["observed_at"].isoformat(),
                        observationId=r["observation_id"],
                    )
                    for r in rows
                ],
                token,
            )

    def status(self):
        with self.request() as conn:
            release = self.version(conn)
            runs = conn.execute(
                "SELECT run_id,started_at,finished_at,status,receipt FROM curated.official_runs ORDER BY started_at DESC LIMIT 2"
            ).fetchall()
            # Older deployments can serve the expanded reader before migration.
            migrated = conn.execute(
                "SELECT to_regclass('curated.official_jobs') AS name"
            ).fetchone()["name"]
            maintenance = None
            if migrated:
                from .official_state import plan

                jobs = conn.execute(
                    "SELECT job_id,operation,scheduled_for,started_at,finished_at,published_at,status,collection_status,publication_status,backup_status FROM curated.official_jobs WHERE family IN ('cr','recovery') ORDER BY started_at DESC LIMIT 6"
                ).fetchall()
                queue = conn.execute(
                    "SELECT count(*) AS eligible,count(*) FILTER(WHERE last_success IS NOT NULL) AS observed,count(*) FILTER(WHERE outcome NOT IN ('success','never')) AS held,count(*) FILTER(WHERE next_due<=now()) AS due,count(*) FILTER(WHERE last_success<now()-interval '90 days') AS olderThan90Days,count(*) FILTER(WHERE last_success>=now()-interval '7 days') AS checkedWithin7Days,count(*) FILTER(WHERE last_success<now()-interval '7 days' AND last_success>=now()-interval '30 days') AS checked8To30DaysAgo,count(*) FILTER(WHERE last_success<now()-interval '30 days' AND last_success>=now()-interval '90 days') AS checked31To90DaysAgo,min(last_success) AS oldestObservation,max(last_success) AS newestObservation FROM curated.official_address_queue"
                ).fetchone()
                for old, new in [
                    ("olderthan90days", "olderThan90Days"),
                    ("checkedwithin7days", "checkedWithin7Days"),
                    ("checked8to30daysago", "checked8To30DaysAgo"),
                    ("checked31to90daysago", "checked31To90DaysAgo"),
                    ("oldestobservation", "oldestObservation"),
                    ("newestobservation", "newestObservation"),
                ]:
                    if old in queue:
                        queue[new] = queue[old]
                budgets = conn.execute(
                    "SELECT provider,day,requests,bytes FROM curated.official_daily_budgets WHERE day=CURRENT_DATE"
                ).fetchall()
                current = datetime.now(timezone.utc)
                next_due = current.replace(hour=5, minute=0, second=0, microsecond=0)
                if next_due <= current:
                    next_due += timedelta(days=1)
                jobs = [
                    {
                        "jobId": r["job_id"],
                        "operation": r["operation"],
                        "scheduledFor": r["scheduled_for"],
                        "startedAt": r["started_at"],
                        "finishedAt": r["finished_at"],
                        "publishedAt": r["published_at"],
                        "status": r["status"],
                        "collectionStatus": r["collection_status"],
                        "publicationStatus": r["publication_status"],
                        "backupStatus": r["backup_status"],
                    }
                    for r in jobs
                ]
                from .official_address_stage import usage as address_usage
                from .official_offsite_job import gate

                recovery = {
                    r["family"]: r["state"]
                    for r in conn.execute(
                        "SELECT family,state FROM curated.official_source_state WHERE family IN ('offsite','offsite_restore')"
                    )
                }
                last = recovery.get("offsite", {}).get("lastSuccess", {})
                daily_observed = (
                    conn.execute(
                        "SELECT 1 FROM curated.official_jobs WHERE family='recovery' AND status='success' AND receipt->>'scheduleKind'='daily' LIMIT 1"
                    ).fetchone()
                    is not None
                )
                coverage_current = gate(conn)
                maintenance = {
                    "offsite": {
                        "lastUploadAt": last.get("finishedAt"),
                        "lastAttemptOutcome": recovery.get("offsite", {})
                        .get("lastAttempt", {})
                        .get("status"),
                        "lastUploadScheduleKind": last.get("scheduleKind"),
                        "restoreVerifiedAt": recovery.get("offsite_restore", {}).get(
                            "verifiedAt"
                        ),
                        "coverageCurrent": coverage_current,
                        "dailyCadenceObserved": daily_observed,
                        "targetRpoHours": 24,
                    },
                    "backfillRecoveryGateOpen": coverage_current,
                    "addressPolicy": address_usage(conn),
                    "nextConfiguredDueAt": next_due.isoformat(),
                    "sourceChecks": conn.execute(
                        "SELECT family,checked_at,hold_until,state->>'status' AS status FROM curated.official_source_state WHERE family NOT IN ('inventory_baseline','health') AND family NOT LIKE 'address:%%' ORDER BY family LIMIT 110"
                    ).fetchall(),
                    "inventory": plan(conn),
                    "jobs": jobs,
                    "addressQueue": queue,
                    "dailyBudgets": budgets,
                    "offsiteRpoQualified": coverage_current and daily_observed,
                }
            # Invocation/source details remain private; public readers get outcomes.
            runs = [{k: v for k, v in row.items() if k != "receipt"} for row in runs]
            return self.result(
                release,
                {
                    "coverage": release["manifest"],
                    "recentRuns": runs,
                    "maintenance": maintenance,
                },
            )
