"""Source-only state, charged request ledger, immutable releases and restore gate."""

import contextlib
import hashlib
from datetime import datetime, timedelta, timezone
from importlib.resources import files

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..build import connect
from ..security import safe_reader_role
from .parser import canonical, digest, MAX_BODY, TRANSFORM

LOCK = 0x484B4558444149
TABLES = (
    "control",
    "versions",
    "reports",
    "records",
    "version_reports",
    "runs",
    "requests",
)
READS_RUN, READS_DAY, BYTES_RUN, BYTES_DAY = 40, 100, 16 * 1024**2, 32 * 1024**2
MIN_INTERVAL = 3


def migrate(dsn):
    body = (
        files("mcp_open_data_hk.curated")
        .joinpath("migrations/006_hkex_daily.sql")
        .read_text()
    )
    with connect(dsn) as c:
        if c.execute(
            "SELECT 1 FROM pg_namespace WHERE nspname='hkex_daily'"
        ).fetchone():
            body = body.replace("CREATE SCHEMA IF NOT EXISTS hkex_daily;", "")
        c.execute(body)


def grant_reader(dsn, role):
    with connect(dsn, row_factory=dict_row) as c:
        if not safe_reader_role(c, role):
            raise ValueError("SELECT_ONLY_ROLE_REQUIRED")
        c.execute(
            sql.SQL("GRANT USAGE ON SCHEMA hkex_daily TO {}").format(
                sql.Identifier(role)
            )
        )
        c.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA hkex_daily TO {}").format(
                sql.Identifier(role)
            )
        )


@contextlib.contextmanager
def writer(dsn):
    with connect(
        dsn,
        autocommit=True,
        row_factory=dict_row,
        options="-c statement_timeout=30000 -c lock_timeout=1000",
    ) as c:
        if not c.execute("SELECT pg_try_advisory_lock(%s) AS ok", (LOCK,)).fetchone()[
            "ok"
        ]:
            raise ValueError("SOURCE_WRITER_BUSY")
        try:
            yield c
        finally:
            c.execute("SELECT pg_advisory_unlock(%s)", (LOCK,))


def reserve(c, run, path):
    with c.transaction():
        control = c.execute(
            "SELECT * FROM hkex_daily.control WHERE singleton FOR UPDATE"
        ).fetchone()
        now = datetime.now(timezone.utc)
        if control["hold_code"] and (
            control["hold_until"] is None or control["hold_until"] > now
        ):
            raise ValueError("SOURCE_HOLD")
        if c.execute(
            "SELECT 1 FROM hkex_daily.requests WHERE state='unknown' LIMIT 1"
        ).fetchone():
            raise ValueError("SOURCE_REQUEST_RECONCILIATION_REQUIRED")
        if (
            control["last_read_at"]
            and (now - control["last_read_at"]).total_seconds() < MIN_INTERVAL
        ):
            raise ValueError("SOURCE_CADENCE_HOLD")
        budgets = c.execute(
            "SELECT count(*) FILTER(WHERE run_id=%s) AS run_reads,count(*) FILTER(WHERE reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS day_reads,COALESCE(sum(COALESCE(received_bytes,reserved_bytes)) FILTER(WHERE run_id=%s),0) AS run_bytes,COALESCE(sum(COALESCE(received_bytes,reserved_bytes)) FILTER(WHERE reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),0) AS day_bytes FROM hkex_daily.requests WHERE run_id=%s OR reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
            (run, run, run),
        ).fetchone()
        if (
            budgets["run_reads"] >= READS_RUN
            or budgets["day_reads"] >= READS_DAY
            or budgets["run_bytes"] + MAX_BODY > BYTES_RUN
            or budgets["day_bytes"] + MAX_BODY > BYTES_DAY
        ):
            raise ValueError("SOURCE_BUDGET_EXHAUSTED")
        key = c.execute(
            "INSERT INTO hkex_daily.requests(run_id,path,state,reserved_bytes) VALUES(%s,%s,'unknown',%s) RETURNING id",
            (run, path, MAX_BODY),
        ).fetchone()["id"]
        c.execute("UPDATE hkex_daily.control SET last_read_at=now() WHERE singleton")
    return key


