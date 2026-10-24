"""One bounded ordinary-scheduler run; owner credentials never reach readers."""

import argparse
import os
import resource
import sys
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .build import connect
from . import official_state as state
from .official import (
    CATALOGUE,
    LIMITATIONS,
    ML_BASE,
    ML_FILES,
    SourceRejected,
    address,
    capture_receipt,
    digest,
    discover,
    encoded,
    lenders,
    now,
    verify_xls,
    weekly,
)


class Collector:
    def __init__(self, conn=None, request_limit=48):
        self.conn = conn
        self.request_limit = request_limit
        self.requests = 0
        self.bytes = 0
        self.checks = []
        self.deadline = time.monotonic() + 780
        self.client = httpx.Client(timeout=30, follow_redirects=False, trust_env=False)

    def get(self, url, params=None):
        self.requests += 1
        if self.requests > self.request_limit or time.monotonic() > self.deadline:
            raise SourceRejected("RUN_REQUEST_OR_TIME_BUDGET")
        reserved = state.reserve(self.conn) if self.conn else None
        with self.client.stream("GET", url, params=params) as response:
            check = {
                "sourceUrl": str(response.url),
                "checkedAt": now(),
                "httpStatus": response.status_code,
                "sourceLastModified": response.headers.get("last-modified"),
            }
            self.checks.append(check)
            if self.conn and response.status_code in {429, 503}:
                retry = response.headers.get("retry-after", "3600")
                try:
                    seconds = int(retry)
                except ValueError:
                    try:
                        seconds = int(
                            (
                                parsedate_to_datetime(retry)
                                - datetime.now(timezone.utc)
                            ).total_seconds()
                        )
                    except (ValueError, TypeError):
                        seconds = 3600
                state.hold(self.conn, seconds)
            if response.status_code != 200:
                raise SourceRejected("SOURCE_HTTP_" + str(response.status_code))
            body = bytearray()
            for chunk in response.iter_bytes():
                self.bytes += len(chunk)
                if (
                    len(body) + len(chunk) > 8 * 1024 * 1024
                    or self.bytes > 64 * 1024 * 1024
                    or time.monotonic() > self.deadline
                ):
                    raise SourceRejected("RUN_BYTE_OR_TIME_BUDGET")
                body.extend(chunk)
            if self.conn:
                state.settle_bytes(self.conn, reserved, len(body))
            check.update(sha256=digest(body), bytes=len(body))
            return bytes(body), response.headers

    def close(self):
        self.client.close()


def current_members(conn):
    return {
        r["source_key"]: r["capture_id"]
        for r in conn.execute(
            "SELECT m.* FROM curated.official_members m JOIN curated.official_pointer p USING(version)"
        )
    }


