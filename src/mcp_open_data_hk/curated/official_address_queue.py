"""Fair bounded address cohorts; quotas remain owned by existing admission gates."""

from collections import deque
from math import ceil

SLOTS = (
    "priority",
    "refresh",
    "initial",
    "refresh",
    "retry",
    "priority",
    "refresh",
    "initial",
    "refresh",
    "initial",
)


def interleave(cohorts, limit, offset=0):
    queues = {k: deque(v) for k, v in cohorts.items()}
    selected = []
    step = offset
    while len(selected) < limit and any(queues.values()):
        cohort = SLOTS[step % len(SLOTS)]
        step += 1
        if not queues.get(cohort):
            continue
        selected.append(
            dict(queues[cohort].popleft(), cohort=cohort, next_offset=step % len(SLOTS))
        )
    return selected


def targets(conn, limit, at=None):
    if limit <= 0:
        return []
    at = at or conn.execute("SELECT now() AS stamp").fetchone()["stamp"]
    clauses = {
        "priority": "priority",
        "refresh": "NOT priority AND last_success IS NOT NULL",
        "initial": "NOT priority AND last_success IS NULL AND last_attempt IS NULL",
        "retry": "NOT priority AND last_success IS NULL AND last_attempt IS NOT NULL",
    }
    cohorts = {
        name: conn.execute(
            "SELECT entity_id FROM curated.official_address_queue WHERE next_due<=%s AND "
            + clause
            + " ORDER BY last_attempt NULLS FIRST,next_due,entity_id LIMIT %s",
            (at, limit),
        ).fetchall()
        for name, clause in clauses.items()
    }
    scheduler = conn.execute(
        "SELECT state FROM curated.official_source_state WHERE family='address_scheduler'"
    ).fetchone()
    return interleave(
        cohorts, limit, scheduler["state"].get("offset", 0) if scheduler else 0
    )


def retry(outcome):
    if outcome == "success":
        return "observed", 90
    if outcome == "SOURCE_NO_MATCH":
        return "source_no_match", 30
    if outcome == "SOURCE_NETWORK_FAILURE" or outcome in {
        "SOURCE_HTTP_429",
        "SOURCE_HTTP_503",
        "SOURCE_HTTP_502",
        "SOURCE_HTTP_504",
        "SOURCE_HOLD",
        "DAILY_SOURCE_BUDGET",
        "RUN_REQUEST_OR_TIME_BUDGET",
        "RUN_BYTE_OR_TIME_BUDGET",
    }:
        return "transient_or_budget", 1
    if outcome in {
        "INVALID_ADDRESS_JSON",
        "ADDRESS_NO_MATCH_OR_PARTIAL",
        "ADDRESS_IDENTITY_OR_SCHEMA_CHANGED",
        "ADDRESS_NAME_MISSING",
        "INVALID_SOURCE_IDENTIFIER",
        "INVALID_SOURCE_DATE",
    }:
        return "input_or_schema", 7
    return "unresolved", 7


def capacity(eligible, daily_limit):
    return {
        "eligible": eligible,
        "dailyAttemptLimit": daily_limit,
        "sharedCrDailyRequestLimit": 500,
        "fullPassMinimumDaysAtCurrentCap": ceil(eligible / daily_limit),
        "wholeSubset90DayCycleFeasible": eligible <= daily_limit * 90,
        "successfulReadsPerDayNeededFor90Days": ceil(eligible / 90),
        "guaranteedWholeSubsetCycleDays": None,
        "refreshTargetDays": 90,
        "priorityCohortCapacityAt90Days": int(daily_limit * 0.2 * 90),
        "targetScope": "observed_and_explicit_priority_cohorts; capacity-dependent, not a whole-subset guarantee",
        "saturatedShares": {
            "priority": 0.2,
            "refresh": 0.4,
            "initial": 0.3,
            "retry": 0.1,
        },
        "idleShareBorrowing": True,
        "basis": "optimistic lower bound; failures, holds and other CR reads reduce throughput",
    }


def main():
    import argparse
    import json
    import os
    import re
    from psycopg.rows import dict_row
    from .build import connect
    from .official import SourceRejected
    from .official_state import LOCK, migrate

    parser = argparse.ArgumentParser(
        description="Track an exact existing company for the priority address cohort"
    )
    parser.add_argument("entity", help="cr:local:NNNNNNNN or cr:foreign:NNNNNNNN")
    parser.add_argument("--untrack", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"cr:(local|foreign):[0-9]{8}", args.entity):
        parser.error("Use an exact namespaced eight-digit BRN")
    with connect(
        os.environ["CURATED_DSN"], autocommit=True, row_factory=dict_row
    ) as conn:
        # The same writer lock as collection/publication; never steal a live owner.
        with conn.transaction():
            if not conn.execute(
                "SELECT pg_try_advisory_xact_lock(%s) AS acquired", (LOCK,)
            ).fetchone()["acquired"]:
                raise SourceRejected("WRITER_BUSY")
            migrate(conn)
            changed = conn.execute(
                "UPDATE curated.official_address_queue SET priority=%s WHERE entity_id=%s RETURNING entity_id,priority",
                (not args.untrack, args.entity),
            ).fetchone()
            if not changed:
                raise SourceRejected("IDENTITY_OUTSIDE_OBSERVED_COHORT")
            print(json.dumps(changed))


if __name__ == "__main__":
    main()
