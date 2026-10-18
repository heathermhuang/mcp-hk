"""Inventory generations and bounded accepted resource cache in the recovery database."""

import hashlib
import json
import time
import uuid
import zlib

from .contracts import DomainError
from . import transport, connected
from .quality import REVISION as REVIEW_REVISION, freshness
from .review_config import capacity
from .source_contracts import comparable_fields

CACHE_BYTES = 4_000_000


def unpack(value):
    return json.loads(zlib.decompress(value) if isinstance(value, bytes) else value)


class CatalogueStore:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS resource_policies (id TEXT PRIMARY KEY, revision TEXT, ttl INTEGER, operator TEXT, mode TEXT);
            CREATE TABLE IF NOT EXISTS inventories (id TEXT PRIMARY KEY, created REAL, receipt TEXT);
            CREATE TABLE IF NOT EXISTS inventory_head (id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT);
            CREATE TABLE IF NOT EXISTS inventory_datasets (generation TEXT, id TEXT, payload TEXT, PRIMARY KEY(generation,id));
            CREATE TABLE IF NOT EXISTS inventory_resources (generation TEXT, id TEXT, dataset TEXT, format TEXT, payload TEXT, PRIMARY KEY(generation,id));
            CREATE INDEX IF NOT EXISTS resource_dataset ON inventory_resources(generation,dataset);
            CREATE TABLE IF NOT EXISTS resource_checks (id TEXT PRIMARY KEY, checked REAL, validated REAL, status TEXT, reason TEXT, hash TEXT, schema_hash TEXT, schema_json TEXT, etag TEXT, modified TEXT, retrieved REAL, rows INTEGER);
            CREATE TABLE IF NOT EXISTS resource_variants (key TEXT PRIMARY KEY, resource TEXT, checked REAL, validated REAL, status TEXT, reason TEXT, hash TEXT, schema_hash TEXT, schema_json TEXT, etag TEXT, modified TEXT, retrieved REAL, rows INTEGER);
            CREATE INDEX IF NOT EXISTS resource_variant_lookup ON resource_variants(resource,validated DESC);
            CREATE TABLE IF NOT EXISTS resource_cache (key TEXT PRIMARY KEY, resource TEXT, hash TEXT, payload BLOB, accessed REAL);
            CREATE TABLE IF NOT EXISTS catalogue_runs (id TEXT PRIMARY KEY, started REAL, finished REAL, status TEXT, receipt TEXT);
            CREATE TABLE IF NOT EXISTS resource_audit_cursor (id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT, cursor TEXT);
            """
            )

    def refresh_transport_policies(self):
        """Invalidate legacy success/error labels once per adapter revision/resource."""
        placeholders = ",".join("?" for _ in transport.DATASETS)
        with self.store.connect() as db:
            rows = db.execute(
                f"SELECT r.id,r.payload,p.revision FROM inventory_resources r LEFT JOIN resource_policies p ON p.id=r.id WHERE r.generation=(SELECT generation FROM inventory_head WHERE id=1) AND r.dataset IN ({placeholders})",
                transport.DATASETS,
            ).fetchall()
            for row in rows:
                p = transport.profile(unpack(row["payload"]))
                if not p or row["revision"] == transport.REVISION:
                    continue
                status = "needs_selection" if p.required else "pending"
                db.execute(
                    "INSERT INTO resource_checks(id,status,reason) VALUES (?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status,reason=excluded.reason,validated=NULL,hash=NULL,schema_hash=NULL,schema_json=NULL,rows=NULL",
                    (row["id"], status, "TRANSPORT_VALIDATION_REQUIRED"),
                )
                db.execute(
                    "INSERT OR REPLACE INTO resource_policies VALUES (?,?,?,?,?)",
                    (
                        row["id"],
                        transport.REVISION,
                        p.ttl if p.arrivals else None,
                        p.operator,
                        p.mode,
                    ),
                )
            db.execute(
                "UPDATE resource_checks SET status='stale',reason='TRANSPORT_REFRESH_DUE' WHERE status='queryable' AND EXISTS (SELECT 1 FROM resource_policies p WHERE p.id=resource_checks.id AND p.ttl IS NOT NULL AND resource_checks.validated < ? - p.ttl)",
                (time.time(),),
            )

    def classify_legacy_failures(self):
        with self.store.connect() as db:
            db.execute(
                "UPDATE resource_checks SET reason='SOURCE_PARSE_ERROR',status='needs_adapter' WHERE reason GLOB '[0-9]*'"
            )
            db.execute(
                "UPDATE resource_checks SET status='needs_adapter' WHERE status='unavailable' AND reason IN ('SOURCE_PARSE_ERROR','SOURCE_SCHEMA_CHANGED')"
            )

    def compact(self):
        with self.store.connect() as db:
            for row in db.execute(
                "SELECT generation,id,payload FROM inventory_resources WHERE typeof(payload)='text'"
            ).fetchall():
                db.execute(
                    "UPDATE inventory_resources SET payload=? WHERE generation=? AND id=?",
                    (
                        zlib.compress(row["payload"].encode()),
                        row["generation"],
                        row["id"],
                    ),
                )

    def head(self):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT generation FROM inventory_head WHERE id=1"
            ).fetchone()
        if not row:
            raise DomainError(
                "INVENTORY_NOT_LOADED",
                "The catalogue inventory has not been published",
                503,
            )
        return row[0]

    def publish(self, datasets, resources, receipt):
        if (
            not datasets
            or len({d["id"] for d in datasets}) != len(datasets)
            or len({r["id"] for r in resources}) != len(resources)
        ):
            raise ValueError("Inventory has empty or duplicate identities")
        if not {r["datasetId"] for r in resources} <= {d["id"] for d in datasets}:
            raise ValueError("Inventory contains orphan resources")
        generation = uuid.uuid4().hex
        fingerprint = hashlib.sha256(
            json.dumps(
                [datasets, resources], sort_keys=True, ensure_ascii=False
            ).encode()
        ).hexdigest()
        receipt = {
            **receipt,
            "fingerprint": fingerprint,
            "datasetCount": len(datasets),
            "resourceCount": len(resources),
        }
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT generation FROM inventory_head WHERE id=1"
            ).fetchone()
            if old:
                prior = json.loads(
                    db.execute(
                        "SELECT receipt FROM inventories WHERE id=?", (old[0],)
                    ).fetchone()[0]
                )
                if prior.get("fingerprint") == fingerprint:
                    db.execute(
                        "UPDATE inventories SET created=?,receipt=? WHERE id=?",
                        (time.time(), json.dumps(receipt), old[0]),
                    )
                    return old[0]
                if (
                    len(datasets) < prior["datasetCount"] * 0.8
                    or len(resources) < prior["resourceCount"] * 0.8
                ):
                    raise ValueError(
                        "Inventory count drop exceeds 20%; previous generation retained"
                    )
            db.execute(
                "INSERT INTO inventories VALUES (?,?,?)",
                (generation, time.time(), json.dumps(receipt)),
            )
            db.executemany(
                "INSERT INTO inventory_datasets VALUES (?,?,?)",
                (
                    (generation, d["id"], json.dumps(d, ensure_ascii=False))
                    for d in datasets
                ),
            )
            db.executemany(
                "INSERT INTO inventory_resources VALUES (?,?,?,?,?)",
                (
                    (
                        generation,
                        r["id"],
                        r["datasetId"],
                        r["format"],
                        zlib.compress(json.dumps(r, ensure_ascii=False).encode()),
                    )
                    for r in resources
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO inventory_head VALUES (1,?)", (generation,)
            )
            # Keep active and previous metadata generations; R2 retains older checkpoints.
            keep = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM inventories ORDER BY created DESC LIMIT 2"
                )
            ]
            for row in db.execute("SELECT id FROM inventories").fetchall():
                if row[0] not in keep:
                    for table in ("inventory_resources", "inventory_datasets"):
                        db.execute(f"DELETE FROM {table} WHERE generation=?", (row[0],))
                    db.execute("DELETE FROM inventories WHERE id=?", (row[0],))
        self.refresh_transport_policies()
        return generation

    def resource(self, resource_id):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT payload FROM inventory_resources WHERE generation=? AND id=?",
                (self.head(), resource_id),
            ).fetchone()
        if not row:
            raise DomainError(
                "RESOURCE_NOT_FOUND", "Use a resource ID from the inventory", 404
            )
        result = unpack(row[0])
        p = transport.profile(result)
        if p:
            result["transport"] = p.describe()
        return result

    def dataset(self, dataset_id):
        if entry := connected.get(dataset_id):
            return entry
        with self.store.connect() as db:
            row = db.execute(
                "SELECT payload FROM inventory_datasets WHERE generation=? AND id=?",
                (self.head(), dataset_id),
            ).fetchone()
        if not row:
            raise DomainError(
                "DATASET_NOT_FOUND", "Dataset is absent from this inventory", 404
            )
        return json.loads(row[0])

    def search(self, q="", limit=20, offset=0, access="all"):
        if (
            len(q) > 200
            or not 1 <= limit <= 100
            or not 0 <= offset <= 100000
            or access not in {"all", "connected", "sources"}
        ):
            raise DomainError("INVALID_QUERY", "Invalid search or pagination", 400)
        self.refresh_transport_policies()
        generation = self.head()
        curated = connected.matching(q) if access != "sources" else []
        terms = connected.normalise(q).split() or [""]
        patterns = [
            "%" + t.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            for t in terms
        ]
        where = "generation=?" + " AND payload LIKE ? ESCAPE '\\'" * len(patterns)
        with self.store.connect() as db:
            total_native = (
                db.execute(
                    "SELECT count(*) FROM inventory_datasets WHERE " + where,
                    (generation, *patterns),
                ).fetchone()[0]
                if access != "connected"
                else 0
            )
            start_native = max(0, offset - len(curated))
            count_native = max(0, limit - len(curated[offset : offset + limit]))
            rows = (
                db.execute(
                    "SELECT payload FROM inventory_datasets WHERE "
                    + where
                    + " ORDER BY CASE WHEN lower(json_extract(payload,'$.title'))=? THEN 0 WHEN json_extract(payload,'$.title') LIKE ? ESCAPE '\\' OR json_extract(payload,'$.titleZhHant') LIKE ? ESCAPE '\\' THEN 1 WHEN json_extract(payload,'$.provider') LIKE ? ESCAPE '\\' THEN 2 ELSE 3 END,id LIMIT ? OFFSET ?",
                    (
                        generation,
                        *patterns,
                        connected.normalise(q),
                        patterns[0],
                        patterns[0],
                        patterns[0],
                        count_native,
                        start_native,
                    ),
                ).fetchall()
                if total_native and count_native
                else []
            )
            native = [json.loads(r[0]) for r in rows]
            for item in native:
                states = {
                    r[0]: r[1]
                    for r in db.execute(
                        "SELECT COALESCE(c.status,'pending'),count(*) FROM inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id WHERE r.generation=? AND r.dataset=? GROUP BY 1",
                        (generation, item["id"]),
                    )
                }
                item["entryKind"] = "source_dataset"
                item["resourceSummary"] = {
                    "total": sum(states.values()),
                    "byStatus": states,
                }
        total = len(curated) + total_native
        return {
            "items": curated[offset : offset + limit] + native,
            "total": total,
            "connectedTotal": len(curated),
            "sourceTotal": total_native,
            "offset": offset,
            "nextOffset": offset + limit if offset + limit < total else None,
            "generation": generation,
            "scope": "Connected query services plus harvested source datasets; connected views can overlap source datasets and are not added to government coverage counts.",
        }

    def resources(self, dataset=None, status=None, fmt=None, limit=20, offset=0):
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise DomainError("INVALID_QUERY", "Invalid pagination", 400)
        if entry := connected.get(dataset):
            return {
                "items": [],
                "total": 0,
                "offset": offset,
                "nextOffset": None,
                "connected": entry,
                "access": entry["access"],
                "generation": self.head(),
                "scope": "Use the connected HTTP endpoint or MCP tool; this is not an imported government resource.",
            }
        self.refresh_transport_policies()
        if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
            raise DomainError("INVALID_QUERY", "Invalid pagination", 400)
        where = "r.generation=?"
        args = [self.head()]
        for expression, value in [
            ("r.dataset", dataset),
            ("COALESCE(c.status,'pending')", status),
            ("r.format", fmt),
        ]:
            if value:
                where += f" AND {expression}=?"
                args.append(value)
        source = "inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id"
        with self.store.connect() as db:
            total = db.execute(
                f"SELECT count(*) FROM {source} WHERE {where}", args
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT r.payload,c.status,c.reason,c.checked,c.validated,c.rows FROM {source} WHERE {where} ORDER BY CASE WHEN c.status='queryable' THEN 0 WHEN c.status IN ('needs_selection','stale') THEN 1 WHEN c.status='document' THEN 2 WHEN c.status IN ('unavailable','restricted') THEN 4 ELSE 3 END, CASE WHEN r.format IN ('JSON','CSV','GEOJSON') THEN 0 WHEN r.format IN ('XML','XLSX','XLS') THEN 1 WHEN r.format IN ('ARCGIS','API') THEN 2 WHEN r.format='PDF' THEN 3 ELSE 4 END,r.id LIMIT ? OFFSET ?",
                (*args, limit, offset),
            ).fetchall()
        items = []
        for row in rows:
            items.append(
                {
                    **unpack(row["payload"]),
                    "validation": {
                        "status": row["status"] or "pending",
                        "reason": row["reason"],
                        "lastCheckedAt": row["checked"],
                        "lastValidatedAt": row["validated"],
                        "recordCount": row["rows"],
                    },
                }
            )
        for item in items:
            p = transport.profile(item)
            item["validation"]["freshness"] = freshness(
                self.dataset(item["datasetId"]),
                item,
                item["validation"]["lastValidatedAt"],
                p.ttl if p else None,
            )
            item["validation"]["semanticVerification"] = "not_performed"
            if p:
                item["transport"] = p.describe()
                item["validation"]["scope"] = "last_selected_route_or_stop"
        return {
            "items": items,
            "total": total,
            "offset": offset,
            "nextOffset": offset + limit if offset + limit < total else None,
            "generation": self.head(),
        }

    def check(self, resource_id, key=None):
        with self.store.connect() as db:
            r = (
                db.execute(
                    "SELECT * FROM resource_variants WHERE key=?", (key,)
                ).fetchone()
                if key
                else db.execute(
                    "SELECT * FROM resource_checks WHERE id=?", (resource_id,)
                ).fetchone()
            )
        return dict(r) if r else {}

    def failure(self, resource_id, code, status="unavailable", key=None):
        with self.store.connect() as db:
            db.execute(
                "INSERT INTO resource_checks(id,checked,status,reason) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET checked=excluded.checked,status=excluded.status,reason=excluded.reason",
                (resource_id, time.time(), status, code),
            )
            if key:
                db.execute(
                    "UPDATE resource_variants SET checked=?,status=?,reason=? WHERE key=?",
                    (time.time(), status, code, key),
                )

    def revalidate(self, resource_id, key, prior, headers):
        """A 304 validates this exact accepted representation, without new rows."""
        now = time.time()
        with self.store.connect() as db:
            changed = db.execute(
                "UPDATE resource_variants SET checked=?,validated=?,reason=NULL,etag=COALESCE(?,etag),modified=COALESCE(?,modified) WHERE key=? AND resource=? AND hash=? AND schema_hash=? AND status IN ('queryable','document')",
                (
                    now,
                    now,
                    headers.get("etag"),
                    headers.get("last-modified"),
                    key,
                    resource_id,
                    prior["hash"],
                    prior["schema_hash"],
                ),
            ).rowcount
            if changed != 1:
                raise DomainError(
                    "CONCURRENT_RESOURCE_CHANGE",
                    "Accepted source changed during revalidation",
                    409,
                )
            row = db.execute(
                "SELECT * FROM resource_variants WHERE key=?", (key,)
            ).fetchone()
            db.execute(
                "UPDATE resource_checks SET checked=?,validated=?,status=?,reason=NULL,hash=?,schema_hash=?,schema_json=NULL,etag=?,modified=?,retrieved=?,rows=? WHERE id=?",
                (
                    now,
                    now,
                    row["status"],
                    row["hash"],
                    row["schema_hash"],
                    row["etag"],
                    row["modified"],
                    row["retrieved"],
                    row["rows"],
                    resource_id,
                ),
            )
        return dict(row)

    def accept(self, resource_id, key, rows, schema, digest, headers, document=False):
        contract = schema.get("sourceContract", {}).get("id")
        schema_hash = hashlib.sha256(
            json.dumps(comparable_fields(schema, contract), sort_keys=True).encode()
        ).hexdigest()
        old = self.check(resource_id, key)
        if old.get("schema_json"):
            prior_schema = unpack(old["schema_json"])
            old["schema_hash"] = hashlib.sha256(
                json.dumps(
                    comparable_fields(prior_schema, contract), sort_keys=True
                ).encode()
            ).hexdigest()
        arrival_contract = schema.get("transport", {}).get("operation") == "arrivals"
        if (
            not arrival_contract
            and old.get("schema_hash")
            and old["schema_hash"] != schema_hash
        ):
            self.failure(resource_id, "SCHEMA_DRIFT", "schema_drift", key)
            raise DomainError(
                "SCHEMA_DRIFT",
                "Source fields/types changed; accepted version retained for operator review",
                409,
            )
        encoded = (
            zlib.compress(
                json.dumps(
                    {"rows": rows, "schema": schema},
                    ensure_ascii=False,
                    allow_nan=False,
                ).encode()
            )
            if isinstance(rows, list)
            else None
        )
        now = time.time()
        retrieved = old.get("retrieved") if old.get("hash") == digest else now
        with self.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO resource_variants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    key,
                    resource_id,
                    now,
                    now,
                    "document" if document else "queryable",
                    None,
                    digest,
                    schema_hash,
                    zlib.compress(json.dumps(schema).encode()),
                    headers.get("etag"),
                    headers.get("last-modified"),
                    retrieved,
                    len(rows),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO resource_checks VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    resource_id,
                    now,
                    now,
                    "document" if document else "queryable",
                    None,
                    digest,
                    schema_hash,
                    None,
                    headers.get("etag"),
                    headers.get("last-modified"),
                    retrieved,
                    len(rows),
                ),
            )
            if encoded is not None and len(encoded) <= CACHE_BYTES:
                db.execute(
                    "INSERT OR REPLACE INTO resource_cache VALUES (?,?,?,?,?)",
                    (key, resource_id, digest, encoded, now),
                )
            db.execute(
                "DELETE FROM resource_variants WHERE key IN (SELECT key FROM resource_variants WHERE resource=? ORDER BY checked DESC LIMIT -1 OFFSET 50)",
                (resource_id,),
            )
            size = db.execute(
                "SELECT COALESCE(sum(length(payload)),0) FROM resource_cache"
            ).fetchone()[0]
            for row in db.execute(
                "SELECT key,length(payload) FROM resource_cache ORDER BY accessed"
            ).fetchall():
                if size <= CACHE_BYTES:
                    break
                db.execute("DELETE FROM resource_cache WHERE key=?", (row[0],))
                size -= row[1]
        return self.check(resource_id, key)

    def cached(self, key):
        with self.store.connect() as db:
            r = db.execute(
                "SELECT * FROM resource_cache WHERE key=?", (key,)
            ).fetchone()
            if r:
                db.execute(
                    "UPDATE resource_cache SET accessed=? WHERE key=?",
                    (time.time(), key),
                )
        return (
            {**dict(r), "value": json.loads(zlib.decompress(r["payload"]))}
            if r
            else None
        )

    def coverage(self):
        self.refresh_transport_policies()
        generation = self.head()
        with self.store.connect() as db:
            meta = db.execute(
                "SELECT * FROM inventories WHERE id=?", (generation,)
            ).fetchone()
            statuses = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT COALESCE(c.status,'pending'),count(*) FROM inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id WHERE r.generation=? GROUP BY 1",
                    (generation,),
                )
            }
            stale = db.execute(
                "SELECT count(*) FROM resource_checks c JOIN inventory_resources r ON r.id=c.id WHERE r.generation=? AND c.validated<? AND c.status IN ('queryable','document')",
                (generation, time.time() - 86400),
            ).fetchone()[0]
            formats = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT format,count(*) FROM inventory_resources WHERE generation=? GROUP BY format",
                    (generation,),
                )
            }
            dataset_validated = db.execute(
                "SELECT count(DISTINCT r.dataset) FROM inventory_resources r JOIN resource_checks c ON c.id=r.id WHERE r.generation=? AND c.status='queryable'",
                (generation,),
            ).fetchone()[0]
            reasons = {
                r[0]: r[1]
                for r in db.execute(
                    "SELECT reason,count(*) FROM resource_checks c JOIN inventory_resources r ON r.id=c.id WHERE r.generation=? AND reason IS NOT NULL GROUP BY reason",
                    (generation,),
                )
            }
            cache_bytes = db.execute(
                "SELECT COALESCE(sum(length(payload)),0) FROM resource_cache"
            ).fetchone()[0]
        with self.store.connect() as db:
            live = [
                dict(r)
                for r in db.execute(
                    "SELECT p.operator,p.mode,p.ttl,COALESCE(c.status,'pending') status,count(*) resources FROM resource_policies p JOIN inventory_resources r ON r.id=p.id AND r.generation=? LEFT JOIN resource_checks c ON c.id=p.id WHERE p.ttl IS NOT NULL GROUP BY p.operator,p.mode,p.ttl,c.status",
                    (generation,),
                )
            ]
        review = {
            "status": "not_initialized",
            "scope": "Validation recency is not observation age or semantic verification.",
        }
        with self.store.connect() as db:
            if db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='resource_review_policy'"
            ).fetchone():
                setup = db.execute(
                    "SELECT * FROM resource_review_setup WHERE id=1"
                ).fetchone()
                if (
                    setup
                    and setup["generation"] == generation
                    and setup["revision"] == REVIEW_REVISION
                ):
                    now = time.time()
                    counts = db.execute(
                        "SELECT count(*) total,SUM(CASE WHEN c.validated IS NULL OR c.validated+COALESCE(t.ttl,p.cache_ttl)<=? THEN 1 ELSE 0 END) cache_expired,SUM(CASE WHEN c.validated IS NULL OR c.validated+p.interval<=? THEN 1 ELSE 0 END) review_overdue FROM inventory_resources r JOIN resource_review_policy p ON p.id=r.id JOIN resource_checks c ON c.id=r.id LEFT JOIN resource_policies t ON t.id=r.id WHERE r.generation=? AND c.status='queryable'",
                        (now, now, generation),
                    ).fetchone()
                    state = db.execute(
                        "SELECT receipt FROM resource_review_state WHERE id=1"
                    ).fetchone()
                    demand = db.execute(
                        "SELECT COALESCE(sum(86400.0/p.interval),0) demand FROM resource_review_policy p JOIN inventory_resources r ON r.id=p.id JOIN resource_checks c ON c.id=r.id LEFT JOIN resource_policies t ON t.id=r.id WHERE r.generation=? AND c.status IN ('queryable','document') AND t.ttl IS NULL",
                        (generation,),
                    ).fetchone()["demand"]
                    accepted = db.execute(
                        "SELECT count(*) overdue FROM resource_review_policy p JOIN inventory_resources r ON r.id=p.id JOIN resource_checks c ON c.id=r.id LEFT JOIN resource_policies t ON t.id=r.id WHERE r.generation=? AND c.validated IS NOT NULL AND c.validated+p.interval<=? AND t.ttl IS NULL",
                        (generation, now),
                    ).fetchone()["overdue"]
                    plan = capacity(demand)
                    review.update(
                        status="active",
                        policyVersion=setup["revision"],
                        queryableCount=counts["total"],
                        cacheExpiredCount=counts["cache_expired"] or 0,
                        reviewOverdueCount=counts["review_overdue"] or 0,
                        lastMaintenance=json.loads(state[0]) if state else None,
                        capacity=plan,
                        overdueAcceptedCount=accepted,
                        health=(
                            "degraded"
                            if accepted or plan["status"] != "sufficient"
                            else "healthy"
                        ),
                    )
        receipt = json.loads(meta["receipt"])
        return {
            "generation": generation,
            "validationFreshness": review,
            "realtimeTransport": {
                "resources": live,
                "scope": "Last tested route/stop selections only; not every route or operator. Expired checks require a new source read. Scheduled departures remain labelled by the provider.",
            },
            "lastCatalogueCheckAt": meta["created"],
            "catalogue": receipt,
            "resources": {
                "discovered": receipt["resourceCount"],
                "byStatus": statuses,
                "staleValidated": stale,
                "byFormat": formats,
                "failureReasons": reasons,
            },
            "datasets": {
                "discovered": receipt["datasetCount"],
                "withQueryableResource": dataset_validated,
            },
            "cache": {"bytes": cache_bytes, "budgetBytes": CACHE_BYTES},
            "claim": "Inventory discovery is not full data onboarding. Queryability requires an actual successful resource read; API response coverage is not necessarily full historical coverage.",
            "allGovernmentDataConnected": False,
        }
