"""Bounded source job; public queries never dispatch HKEX requests."""

import argparse
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from . import store
from .parser import (
    BASE,
    MENU,
    MAX_BODY,
    parse_menu,
    parse_report,
    report_path,
    TRANSFORM,
)

PATH = re.compile(r"/di/summary/(?:NSMSumMenu\.htm|DSM[0-9]{8}C[1-4]\.htm)")


class Transport:
    def __init__(self):
        self.client = httpx.Client(
            timeout=20,
            follow_redirects=False,
            trust_env=False,
            headers={
                "User-Agent": "mcp.hk disclosure updater (+https://mcp.hk)",
                "Accept": "text/html",
            },
        )

    def get(self, path, headers):
        if not PATH.fullmatch(path):
            raise ValueError("SOURCE_ROUTE_NOT_ALLOWED")
        started = time.monotonic()
        with self.client.stream("GET", BASE + path, headers=headers) as r:
            body = bytearray()
            for chunk in r.iter_bytes():
                if time.monotonic() - started > 20:
                    raise httpx.ReadTimeout("Source response wall-time bound")
                if len(body) + len(chunk) > MAX_BODY:
                    raise ValueError("SOURCE_BODY_LIMIT")
                body.extend(chunk)
            return r.status_code, bytes(body), dict(r.headers)

    def close(self):
        self.client.close()


def fetch(c, run, path, transport, deadline, headers=None):
    row = c.execute(
        "SELECT last_read_at FROM hkex_daily.control WHERE singleton"
    ).fetchone()
    if row["last_read_at"]:
        delay = (
            store.MIN_INTERVAL
            - (datetime.now(timezone.utc) - row["last_read_at"]).total_seconds()
        )
        if delay > store.MIN_INTERVAL + 1:
            raise ValueError("SOURCE_CLOCK_SKEW")
        if delay > 0:
            time.sleep(delay + 0.02)
    if time.monotonic() >= deadline:
        raise ValueError("SOURCE_RUN_DEADLINE")
    key = store.reserve(c, run, path)
    try:
        status, body, response_headers = transport.get(path, headers or {})
    except httpx.HTTPError:
        # A caught read-only GET failure is charged at the full reserved bound;
        # an actual process crash leaves 'unknown' and requires reconciliation.
        with c.transaction():
            c.execute(
                "UPDATE hkex_daily.requests SET state='transport_failed' WHERE id=%s",
                (key,),
            )
            c.execute(
                "UPDATE hkex_daily.control SET hold_code='SOURCE_TRANSPORT_HOLD',hold_until=now()+interval '1 hour' WHERE singleton"
            )
        raise ValueError("SOURCE_TRANSPORT_HOLD") from None
    code = store.settle(c, key, status, body, response_headers.get("retry-after"))
    if code:
        raise ValueError(code)
    if status == 200 and re.search(
        rb"access denied|request blocked|verify (?:that )?you are (?:a )?human|captcha challenge",
        body,
        re.I,
    ):
        c.execute(
            "UPDATE hkex_daily.control SET hold_code='SOURCE_ACCESS_CHALLENGE',hold_until=NULL WHERE singleton"
        )
        raise ValueError("SOURCE_ACCESS_CHALLENGE")
    if status == 200 and not response_headers.get(
        "content-type", ""
    ).lower().startswith(("text/html", "application/xhtml+xml")):
        raise ValueError("SOURCE_CONTENT_TYPE_CHANGED")
    return status, body, response_headers


