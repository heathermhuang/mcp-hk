"""One bounded ordinary-scheduler run; owner credentials never reach readers."""

import argparse
import os
import time
import uuid

import httpx
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .build import connect
from .official import (
    CATALOGUE,
    DDL,
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
    def __init__(self):
        self.requests = 0
        self.bytes = 0
        self.checks = []
        self.deadline = time.monotonic() + 780
        self.client = httpx.Client(timeout=30, follow_redirects=False, trust_env=False)

    def get(self, url, params=None):
        self.requests += 1
        if self.requests > 48 or time.monotonic() > self.deadline:
            raise SourceRejected("RUN_REQUEST_OR_TIME_BUDGET")
        with self.client.stream("GET", url, params=params) as response:
            check = {
                "sourceUrl": str(response.url),
                "checkedAt": now(),
                "httpStatus": response.status_code,
                "sourceLastModified": response.headers.get("last-modified"),
            }
            self.checks.append(check)
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
    capture_id = digest(key.encode() + b"\0" + body + b"\0" + (verification or b""))
    # Raw captures survive parser/verification failure, independently of promotion.
    receipt = capture_receipt(url, body, headers, [])
    conn.execute(
        "INSERT INTO curated.official_captures(capture_id,source_key,sha256,body,verification_body,receipt) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (capture_id, key, digest(body), body, verification, Jsonb(receipt)),
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
            "UPDATE curated.official_captures SET receipt=receipt || %s WHERE capture_id=%s AND NOT valid",
            (Jsonb({"failureCode": type(exc).__name__, "failedAt": now()}), capture_id),
        )
        raise


def search_name(value):
    from .normalize import search_key

    return search_key(value)


def promote(conn, members, coverage):
    if not members:
        raise SourceRejected("EMPTY_PUBLICATION")
    identity = {"members": members, "coverage": coverage}
    version = "official-" + digest(encoded(identity))[:32]
    with conn.transaction():
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


def run(dsn, collector=None):
    collector = collector or Collector()
    run_id = uuid.uuid4().hex
    try:
        with connect(dsn, autocommit=True, row_factory=dict_row) as conn:
            conn.execute(DDL)
            if not conn.execute(
                "SELECT pg_try_advisory_lock(68002406) AS locked"
            ).fetchone()["locked"]:
                return {"status": "busy"}
            conn.execute(
                "INSERT INTO curated.official_runs(run_id,status) VALUES(%s,'running')",
                (run_id,),
            )
            try:
                before = current_members(conn)
                members = dict(before)
                catalogue, _ = collector.get(CATALOGUE)
                links = discover(catalogue)
                if any(
                    k.startswith("https://www.cr.gov.hk/docs/wrpt/") and k not in links
                    for k in before
                ):
                    raise SourceRejected("CATALOGUE_LOST_ACCEPTED_RESOURCES")
                weeks = sorted({u[-12:-4] for u in links})
                selected = weeks[-2:]
                older = [
                    w
                    for w in weeks[:-2]
                    if any(u not in members for u in links if w in u)
                ]
                if older:
                    selected.append(older[0])
                tracked = {}
                for url in sorted(u for u in links if u[-12:-4] in selected):
                    body, headers = collector.get(url)
                    xls, _ = collector.get(url[:-3] + "xls")
                    scope = "local" if "RNC063L_" in url else "foreign"
                    capture, records = save_capture(
                        conn,
                        url,
                        url,
                        body,
                        headers,
                        xls,
                        lambda b: weekly(b, scope, url[-12:-4]),
                    )
                    members[url] = capture
                    for row in records:
                        tracked[row["entity_id"]] = row["identifier"]["value"]
                periods = []
                for file in ML_FILES:
                    url = ML_BASE + file + ".csv"
                    body, headers = collector.get(url)
                    xls, _ = collector.get(ML_BASE + file + ".xls")
                    capture, records = save_capture(
                        conn, url, url, body, headers, xls, lambda b: lenders(b, file)
                    )
                    periods.append(records[0]["coverageEnd"])
                    members[url] = capture
                if len(set(periods)) != 1:
                    raise SourceRejected("MONEY_LENDER_REGISTER_PERIODS_DIFFER")
                # Deterministic fair rotation of already observed identities, never an ID sweep.
                existing = conn.execute(
                    "SELECT DISTINCT r.entity_id FROM curated.official_records r JOIN curated.official_members m USING(capture_id) JOIN curated.official_pointer p ON p.version=m.version WHERE r.entity_id LIKE 'cr:local:%%' OR r.entity_id LIKE 'cr:foreign:%%' ORDER BY r.entity_id"
                ).fetchall()
                for row in existing:
                    tracked[row["entity_id"]] = row["entity_id"].split(":")[-1]
                ordered = sorted(tracked)
                previous = conn.execute(
                    "SELECT receipt FROM curated.official_runs WHERE status IN ('success','success_with_address_gaps') ORDER BY finished_at DESC LIMIT 1"
                ).fetchone()
                offset = (
                    previous["receipt"].get("addressOffset", 0) if previous else 0
                ) % max(1, len(ordered))
                targets = (ordered[offset:] + ordered[:offset])[:20]
                address_gaps = []
                for entity in targets:
                    scope, brn = entity.split(":")[1:]
                    url = f"https://data.cr.gov.hk/cr/api/api/v1/api_builder/json/{scope}/search"
                    params = {
                        "query[0][key1]": "Brn",
                        "query[0][key2]": "equal",
                        "query[0][key3]": brn,
                    }
                    key = "address:" + entity
                    try:
                        body, headers = collector.get(url, params)
                        capture, _ = save_capture(
                            conn,
                            key,
                            str(httpx.URL(url, params=params)),
                            body,
                            headers,
                            parser=lambda b: address(b, scope, brn),
                        )
                    except (SourceRejected, httpx.HTTPError) as exc:
                        address_gaps.append(
                            {
                                "entityId": entity,
                                "code": (
                                    str(exc)
                                    if isinstance(exc, SourceRejected)
                                    else "SOURCE_NETWORK_FAILURE"
                                ),
                                "acceptedObservationRetained": key in before,
                            }
                        )
                        if str(exc) in {"SOURCE_HTTP_429", "SOURCE_HTTP_503"}:
                            break
                        continue
                    members[key] = capture
                accepted_weeks = sorted({u[-12:-4] for u in links if u in members})
                counts = conn.execute(
                    "SELECT r.record->>'kind' AS kind,count(*) AS rows,count(DISTINCT r.entity_id) AS entities FROM curated.official_records r WHERE capture_id=ANY(%s) GROUP BY r.record->>'kind'",
                    (list(set(members.values())),),
                ).fetchall()
                coverage = {
                    "recordCounts": {
                        r["kind"]: {"rows": r["rows"], "entities": r["entities"]}
                        for r in counts
                    },
                    "view": "latest_observed",
                    "limitations": LIMITATIONS,
                    "discoveredWeeklyFiles": len(links),
                    "acceptedWeeklyFiles": sum(u in members for u in links),
                    "acceptedWeeks": accepted_weeks,
                    "missingWeeks": [
                        w
                        for w in weeks
                        if any(u not in members for u in links if w in u)
                    ],
                    "discoveredCoverageStart": weeks[0],
                    "discoveredCoverageEnd": weeks[-1],
                    "addressEntities": sum(k.startswith("address:") for k in members),
                    "addressEligibleObservedEntities": len(tracked),
                    "moneyLenderCutoff": periods[0],
                    "schedule": {
                        "kind": "systemd",
                        "utc": "05:00 daily",
                        "addressLimit": 20,
                        "requestLimit": 48,
                        "byteLimit": 67108864,
                    },
                    "catalogueSha256": digest(catalogue),
                }
                with conn.transaction():
                    version = promote(conn, members, coverage)
                    receipt = {
                        "version": version,
                        "status": (
                            "success_with_address_gaps" if address_gaps else "success"
                        ),
                        "addressFailures": address_gaps,
                        "sourceChecks": getattr(collector, "checks", []),
                        "requests": collector.requests,
                        "bytes": collector.bytes,
                        "changedSources": sum(
                            before.get(k) != v for k, v in members.items()
                        ),
                        "addressOffset": offset + len(targets),
                        "coverage": coverage,
                    }
                    conn.execute(
                        "UPDATE curated.official_runs SET status=%s,finished_at=now(),receipt=%s WHERE run_id=%s",
                        (receipt["status"], Jsonb(receipt), run_id),
                    )
                return receipt
            except Exception as exc:
                # Exception text can contain provider bodies or DSNs; retain only a fixed code/type.
                receipt = {
                    "status": "failed",
                    "errorType": type(exc).__name__,
                    "errorCode": (
                        str(exc)
                        if isinstance(exc, SourceRejected)
                        else "SOURCE_OR_STORAGE_FAILURE"
                    ),
                    "sourceChecks": getattr(collector, "checks", []),
                    "requests": collector.requests,
                    "bytes": collector.bytes,
                    "acceptedRetained": True,
                }
                conn.execute(
                    "UPDATE curated.official_runs SET status='failed',finished_at=now(),receipt=%s WHERE run_id=%s",
                    (Jsonb(receipt), run_id),
                )
                return receipt
    finally:
        collector.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rollback")
    args = parser.parse_args()
    dsn = os.environ["CURATED_DSN"]
    if args.rollback:
        with connect(dsn, autocommit=True, row_factory=dict_row) as conn:
            if not conn.execute(
                "SELECT pg_try_advisory_lock(68002406) AS locked"
            ).fetchone()["locked"]:
                raise SystemExit("Official writer busy")
            rollback(conn, args.rollback)
        return
    import json

    receipt = run(dsn)
    print(json.dumps(receipt))
    if receipt["status"] not in {"success", "success_with_address_gaps"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
