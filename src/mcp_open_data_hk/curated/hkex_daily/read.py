"""Version-pinned, SELECT-only reads; a read never starts source collection."""

import contextlib
import json
import re
import time
from datetime import date, timedelta

from psycopg.rows import dict_row

from ..build import connect
from ..read import ReadError
from ..security import safe_reader_role

from .contracts import SOURCE, RECORD_ID, VERSION, NOTICE


class DailyReader:
    def __init__(self, shared):
        self.shared = shared

    @contextlib.contextmanager
    def request(self):
        if not self.shared.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Shared read slots are busy")
        try:
            with connect(
                self.shared.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as c:
                if not safe_reader_role(c):
                    raise ReadError(
                        "UNSAFE_READER", "Dedicated SELECT-only reader required"
                    )
                row = c.execute(
                    "SELECT has_schema_privilege('hkex_daily','CREATE') AS creates,EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='hkex_daily' AND (tableowner=current_user OR has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES'))) AS writes"
                ).fetchone()
                if any(row.values()):
                    raise ReadError(
                        "UNSAFE_READER", "Source reader has write privileges"
                    )
                yield c
        except Exception as exc:
            from psycopg.errors import QueryCanceled, LockNotAvailable

            if isinstance(exc, (QueryCanceled, LockNotAvailable)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Bounded source query timed out"
                ) from exc
            raise
        finally:
            self.shared.slots.release()

    def status(self):
        try:
            with self.request() as c:
                control = c.execute(
                    "SELECT * FROM hkex_daily.control WHERE singleton"
                ).fetchone()
                version = c.execute(
                    "SELECT version,manifest,created_at FROM hkex_daily.versions WHERE version=%s AND state='published'",
                    (control["accepted_version"],),
                ).fetchone()
                run = c.execute(
                    "SELECT id,started_at,finished_at,scheduled_for,provenance,state,code,version,request_count,received_bytes,latest_source_date FROM hkex_daily.runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
                pending = c.execute(
                    "SELECT version FROM hkex_daily.versions WHERE state IN ('staged','qualified') ORDER BY created_at LIMIT 1"
                ).fetchone()
                rows = (
                    c.execute(
                        "SELECT count(*) AS rows,count(DISTINCT r.serial) AS filings,min(r.summary_date) AS first_summary,max(r.summary_date) AS latest_summary FROM hkex_daily.records r JOIN hkex_daily.version_reports p ON p.report_sha256=r.report_sha256 AND p.version=%s",
                        (control["accepted_version"],),
                    ).fetchone()
                    if version
                    else None
                )
                return {
                    "source": SOURCE,
                    "state": "available" if version else "not_published",
                    "version": version["version"] if version else None,
                    "coverage": dict(version["manifest"], **rows) if version else None,
                    "updater": {
                        "lastChecked": control["last_checked"],
                        "lastSuccessfulRead": control["last_success"],
                        "lastChanged": control["last_changed"],
                        "holdCode": control["hold_code"],
                        "holdUntil": control["hold_until"],
                        "lastRun": run,
                        "pendingVersion": pending["version"] if pending else None,
                        "schedule": "09:20, 13:20, 17:20, 18:20 and 22:20 Asia/Hong_Kong",
                        "reconciliation": "Recent seven calendar summary dates rechecked once per UTC day; current published summary rechecked every occurrence",
                        "limits": {
                            "requestsRun": 40,
                            "requestsDay": 100,
                            "concurrent": 1,
                            "minimumSecondsBetweenRequests": 3,
                        },
                    },
                    "notice": NOTICE,
                }
        except Exception as exc:
            from psycopg.errors import (
                UndefinedTable,
                InvalidSchemaName,
                InsufficientPrivilege,
            )

            if not isinstance(
                exc, (UndefinedTable, InvalidSchemaName, InsufficientPrivilege)
            ):
                raise
            return {
                "source": SOURCE,
                "state": "not_published",
                "version": None,
                "coverage": None,
                "updater": None,
                "notice": NOTICE,
            }

    def query(self, operation, params):
        params = {k: v for k, v in params.items() if v is not None}
        limit = params.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadError("INVALID_QUERY", "Use limit 1–100")
        if operation not in {"disclosures", "disclosure"}:
            raise ReadError("INVALID_QUERY", "Unknown daily-summary operation")
        filters = {
            k: v for k, v in params.items() if k not in {"cursor", "version", "limit"}
        }
        cursor = (
            self.shared.unseal(params["cursor"], SOURCE + ":" + operation, filters)
            if params.get("cursor")
            else None
        )
        version = params.get("version")
        if version and not re.fullmatch(VERSION, version):
            raise ReadError("INVALID_QUERY", "Use an exact returned source version")
        if cursor:
            if version and version != cursor["version"]:
                raise ReadError("INVALID_CURSOR", "Cursor version differs")
            version = cursor["version"]
        with self.request() as c:
            release = c.execute(
                "SELECT v.* FROM hkex_daily.versions v WHERE v.version=COALESCE(%s,(SELECT accepted_version FROM hkex_daily.control WHERE singleton)) AND v.state='published'",
                (version,),
            ).fetchone()
            if not release:
                raise ReadError(
                    "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                    "No accepted daily-summary version",
                )
            if version and release["created_at"].timestamp() < time.time() - 7 * 86400:
                # Old cursor versions have a guaranteed 48h window; immutable
                # backup retention does not imply an unlimited public cursor.
                current = c.execute(
                    "SELECT accepted_version FROM hkex_daily.control WHERE singleton"
                ).fetchone()["accepted_version"]
                if version != current:
                    raise ReadError(
                        "VERSION_EXPIRED", "Restart from the current summary version"
                    )
            selected, more = release["version"], None
            query_coverage = {
                "scope": "one_observed_report_row",
                "completeRequestedReports": True,
            }
            if operation == "disclosure":
                key = params.get("recordId", "")
                if not re.fullmatch(RECORD_ID, key):
                    raise ReadError(
                        "INVALID_ID", "Use an exact returned summary record ID"
                    )
                rows = c.execute(
                    "SELECT r.facts FROM hkex_daily.records r JOIN hkex_daily.version_reports p ON p.report_sha256=r.report_sha256 AND p.version=%s WHERE r.id=%s",
                    (selected, key),
                ).fetchall()
                if len(rows) != 1:
                    raise ReadError(
                        "NOT_FOUND", "Summary record absent from pinned version"
                    )
                data = rows[0]["facts"]
            else:
                code = params.get("stockCode")
                if code is not None:
                    if not isinstance(code, str) or not re.fullmatch(
                        r"[0-9]{1,5}", code
                    ):
                        raise ReadError("INVALID_QUERY", "Use a digit stock code")
                    code = code.zfill(5)
                start, end = params.get("start"), params.get("end")
                if bool(start) != bool(end):
                    raise ReadError("INVALID_QUERY", "Provide both summary date bounds")
                if start:
                    try:
                        begin, finish = date.fromisoformat(start), date.fromisoformat(
                            end
                        )
                        if not 1 <= (finish - begin).days <= 31:
                            raise ValueError()
                    except (ValueError, TypeError) as exc:
                        raise ReadError(
                            "INVALID_QUERY", "Use 1–31 summary days, end exclusive"
                        ) from exc
                else:
                    finish = date.fromisoformat(
                        release["manifest"]["latestSummaryDate"]
                    ) + timedelta(days=1)
                    begin = finish - timedelta(days=7)
                known = {
                    (r["day"], r["category"]) for r in release["manifest"]["reports"]
                }
                missing = [
                    {
                        "summaryDate": (begin + timedelta(days=i)).isoformat(),
                        "category": k,
                    }
                    for i in range((finish - begin).days)
                    for k in (1, 2, 3, 4)
                    if ((begin + timedelta(days=i)).isoformat(), k) not in known
                ]
                query_coverage = {
                    "scope": "observed_daily_reports_only",
                    "basis": "summary_date",
                    "start": begin.isoformat(),
                    "endExclusive": finish.isoformat(),
                    "completeRequestedReports": not missing,
                    "unobservedReports": missing,
                }
                last = cursor["last"] if cursor else ["9999-12-31", "\uffff"]
                rows = c.execute(
                    "SELECT r.summary_date,r.id,r.facts FROM hkex_daily.records r JOIN hkex_daily.version_reports p ON p.report_sha256=r.report_sha256 AND p.version=%s WHERE (%s::text IS NULL OR r.stock_code=%s) AND r.summary_date>=%s AND r.summary_date<%s AND (r.summary_date,r.id)<(%s::date,%s) ORDER BY r.summary_date DESC,r.id DESC LIMIT %s",
                    (selected, code, code, begin, finish, last[0], last[1], limit + 1),
                ).fetchall()
                if len(rows) > limit:
                    rows = rows[:limit]
                    more = [rows[-1]["summary_date"].isoformat(), rows[-1]["id"]]
                data = [r["facts"] for r in rows]
            result = {
                "source": SOURCE,
                "version": selected,
                "data": data,
                "coverage": release["manifest"],
                "queryCoverage": query_coverage,
                "nextCursor": (
                    self.shared.seal(
                        {
                            "op": SOURCE + ":" + operation,
                            "filters": filters,
                            "version": selected,
                            "last": more,
                            "expires": time.time() + 48 * 3600,
                        }
                    )
                    if more
                    else None
                ),
                "notice": NOTICE,
            }
            if len(json.dumps(result, ensure_ascii=False).encode()) > 2 * 1024**2:
                raise ReadError("OUTPUT_LIMIT", "Summary page exceeds 2 MiB")
            return result