def collect(
    dsn,
    *,
    transport=None,
    scheduled_for=None,
    provenance="manual",
    today=None,
    lookback=7,
):
    if provenance not in {"manual", "timer"} or not 1 <= lookback <= 7:
        raise ValueError("INVALID_JOB_SCOPE")
    today = today or datetime.now(ZoneInfo("Asia/Hong_Kong")).date()
    run = uuid.uuid4().hex
    owned = transport is None
    transport = transport or Transport()
    try:
        with store.writer(dsn) as c:
            pending = c.execute(
                "SELECT version FROM hkex_daily.versions WHERE state IN ('staged','qualified') ORDER BY created_at LIMIT 1"
            ).fetchone()
            if pending:
                return {"state": "pending_recovery", "version": pending["version"]}
            c.execute(
                "INSERT INTO hkex_daily.runs(id,scheduled_for,provenance) VALUES(%s,%s,%s)",
                (run, scheduled_for, provenance),
            )
            try:
                deadline = time.monotonic() + 600
                status, body, _ = fetch(c, run, MENU, transport, deadline)
                if status != 200:
                    raise ValueError("SUMMARY_MENU_UNAVAILABLE")
                latest = parse_menu(body)
                if not date(2017, 7, 3) <= latest <= today:
                    raise ValueError("SUMMARY_MENU_DATE_INVALID")
                selected, missing = {}, set()
                prior = c.execute(
                    "SELECT 1 FROM hkex_daily.runs WHERE id<>%s AND started_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AND state IN ('staged','unchanged') LIMIT 1",
                    (run,),
                ).fetchone()
                days = [
                    latest - timedelta(days=i) for i in range(1 if prior else lookback)
                ]
                for day in days:
                    for category in (1, 2, 3, 4):
                        cached = c.execute(
                            "SELECT r.* FROM hkex_daily.reports r LEFT JOIN hkex_daily.version_reports p ON p.report_sha256=r.sha256 AND p.version=(SELECT accepted_version FROM hkex_daily.control WHERE singleton) WHERE r.day=%s AND r.category=%s AND r.transform_sha256=%s ORDER BY (p.version IS NOT NULL) DESC,r.observed_at DESC LIMIT 1",
                            (day, category, TRANSFORM),
                        ).fetchone()
                        # Force complete byte reconciliation at least daily. Other
                        # checks may reuse a source-validated 304 for the same path.
                        headers = (
                            {"If-None-Match": cached["etag"]}
                            if prior and cached and cached["etag"]
                            else {}
                        )
                        status, body, response_headers = fetch(
                            c,
                            run,
                            report_path(day, category),
                            transport,
                            deadline,
                            headers,
                        )
                        if status == 304:
                            if not cached or not headers:
                                raise ValueError("SUMMARY_304_WITHOUT_VALIDATED_REPORT")
                            selected[(day.isoformat(), category)] = cached["sha256"]
                        elif status == 200:
                            try:
                                report = parse_report(body, day, category)
                            except ValueError:
                                if day == latest:
                                    raise
                                # Older unavailable/unqualified pages are explicit
                                # coverage gaps; they do not prevent publishing
                                # a fully validated newer daily summary.
                                missing.add(report_path(day, category))
                                continue
                            selected[(day.isoformat(), category)] = store.save_report(
                                c, report, response_headers
                            )
                        elif status == 404 and day != latest:
                            missing.add(report_path(day, category))
                        else:
                            raise ValueError("SUMMARY_REPORT_UNAVAILABLE")
                version = store.stage(c, run, latest, selected, missing)
                state = "staged" if version else "unchanged"
                with c.transaction():
                    c.execute(
                        "UPDATE hkex_daily.runs SET state=%s,latest_source_date=%s,finished_at=now(),request_count=(SELECT count(*) FROM hkex_daily.requests WHERE run_id=%s),received_bytes=(SELECT COALESCE(sum(COALESCE(received_bytes,reserved_bytes)),0) FROM hkex_daily.requests WHERE run_id=%s) WHERE id=%s",
                        (state, latest, run, run, run),
                    )
                    c.execute(
                        "UPDATE hkex_daily.control SET last_checked=now(),last_success=now(),hold_code=NULL,hold_until=NULL WHERE singleton"
                    )
                return {
                    "state": state,
                    "run": run,
                    "version": version,
                    "latestSummaryDate": latest.isoformat(),
                }
            except Exception as exc:
                code = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    and str(exc).isupper()
                    and len(str(exc)) < 90
                    else "SOURCE_JOB_FAILED"
                )
                with c.transaction():
                    c.execute(
                        "UPDATE hkex_daily.runs SET state='failed',code=%s,finished_at=now(),request_count=(SELECT count(*) FROM hkex_daily.requests WHERE run_id=%s),received_bytes=(SELECT COALESCE(sum(COALESCE(received_bytes,reserved_bytes)),0) FROM hkex_daily.requests WHERE run_id=%s) WHERE id=%s",
                        (code, run, run, run),
                    )
                    c.execute(
                        "UPDATE hkex_daily.control SET last_checked=now() WHERE singleton"
                    )
                    if any(
                        x in code
                        for x in (
                            "SCHEMA",
                            "MISMATCH",
                            "RECONCILIATION",
                            "UNRECOGNIZED",
                            "LIMIT",
                            "DECIMAL",
                            "UNESTABLISHED",
                            "CHANGED",
                            "IDENTITY",
                            "EMPTY_",
                            "COLUMNS",
                        )
                    ):
                        c.execute(
                            "UPDATE hkex_daily.control SET hold_code=%s,hold_until=NULL WHERE singleton",
                            (code,),
                        )
                return {"state": "failed", "run": run, "code": code}
    finally:
        if owned:
            transport.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "command",
        choices=[
            "collect",
            "fingerprint",
            "qualify",
            "publish",
            "migrate",
            "grant-reader",
            "state",
        ],
    )
    p.add_argument("--version")
    p.add_argument("--sha256")
    p.add_argument("--restore-database")
    p.add_argument("--scheduled-for")
    p.add_argument("--provenance", choices=["manual", "timer"], default="manual")
    p.add_argument("--role")
    args = p.parse_args()
    dsn = os.environ["HKEX_DAILY_DSN"]
    if args.command == "collect":
        result = collect(
            dsn, scheduled_for=args.scheduled_for, provenance=args.provenance
        )
    elif args.command == "fingerprint":
        if args.restore_database:
            from psycopg.conninfo import conninfo_to_dict, make_conninfo

            if not re.fullmatch(
                r"hkex_daily_restore_[a-z0-9_]{1,50}", args.restore_database
            ):
                p.error("Invalid source-specific restored database")
            dsn = make_conninfo(
                **dict(conninfo_to_dict(dsn), dbname=args.restore_database)
            )
        result = store.snapshot(dsn)
    elif args.command == "state":
        from ..build import connect
        from psycopg.rows import dict_row

        with connect(dsn, row_factory=dict_row) as c:
            control = c.execute(
                "SELECT accepted_version,accepted_revision FROM hkex_daily.control WHERE singleton"
            ).fetchone()
            version = (
                c.execute(
                    "SELECT version,state,base_version,published_revision FROM hkex_daily.versions WHERE version=%s",
                    (args.version,),
                ).fetchone()
                if args.version
                else None
            )
            result = {"control": control, "version": version}
    elif args.command == "migrate":
        store.migrate(dsn)
        result = {"migrated": True}
    elif args.command == "grant-reader":
        store.grant_reader(dsn, args.role)
        result = {"granted": True}
    elif args.command == "qualify":
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        if not args.restore_database or not re.fullmatch(
            r"hkex_daily_restore_[a-z0-9_]{1,50}", args.restore_database
        ):
            p.error("Use an independently restored source-specific database")
        config = conninfo_to_dict(dsn)
        result = store.qualify(
            dsn,
            make_conninfo(**dict(config, dbname=args.restore_database)),
            args.version,
            args.sha256,
        )
    else:
        result = {"published": store.publish(dsn, args.version)}
    print(json.dumps(result, ensure_ascii=False, default=str))
    if result.get("state") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
