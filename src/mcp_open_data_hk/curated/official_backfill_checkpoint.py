"""Bounded inventory comparison for ordinary catch-up and recovery milestones."""

import json
import os

from psycopg.rows import dict_row

from .build import connect
from .official_state import plan


def checkpoint(conn):
    inventory = plan(conn)
    rows = conn.execute(
        "SELECT i.week,count(*) AS n FROM curated.official_inventory i LEFT JOIN curated.official_staged s USING(source_key) LEFT JOIN curated.official_pointer p ON true LEFT JOIN curated.official_members m ON m.version=p.version AND m.source_key=i.source_key WHERE i.present AND (s.capture_id IS NOT NULL OR m.capture_id IS NOT NULL) GROUP BY i.week HAVING count(*)=2"
    ).fetchall()
    total = len(inventory["weeks"])
    qualified = len(rows)
    prior = conn.execute(
        "SELECT state FROM curated.official_source_state WHERE family='performance'"
    ).fetchone()
    tested = (prior["state"].get("qualifiedWeekPairs") or 0) if prior else 0
    milestone = next(
        (
            n
            for n in [10, 50, 100]
            if total and qualified * 100 >= total * n and tested * 100 < total * n
        ),
        None,
    )
    return {
        "pendingPairs": inventory["pendingPairs"],
        "qualifiedPairs": qualified,
        "inventoryPairs": total,
        "performanceQualifiedPairs": tested,
        "milestoneNeeded": milestone,
        "noOp": inventory["pendingPairs"] == 0 and milestone is None,
    }


def main():
    with connect(os.environ["CURATED_DSN"], row_factory=dict_row) as conn:
        print(json.dumps(checkpoint(conn)))


if __name__ == "__main__":
    main()
