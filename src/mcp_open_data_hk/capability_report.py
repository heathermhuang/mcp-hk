"""Operator-only read transaction over the existing inventory; never opens Store."""

import sqlite3
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from .capabilities import family, unpack, REVISION
from .spatial_profiles import profiles, fingerprint


def checkpoint(db, generation):
    """Compare receipt metadata once, excluding record cache touches and other packs."""
    digest = hashlib.sha256(
        json.dumps(
            [
                "opportunity-matrix-2",
                generation,
                REVISION,
                [fingerprint(p) for p in profiles()],
            ],
            sort_keys=True,
        ).encode()
    )
    for table, identity in (("resource_checks", "id"), ("resource_variants", "key")):
        digest.update(table.encode())
        for row in db.execute(
            f"SELECT {identity},checked,validated,status,reason,hash,schema_hash,rows FROM {table} ORDER BY {identity}"
        ):
            digest.update(
                json.dumps(
                    tuple(row), separators=(",", ":"), ensure_ascii=False
                ).encode()
            )
            digest.update(b"\n")
    if db.execute(
        "SELECT 1 FROM sqlite_master WHERE name='resource_selection_options'"
    ).fetchone():
        for row in db.execute(
            "SELECT resource,kind,checked,payload FROM resource_selection_options ORDER BY resource,kind"
        ):
            digest.update(
                json.dumps(
                    tuple(row)[:3], separators=(",", ":"), ensure_ascii=False
                ).encode()
            )
            digest.update(row["payload"])
    return digest.hexdigest()


def opportunity_report(path, prior=None):
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        generation = db.execute(
            "SELECT generation FROM inventory_head WHERE id=1"
        ).fetchone()[0]
        current_checkpoint = checkpoint(db, generation)
        if prior and prior.get("checkpoint") == current_checkpoint:
            return {
                "generation": generation,
                "checkpoint": current_checkpoint,
                "unchanged": True,
                "providerRequests": 0,
                "mutations": 0,
                "scope": "Inventory, receipt metadata and capability/profile revisions are unchanged; no matrix scan or source request.",
            }
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
        statuses, uncovered = Counter(), defaultdict(set)
        schemas = defaultdict(list)
        for row in db.execute(
            "SELECT resource,schema_hash FROM resource_variants WHERE schema_hash IS NOT NULL GROUP BY resource,schema_hash ORDER BY resource,schema_hash"
        ):
            schemas[row["resource"]].append(row["schema_hash"])
        for r in db.execute(
            "SELECT r.*,c.status,c.reason,c.schema_hash FROM inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id WHERE r.generation=? ORDER BY r.id",
            (generation,),
        ):
            resource = unpack(r["payload"])
            status = r["status"] or "pending"
            statuses[status] += 1
            fingerprints = tuple(schemas.get(r["id"], ()))
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
                "operation": "map_imagery" if k[0] == "map_imagery" else "records",
                "disposition": (
                    "not_a_record_reader_opportunity"
                    if k[0] in {"map_imagery", "document_text"}
                    else "requires_scope_review"
                ),
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
            "checkpoint": current_checkpoint,
            "unchanged": False,
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