def save_capture(conn, key, url, body, headers, verification=None, parser=None):
    state.migrate(conn)
    transform = state.transform_hash()
    capture_id = digest(
        key.encode()
        + b"\0"
        + body
        + b"\0"
        + (verification or b"")
        + b"\0"
        + transform.encode()
    )
    # Raw captures survive parser/verification failure, independently of promotion.
    receipt = capture_receipt(url, body, headers, [])
    conn.execute(
        "INSERT INTO curated.official_captures(capture_id,source_key,sha256,body,verification_body,receipt) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (capture_id, key, digest(body), body, verification, Jsonb(receipt)),
    )
    conn.execute(
        "UPDATE curated.official_captures SET transform_version=%s,transform_sha256=%s WHERE capture_id=%s AND transform_sha256 IS NULL",
        (state.TRANSFORM, transform, capture_id),
    )
    conn.execute(
        "UPDATE curated.official_inventory SET state='downloaded' WHERE source_key=%s",
        (key,),
    )
    try:
        records = parser(body)
        if verification is not None:
            verify_xls(body, verification)
        if not records:
            raise SourceRejected("EMPTY_PARSED_CAPTURE")
        receipt = capture_receipt(url, body, headers, records)
        previous = conn.execute(
            "SELECT c.receipt FROM curated.official_captures c JOIN curated.official_members m USING(capture_id) JOIN curated.official_pointer p ON p.version=m.version WHERE m.source_key=%s",
            (key,),
        ).fetchone()
        if previous:
            accepted = previous["receipt"]
            minimum = (
                accepted["rowCount"]
                if "/wrpt/" in url
                else int(accepted["rowCount"] * 0.8)
            )
            if len(records) < minimum or (receipt.get("coverageEnd") or "") < (
                accepted.get("coverageEnd") or ""
            ):
                raise SourceRejected("SOURCE_COMPLETENESS_OR_DATE_REGRESSION")
        receipt["transformVersion"] = state.TRANSFORM
        receipt["transformSha256"] = transform
        receipt["independentXlsVerified"] = verification is not None
        receipt["verificationSha256"] = digest(verification) if verification else None
        with conn.transaction():
            if not conn.execute(
                "SELECT valid FROM curated.official_captures WHERE capture_id=%s",
                (capture_id,),
            ).fetchone()["valid"]:
                for row_number, record in enumerate(records, 1):
                    record = dict(record, sourceRowNumber=row_number)
                    fact_id = digest(encoded(record))
                    record = dict(record, fact_id=fact_id, source=receipt)
                    names = record["names"]
                    conn.execute(
                        "INSERT INTO curated.official_records VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                        (
                            capture_id,
                            fact_id,
                            record["entity_id"],
                            search_name(names[0]),
                            search_name(names[1]) if len(names) > 1 else "",
                            Jsonb(record),
                        ),
                    )
                conn.execute(
                    "UPDATE curated.official_captures SET valid=true,receipt=%s WHERE capture_id=%s",
                    (Jsonb(receipt), capture_id),
                )
        return capture_id, records
    except Exception as exc:
        conn.execute(
            "UPDATE curated.official_inventory SET state='rejected' WHERE source_key=%s",
            (key,),
        )
        conn.execute(
            "UPDATE curated.official_captures SET receipt=receipt || %s WHERE capture_id=%s AND NOT valid",
            (Jsonb({"failureCode": type(exc).__name__, "failedAt": now()}), capture_id),
        )
        raise


def search_name(value):
    from .normalize import search_key

    return search_key(value)


_UNSET = object()


def promote(conn, members, coverage, expected_base=_UNSET):
    if not members:
        raise SourceRejected("EMPTY_PUBLICATION")
    identity = {"members": members, "coverage": coverage}
    version = "official-" + digest(encoded(identity))[:32]
    with conn.transaction():
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (state.LOCK,))
        if expected_base is not _UNSET and state.pointer(conn) != expected_base:
            raise SourceRejected("PUBLICATION_CONFLICT")
        valid = conn.execute(
            "SELECT count(*) AS n FROM curated.official_captures WHERE capture_id=ANY(%s) AND valid",
            (list(set(members.values())),),
        ).fetchone()["n"]
        if valid != len(set(members.values())):
            raise SourceRejected("UNVALIDATED_PUBLICATION")
        conn.execute(
            "INSERT INTO curated.official_versions VALUES(%s,%s) ON CONFLICT DO NOTHING",
            (version, Jsonb(coverage)),
        )
        for key, capture in members.items():
            conn.execute(
                "INSERT INTO curated.official_members VALUES(%s,%s,%s) ON CONFLICT DO NOTHING",
                (version, key, capture),
            )
        conn.execute(
            "INSERT INTO curated.official_pointer VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET version=EXCLUDED.version",
            (version,),
        )
    return version


def rollback(conn, version):
    with conn.transaction():
        if not conn.execute(
            "SELECT 1 FROM curated.official_versions WHERE version=%s", (version,)
        ).fetchone():
            raise SourceRejected("UNKNOWN_ROLLBACK_VERSION")
        conn.execute(
            "UPDATE curated.official_pointer SET version=%s WHERE singleton", (version,)
        )