def settle(c, key, status, body, retry_after=None):
    with c.transaction():
        c.execute(
            "UPDATE hkex_daily.requests SET state='received',status=%s,received_bytes=%s,sha256=%s WHERE id=%s",
            (status, len(body), hashlib.sha256(body).hexdigest(), key),
        )
        code, until = None, None
        if status in (401, 403) or 300 <= status < 400 and status != 304:
            code = "SOURCE_ACCESS_HOLD"
        elif status in (429, 503):
            try:
                from email.utils import parsedate_to_datetime

                now = datetime.now(timezone.utc)
                until = (
                    now + timedelta(seconds=max(3600, int(retry_after)))
                    if retry_after and str(retry_after).isdigit()
                    else (
                        parsedate_to_datetime(retry_after)
                        if retry_after
                        else now + timedelta(hours=1)
                    )
                )
                if until.tzinfo is None:
                    raise ValueError()
                until = max(until, now + timedelta(hours=1))
                code = "SOURCE_RETRY_HOLD"
            except (ValueError, TypeError, OverflowError):
                code, until = "SOURCE_RETRY_HEADER_UNQUALIFIED", None
        if code:
            c.execute(
                "UPDATE hkex_daily.control SET hold_code=%s,hold_until=%s WHERE singleton",
                (code, until),
            )
            return code
    return None


def save_report(c, report, headers):
    if any(len(canonical(r)) > 65536 for r in report["rows"]):
        raise ValueError("SUMMARY_RECORD_LIMIT")
    sha = digest({"source": report["sourceSha256"], "transform": TRANSFORM})
    with c.transaction():
        inserted = c.execute(
            "INSERT INTO hkex_daily.reports(sha256,day,category,record_count,source_bytes,etag,modified,source_sha256,transform_sha256) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (
                sha,
                report["day"],
                report["category"],
                report["count"],
                report["sourceBytes"],
                headers.get("etag") if len(headers.get("etag", "")) <= 1000 else None,
                (
                    headers.get("last-modified")
                    if len(headers.get("last-modified", "")) <= 200
                    else None
                ),
                report["sourceSha256"],
                TRANSFORM,
            ),
        ).rowcount
        if inserted:
            with c.cursor().copy(
                "COPY hkex_daily.records(report_sha256,id,serial,issuer_id,stock_code,summary_date,category,facts) FROM STDIN"
            ) as out:
                for r in report["rows"]:
                    out.write_row(
                        (
                            sha,
                            r["id"],
                            r["serial"],
                            r["issuer_id"],
                            r["stock_code"],
                            r["summary_date"],
                            r["category"],
                            Jsonb(r),
                        )
                    )
    return sha


def stage(c, run, latest, selected, missing):
    old = c.execute(
        "SELECT accepted_version FROM hkex_daily.control WHERE singleton"
    ).fetchone()["accepted_version"]
    mapping = (
        {
            (r["day"].isoformat(), r["category"]): r["report_sha256"]
            for r in c.execute(
                "SELECT day,category,report_sha256 FROM hkex_daily.version_reports WHERE version=%s AND day>=%s",
                (old, latest - timedelta(days=30)),
            )
        }
        if old
        else {}
    )
    mapping.update(selected)
    if any((latest.isoformat(), k) not in mapping for k in (1, 2, 3, 4)):
        raise ValueError("LATEST_FOUR_REPORTS_REQUIRED")
    if old:
        previous = c.execute(
            "SELECT manifest FROM hkex_daily.versions WHERE version=%s", (old,)
        ).fetchone()["manifest"]
        missing = set(previous.get("unavailableRecheckDates", [])) | set(missing)
        for day, category in selected:
            from .parser import report_path
            from datetime import date

            missing.discard(report_path(date.fromisoformat(day), category))
    manifest = {
        "source": "hkex_daily_summary",
        "view": "published_daily_summaries",
        "transformSha256": TRANSFORM,
        "latestSummaryDate": latest.isoformat(),
        "reports": [
            {"day": day, "category": k, "reportVersion": sha}
            for (day, k), sha in sorted(mapping.items())
        ],
        "unavailableRecheckDates": sorted(missing),
        "dateBasis": "HKEX daily summary date, not event date or exact filing/publication timestamp",
        "scope": "Observed records in the four public daily-summary categories; full filing documents, Form 4 and s.309 notices are outside this feed",
        "currentHoldings": False,
        "providerLicenceClaimed": False,
    }
    if old:
        old_manifest = c.execute(
            "SELECT manifest FROM hkex_daily.versions WHERE version=%s", (old,)
        ).fetchone()["manifest"]
        if old_manifest == manifest:
            return None
    version = "hkex-daily-" + digest({"manifest": manifest, "parent": old})[:32]
    with c.transaction():
        c.execute(
            "INSERT INTO hkex_daily.versions(version,state,base_version,manifest) VALUES(%s,'staged',%s,%s) ON CONFLICT DO NOTHING",
            (version, old, Jsonb(manifest)),
        )
        for (day, category), sha in mapping.items():
            c.execute(
                "INSERT INTO hkex_daily.version_reports VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                (version, day, category, sha),
            )
        c.execute("UPDATE hkex_daily.runs SET version=%s WHERE id=%s", (version, run))
        size = c.execute(
            "SELECT COALESCE(sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))),0) AS n FROM pg_tables WHERE schemaname='hkex_daily'"
        ).fetchone()["n"]
        if size > 1024**3:
            raise ValueError("SOURCE_STORAGE_LIMIT")
    return version


