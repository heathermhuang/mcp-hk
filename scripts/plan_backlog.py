"""Freeze exact remaining candidates from an accepted checkpoint, without source IO.

Run with PYTHONPATH=src .venv/bin/python scripts/plan_backlog.py DATABASE OUTPUT.
This writes an operator evidence file, never a capability approval or source status.
"""

import argparse
from collections import Counter, defaultdict
import gzip
import json
from pathlib import Path
import sqlite3

from mcp_open_data_hk.capabilities import family, unpack
from mcp_open_data_hk.capability_report import opportunity_report


def plan(path):
    report = opportunity_report(path)
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        generation = db.execute("SELECT generation FROM inventory_head").fetchone()[0]
        if generation != report["generation"]:
            raise ValueError("Inventory changed; restart from an immutable checkpoint")
        datasets = {
            r["id"]: unpack(r["payload"])
            for r in db.execute(
                "SELECT id,payload FROM inventory_datasets WHERE generation=?",
                (generation,),
            )
        }
        accepted = defaultdict(list)
        rows = list(
            db.execute(
                "SELECT r.id,r.dataset,r.payload,c.status,c.reason,c.checked,c.rows "
                "FROM inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id "
                "WHERE r.generation=? ORDER BY r.dataset,r.id",
                (generation,),
            )
        )
        for r in rows:
            if r["status"] == "queryable":
                accepted[r["dataset"]].append(r["id"])
        candidates, residual = [], defaultdict(list)
        for r in rows:
            resource = unpack(r["payload"])
            access = family(resource)
            status = r["status"] or "pending"
            if status == "queryable":
                continue
            if access in {"arcgis", "wfs", "workbook"}:
                candidates.append(
                    {
                        "resourceId": r["id"],
                        "datasetId": r["dataset"],
                        "title": datasets[r["dataset"]].get("title"),
                        "family": access,
                        "format": resource.get("format"),
                        "sourceUrl": resource["url"],
                        "lastStatus": status,
                        "lastReason": r["reason"],
                        "checkedAt": r["checked"],
                        "acceptedSameDatasetAlternatives": accepted.get(
                            r["dataset"], []
                        ),
                        "alternativeEquivalence": "unverified_language_period_scope",
                        "state": "pending_investigation",
                        "nextAction": (
                            "inspect_explicit_selection_then_read"
                            if status == "needs_selection"
                            else "investigate_exact_receipt_before_retry"
                        ),
                        "acceptance": "complete_selected_read_plus_scope_cost_and_recovery_receipt",
                        "semanticApproval": None,
                    }
                )
            if not accepted.get(r["dataset"]):
                residual[(r["dataset"], access, status, r["reason"])].append(r["id"])
        sizes = dict(
            db.execute("SELECT name,sum(pgsize) FROM dbstat GROUP BY name").fetchall()
        )
        allocated, free = db.execute(
            "SELECT page_count*page_size,freelist_count*page_size "
            "FROM pragma_page_count(),pragma_page_size(),pragma_freelist_count()"
        ).fetchone()
        return {
            "generation": generation,
            "checkpoint": report["checkpoint"],
            "datasetCount": report["datasetCount"],
            "resourceCount": report["resourceCount"],
            "datasetsWithAcceptedRepresentation": len(accepted),
            "familyCandidates": candidates,
            "familyCandidateCounts": dict(Counter(c["family"] for c in candidates)),
            "residualUncoveredGroups": [
                {
                    "datasetId": key[0],
                    "family": key[1],
                    "status": key[2],
                    "reason": key[3],
                    "resourceIds": ids,
                    "state": "pending_task_scope_triage",
                }
                for key, ids in sorted(residual.items(), key=lambda x: str(x[0]))
            ],
            "capacity": {
                "databaseBytes": allocated,
                "freePageBytes": free,
                "databaseCeiling": 500_000_000,
                "remainingDatabaseBytes": 500_000_000 - allocated,
                "tableBytes": sizes,
                "growthRate": None,
                "growthQualification": "measure_bounded_representative_batch_before_expansion",
            },
            "providerRequests": 0,
            "mutations": 0,
            "scope": "Frozen candidate inventory. No selection, alternate equivalence or semantic binding is approved by this report. Counts overlap across families and source representations.",
        }
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = plan(args.database)
    encoded = (
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    ).encode()
    if args.output.suffix == ".gz":
        args.output.write_bytes(gzip.compress(encoded, mtime=0))
    else:
        args.output.write_bytes(encoded)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in {"familyCandidates", "residualUncoveredGroups", "capacity"}
            }
        )
    )