def coverage(conn, members):
    rows = conn.execute(
        "SELECT r.record->>'kind' AS kind,count(*) AS rows,count(DISTINCT r.entity_id) AS entities FROM curated.official_records r WHERE capture_id=ANY(%s) GROUP BY r.record->>'kind'",
        (list(set(members.values())),),
    ).fetchall()
    links = [
        r["source_key"]
        for r in conn.execute(
            "SELECT source_key FROM curated.official_inventory WHERE present ORDER BY week,register"
        )
    ]
    weeks = sorted({u[-12:-4] for u in links})
    accepted = [w for w in weeks if all(u in members for u in links if u[-12:-4] == w)]
    cutoff = conn.execute(
        "SELECT max(r.record->>'coverageEnd') AS cutoff FROM curated.official_records r WHERE capture_id=ANY(%s) AND r.record->>'kind'='money_lender'",
        (list(set(members.values())),),
    ).fetchone()["cutoff"]
    counts = {r["kind"]: {"rows": r["rows"], "entities": r["entities"]} for r in rows}

    def end(w):
        return (
            (datetime.strptime(w, "%Y%m%d").date() + timedelta(days=6)).isoformat()
            if w
            else None
        )

    return {
        "view": "latest_observed",
        "limitations": LIMITATIONS,
        "recordCounts": counts,
        "discoveredWeeklyFiles": len(links),
        "acceptedWeeklyFiles": sum(u in members for u in links),
        "acceptedWeeks": accepted,
        "missingWeeks": [w for w in weeks if w not in accepted],
        "discoveredCoverageStart": (
            datetime.strptime(weeks[0], "%Y%m%d").date().isoformat() if weeks else None
        ),
        "discoveredCoverageEnd": end(weeks[-1] if weeks else None),
        "latestAcceptedCoverageEnd": end(accepted[-1] if accepted else None),
        "addressEntities": counts.get("address_observation", {}).get("entities", 0),
        "addressEligibleObservedEntities": counts.get("company_event", {}).get(
            "entities", 0
        ),
        "moneyLenderCutoff": cutoff,
        "schedule": {
            "kind": "systemd",
            "utc": "05:00 daily",
            "addressLimit": 20,
            "requestLimit": 48,
            "dailyCrRequestLimit": 500,
            "byteLimit": 67108864,
        },
    }


def collect_pair(conn, collector, week):
    entries = conn.execute(
        "SELECT * FROM curated.official_inventory WHERE present AND week=%s ORDER BY register",
        (week,),
    ).fetchall()
    if len(entries) != 2 or {r["register"] for r in entries} != {"local", "foreign"}:
        raise SourceRejected("INCOMPLETE_WEEK_PAIR")
    captures = {}
    for row in entries:
        body, headers = collector.get(row["source_key"])
        xls, _ = collector.get(row["verification_url"])
        cap, _ = save_capture(
            conn,
            row["source_key"],
            row["source_key"],
            body,
            headers,
            xls,
            lambda b: weekly(b, row["register"], week),
        )
        captures[row["source_key"]] = cap
    state.stage_group(conn, "week:" + week, captures)


def collect_lenders(conn, collector):
    captures, periods = {}, []
    for file in ML_FILES:
        url = ML_BASE + file + ".csv"
        body, headers = collector.get(url)
        xls, _ = collector.get(ML_BASE + file + ".xls")
        cap, records = save_capture(
            conn, url, url, body, headers, xls, lambda b: lenders(b, file)
        )
        captures[url] = cap
        periods.append(records[0]["coverageEnd"])
    if len(set(periods)) != 1:
        raise SourceRejected("MONEY_LENDER_REGISTER_PERIODS_DIFFER")
    state.stage_group(conn, "lenders", captures)