def snapshot(dsn):
    result = {}
    with connect(dsn) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL TIME ZONE 'UTC'")
        for table in TABLES:
            leaves = []
            with c.cursor(name="hkex_daily_fingerprint") as cur:
                cur.itersize = 2000
                cur.execute(
                    sql.SQL("SELECT to_jsonb(t) FROM hkex_daily.{} t").format(
                        sql.Identifier(table)
                    )
                )
                for row in cur:
                    leaves.append(hashlib.sha256(canonical(row[0])).hexdigest())
            result[table] = {
                "rows": len(leaves),
                "sha256": hashlib.sha256(
                    "\n".join(sorted(leaves)).encode()
                ).hexdigest(),
            }
        last_value, is_called = c.execute(
            "SELECT last_value,is_called FROM hkex_daily.requests_id_seq"
        ).fetchone()
        result["requests"]["sequence"] = {
            "lastValue": last_value,
            "isCalled": is_called,
        }
    return result


def qualify(dsn, restored_dsn, version, sha):
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
    if (
        not isinstance(sha, str)
        or len(sha) != 64
        or any(x not in "0123456789abcdef" for x in sha)
    ):
        raise ValueError("INVALID_BACKUP_SHA256")
    original, restored = snapshot(dsn), snapshot(restored_dsn)
    if original != restored:
        raise ValueError("RESTORE_CONTENT_MISMATCH")
    proof = {"backupSha256": sha, "independentlyRestored": True, "allTables": original}
    with writer(dsn) as c:
        if (
            c.execute(
                "UPDATE hkex_daily.versions SET state='qualified',restore_proof=%s WHERE version=%s AND state IN ('staged','qualified')",
                (Jsonb(proof), version),
            ).rowcount
            != 1
        ):
            raise ValueError("STAGED_VERSION_REQUIRED")
    return proof


def publish(dsn, version):
    with writer(dsn) as c, c.transaction():
        row = c.execute(
            "SELECT * FROM hkex_daily.versions WHERE version=%s AND state='qualified' AND restore_proof IS NOT NULL",
            (version,),
        ).fetchone()
        old = c.execute(
            "SELECT accepted_version FROM hkex_daily.control WHERE singleton FOR UPDATE"
        ).fetchone()["accepted_version"]
        if not row or old != row["base_version"]:
            raise ValueError("PUBLICATION_CONFLICT_OR_RESTORE_REQUIRED")
        c.execute(
            "UPDATE hkex_daily.versions SET state='published',published_revision=(SELECT accepted_revision+1 FROM hkex_daily.control WHERE singleton) WHERE version=%s",
            (version,),
        )
        c.execute(
            "UPDATE hkex_daily.control SET accepted_version=%s,accepted_revision=accepted_revision+1,last_changed=now(),latest_source_date=%s WHERE singleton",
            (version, row["manifest"]["latestSummaryDate"]),
        )
    return version
