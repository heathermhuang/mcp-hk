"""Operator-only read transaction over the existing inventory; never opens Store."""

import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from .capabilities import family, unpack


def opportunity_report(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        generation = db.execute(
            "SELECT generation FROM inventory_head WHERE id=1"
        ).fetchone()[0]
        datasets = {
            r["id"]: unpack(r["payload"])
            for r in db.execute(
                "SELECT id,payload FROM inventory_datasets WHERE generation=?",
                (generation,),
            )
        }
        alternatives = defaultdict(list)
        for r in db.execute(
            "SELECT r.id,r.dataset FROM inventory_resources r JOIN resource_checks c ON c.id=r.id WHERE r.generation=? AND c.status='queryable'",
            (generation,),
        ):
            alternatives[r["dataset"]].append(r["id"])
        groups = defaultdict(
            lambda: {"resources": 0, "datasets": set(), "withAlternative": set()}
        )
        statuses, uncovered, schema_counts = Counter(), defaultdict(set), Counter()
        for r in db.execute(
            "SELECT r.*,c.status,c.reason,c.schema_hash FROM inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id WHERE r.generation=? ORDER BY r.id",
            (generation,),
        ):
            resource = unpack(r["payload"])
            status = r["status"] or "pending"
            statuses[status] += 1
            fingerprints = tuple(
                x[0]
                for x in db.execute(
                    "SELECT DISTINCT schema_hash FROM resource_variants WHERE resource=? AND schema_hash IS NOT NULL ORDER BY schema_hash",
                    (r["id"],),
                )
            )
            schema_counts[len(fingerprints)] += 1
            provider = datasets[r["dataset"]].get("provider", "unknown")
            key = (
                provider,
                family(resource),
                r["format"],
                status,
                r["reason"],
                fingerprints,
            )
            group = groups[key]
            group["resources"] += 1
            group["datasets"].add(r["dataset"])
            if alternatives[r["dataset"]]:
                group["withAlternative"].add(r["dataset"])
            elif status != "queryable":
                uncovered[(family(resource), status, r["reason"])].add(r["dataset"])
        matrix = [
            {
                "provider": k[0],
                "accessFamily": k[1],
                "format": k[2],
                "status": k[3],
                "reason": k[4],
                "schemaFingerprints": list(k[5]),
                "resourceCount": v["resources"],
                "datasetCount": len(v["datasets"]),
                "datasetsWithAcceptedAlternative": len(v["withAlternative"]),
            }
            for k, v in groups.items()
        ]
        backlog = [
            {
                "accessFamily": k[0],
                "status": k[1],
                "reason": k[2],
                "operation": "records",
                "uncoveredDatasetCount": len(ids),
                "datasetIds": sorted(ids),
                "benefit": "candidate_only_scope_equivalence_unverified",
                "cost": None,
            }
            for k, ids in uncovered.items()
        ]
        backlog.sort(
            key=lambda x: (
                -x["uncoveredDatasetCount"],
                x["accessFamily"],
                x["status"],
                x["reason"] or "",
            )
        )
        return {
            "generation": generation,
            "datasetCount": len(datasets),
            "resourceCount": sum(statuses.values()),
            "byStatus": dict(statuses),
            "datasetsWithAcceptedRepresentation": len(
                [v for v in alternatives.values() if v]
            ),
            "uncoveredDatasetOperationPairs": len(datasets)
            - len([v for v in alternatives.values() if v]),
            "matrix": matrix,
            "rankedBacklog": backlog,
            "providerRequests": 0,
            "mutations": 0,
            "scope": "Same-dataset alternatives are not proven equivalent in language, period, selection or semantics. Backlog families overlap; do not sum their dataset counts.",
        }
    finally:
        db.close()