def collect_addresses(conn, collector, job_id, limit):
    state.seed_queue(conn)
    targets = conn.execute(
        "SELECT entity_id FROM curated.official_address_queue WHERE next_due<=now() ORDER BY next_due,last_success NULLS FIRST,entity_id LIMIT %s",
        (limit,),
    ).fetchall()
    failures = []
    for target in targets:
        entity = target["entity_id"]
        scope, brn = entity.split(":")[1:]
        url = f"https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/{scope}/search"
        params = {
            "query[0][key1]": "Brn",
            "query[0][key2]": "equal",
            "query[0][key3]": brn,
        }
        cap, outcome = None, "success"
        # Claim before the read; a crash leaves a bounded per-entity hold.
        conn.execute(
            "UPDATE curated.official_address_queue SET last_attempt=now(),next_due=now()+interval '1 day',outcome='unknown' WHERE entity_id=%s",
            (entity,),
        )
        try:
            body, headers = collector.get(url, params)
            previous = conn.execute(
                "SELECT c.capture_id,c.body,c.transform_sha256,q.latest_observation FROM curated.official_address_queue q LEFT JOIN curated.official_captures c ON c.capture_id=q.latest_capture WHERE q.entity_id=%s",
                (entity,),
            ).fetchone()
            parsed = address(body, scope, brn)
            unchanged = (
                previous
                and previous["capture_id"]
                and previous["transform_sha256"] == state.transform_hash()
                and address(bytes(previous["body"]), scope, brn) == parsed
            )
            if unchanged:
                cap = previous["capture_id"]
            else:
                cap, _ = save_capture(
                    conn,
                    "address:" + entity,
                    url,
                    body,
                    headers,
                    parser=lambda b: parsed,
                )
                occurrence_id = digest(encoded([entity, job_id, cap]))
                source_key = "address:" + entity + ":" + occurrence_id
                # Occurrences are separate from immutable raw-byte identities. A->B->A
                # is a new A occurrence, even when the original bytes can be reused.
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO curated.official_address_observations(observation_id,entity_id,source_key,capture_id,observed_at,previous_id) VALUES(%s,%s,%s,%s,now(),%s) ON CONFLICT DO NOTHING",
                        (
                            occurrence_id,
                            entity,
                            source_key,
                            cap,
                            previous["latest_observation"] if previous else None,
                        ),
                    )
                    state.stage_group(conn, "address:" + entity, {source_key: cap})
                    conn.execute(
                        "UPDATE curated.official_address_queue SET latest_observation=%s WHERE entity_id=%s",
                        (occurrence_id, entity),
                    )
        except (SourceRejected, httpx.HTTPError) as exc:
            outcome = (
                str(exc)
                if isinstance(exc, SourceRejected)
                else "SOURCE_NETWORK_FAILURE"
            )
            failures.append({"entityId": entity, "code": outcome})
        with conn.transaction():
            conn.execute(
                "INSERT INTO curated.official_address_checks(job_id,entity_id,outcome,capture_id) VALUES(%s,%s,%s,%s)",
                (job_id, entity, outcome, cap),
            )
            conn.execute(
                "UPDATE curated.official_address_queue SET outcome=%s,last_success=CASE WHEN %s::text IS NOT NULL THEN now() ELSE last_success END,latest_capture=coalesce(%s,latest_capture),next_due=now()+CASE WHEN %s::text IS NOT NULL THEN interval '90 days' ELSE interval '7 days' END WHERE entity_id=%s",
                (outcome, cap, cap, cap, entity),
            )
        if outcome in {
            "SOURCE_HTTP_429",
            "SOURCE_HTTP_503",
            "SOURCE_HOLD",
            "DAILY_SOURCE_BUDGET",
            "RUN_REQUEST_OR_TIME_BUDGET",
            "RUN_BYTE_OR_TIME_BUDGET",
        }:
            break
    conn.execute(
        "INSERT INTO curated.official_source_state(family,checked_at,state) VALUES('addresses',now(),%s) ON CONFLICT(family) DO UPDATE SET checked_at=now(),state=EXCLUDED.state",
        (
            Jsonb(
                {
                    "status": "partial" if failures else "success",
                    "selected": len(targets),
                    "failures": len(failures),
                }
            ),
        ),
    )
    return failures


def publish_staged(conn):
    base = state.pointer(conn)
    before = current_members(conn)
    members = dict(before)
    # Preserve existing history keys. Old single-address members remain immutable.
    for row in conn.execute(
        "SELECT source_key,capture_id FROM curated.official_staged"
    ):
        members[row["source_key"]] = row["capture_id"]
    if members == before:
        return base, False
    # One public promotion per UTC date, including the original deployed runner.
    today = conn.execute(
        "SELECT 1 FROM curated.official_versions WHERE created_at::date=(now() AT TIME ZONE 'UTC')::date LIMIT 1"
    ).fetchone()
    if today:
        return base, False
    version = promote(conn, members, coverage(conn, members), expected_base=base)
    return version, True


def run(
    dsn, collector=None, mode="freshness", scheduled_for=None, pairs=4, address_limit=20
):
    if mode not in {
        "freshness",
        "backfill",
        "addresses",
        "publish",
        "plan",
        "verify-run",
    }:
        raise ValueError("Unknown maintenance mode")
    if not 1 <= pairs <= 4 or not 0 <= address_limit <= 100:
        raise ValueError("Batch bounds exceeded")
    with connect(dsn, autocommit=True, row_factory=dict_row) as conn:
        state.migrate(conn)
        if mode == "plan":
            return state.plan(conn)
        if mode == "verify-run":
            return verify_run(conn, scheduled_for)
        if not conn.execute(
            "SELECT pg_try_advisory_lock(%s) AS locked", (state.LOCK,)
        ).fetchone()["locked"]:
            return {"status": "busy"}
        if (
            mode == "backfill"
            and conn.execute(
                "SELECT count(*) AS n FROM curated.official_jobs WHERE operation='backfill' AND started_at>=(now() AT TIME ZONE 'UTC')::date"
            ).fetchone()["n"]
            >= 12
        ):
            return {"status": "daily_batch_limit"}
        occurrence = scheduled_for or now()
        job_id = state.begin_job(conn, mode, occurrence)
        if not job_id:
            return {"status": "duplicate", "scheduledFor": occurrence}
        collector = collector or Collector(
            conn, 16 if mode == "backfill" else 120 if mode == "addresses" else 48
        )
        collector.conn = conn
        errors, changed = [], False
        started = time.monotonic()
        db_before = conn.execute(
            "SELECT pg_database_size(current_database()) AS bytes"
        ).fetchone()["bytes"]
        try:
            conn.execute(
                "INSERT INTO curated.official_runs(run_id,status) VALUES(%s,'running')",
                (job_id,),
            )
            if mode == "freshness":
                try:
                    body, _ = collector.get(CATALOGUE)
                    state.inventory(conn, discover(body), digest(body))
                except (SourceRejected, httpx.HTTPError) as exc:
                    errors.append(error("inventory", exc))
                weeks = conn.execute(
                    "SELECT DISTINCT week FROM curated.official_inventory WHERE present ORDER BY week DESC LIMIT 2"
                ).fetchall()
                for row in weeks:
                    try:
                        state.collect_group(
                            conn,
                            "week:" + row["week"],
                            occurrence,
                            lambda: collect_pair(conn, collector, row["week"]),
                        )
                    except (SourceRejected, httpx.HTTPError) as exc:
                        errors.append(error("week:" + row["week"], exc))
                try:
                    state.collect_group(
                        conn,
                        "lenders",
                        occurrence,
                        lambda: collect_lenders(conn, collector),
                    )
                except (SourceRejected, httpx.HTTPError) as exc:
                    errors.append(error("lenders", exc))
            if mode == "backfill":
                inv = conn.execute(
                    "SELECT checked_at<now()-interval '36 hours' AS stale FROM curated.official_source_state WHERE family='inventory'"
                ).fetchone()
                if not inv or inv["stale"]:
                    raise SourceRejected("INVENTORY_REFRESH_REQUIRED")
                pending = [
                    r["week"]
                    for r in state.plan(conn)["weeks"]
                    if r["published"] < 2 and r["staged"] < 2
                ][:pairs]
                for week in pending:
                    try:
                        state.collect_group(
                            conn,
                            "week:" + week,
                            occurrence,
                            lambda: collect_pair(conn, collector, week),
                        )
                    except (SourceRejected, httpx.HTTPError) as exc:
                        errors.append(error("week:" + week, exc))
                        if str(exc) in {
                            "SOURCE_HTTP_429",
                            "SOURCE_HTTP_503",
                            "SOURCE_HOLD",
                            "DAILY_SOURCE_BUDGET",
                        }:
                            break
            if mode in {"freshness", "addresses"}:
                errors.extend(collect_addresses(conn, collector, job_id, address_limit))
            with conn.transaction():
                version = state.pointer(conn)
                if mode in {"freshness", "publish"}:
                    version, changed = publish_staged(conn)
                receipt = {
                    "status": "partial" if errors else "success",
                    "jobId": job_id,
                    "operation": mode,
                    "scheduledFor": occurrence,
                    "version": version,
                    "published": changed,
                    "publicationStatus": (
                        "published"
                        if changed
                        else (
                            "unchanged_or_daily_staged"
                            if mode in {"freshness", "publish"}
                            else "staged_only"
                        )
                    ),
                    "backupStatus": "not_observed",
                    "requests": collector.requests,
                    "bytes": collector.bytes,
                    "durationSeconds": round(time.monotonic() - started, 3),
                    "maxRssKiB": int(
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                        / (1024 if sys.platform == "darwin" else 1)
                    ),
                    "databaseGrowthBytes": conn.execute(
                        "SELECT pg_database_size(current_database()) AS bytes"
                    ).fetchone()["bytes"]
                    - db_before,
                    "errors": errors,
                    "sourceChecks": collector.checks,
                    "inventory": state.plan(conn),
                }
                state.finish_job(conn, job_id, receipt)
        except Exception as exc:
            receipt = {
                "status": "failed",
                "jobId": job_id,
                "operation": mode,
                "errors": [error(mode, exc)],
                "acceptedRetained": True,
                "requests": collector.requests,
                "bytes": collector.bytes,
                "sourceChecks": collector.checks,
            }
        finally:
            collector.close()
        if receipt["status"] == "failed":
            with conn.transaction():
                state.finish_job(conn, job_id, receipt)
        return receipt


def error(group, exc):
    return {
        "group": group,
        "code": (
            str(exc) if isinstance(exc, SourceRejected) else "SOURCE_OR_STORAGE_FAILURE"
        ),
        "errorType": type(exc).__name__,
    }


def verify_run(conn, scheduled_for):
    if not scheduled_for:
        raise ValueError("Verifier requires the expected scheduled occurrence")
    row = conn.execute(
        "SELECT job_id,status,collection_status,publication_status,backup_status,started_at,finished_at FROM curated.official_jobs WHERE operation='freshness' AND scheduled_for=%s",
        (scheduled_for,),
    ).fetchone()
    return {
        "status": "missed" if not row else row["status"],
        "scheduledFor": scheduled_for,
        "job": row,
    }


def main():
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode",
        nargs="?",
        default="freshness",
        choices=["freshness", "backfill", "addresses", "publish", "verify-run", "plan"],
    )
    parser.add_argument("--rollback")
    parser.add_argument("--scheduled-for")
    parser.add_argument("--pairs", type=int, default=4)
    parser.add_argument("--address-limit", type=int, default=20)
    args = parser.parse_args()
    dsn = os.environ["CURATED_DSN"]
    if args.rollback:
        with connect(dsn, autocommit=True, row_factory=dict_row) as conn:
            if not conn.execute(
                "SELECT pg_try_advisory_lock(%s) AS locked", (state.LOCK,)
            ).fetchone()["locked"]:
                raise SystemExit("Official writer busy")
            rollback(conn, args.rollback)
        return
    receipt = run(
        dsn,
        mode=args.mode,
        scheduled_for=args.scheduled_for,
        pairs=args.pairs,
        address_limit=args.address_limit,
    )
    print(json.dumps(receipt, default=str))
    if receipt.get("status") not in {None, "success", "duplicate"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
