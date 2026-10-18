"""Explicit CLI ingestion; never runs in a user request."""

import argparse
import asyncio
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from .contracts import DomainError
from .http import request_json
from .resource_fetch import fetch
from .sources import (
    DISTRICTS,
    POPULATION,
    RESTAURANTS_SNAPSHOT,
    parse_population,
    parse_restaurant,
)
from .storage import Store


async def read_restaurant_features():
    # The paginated CSDI service currently alternates between different source
    # editions even within one second. Its official GeoJSON file is one complete
    # response, so rows cannot be assembled from different replicas/editions.
    body, _, resolved, status = await fetch(RESTAURANTS_SNAPSHOT, maximum=32_000_000)
    if status != 200 or resolved != RESTAURANTS_SNAPSHOT:
        raise DomainError("INVALID_SOURCE", "Restaurant snapshot source changed")
    try:
        value = json.loads(body)
        features = value["features"]
        if (
            value.get("type") != "FeatureCollection"
            or value.get("error")
            or value.get("exceededTransferLimit")
            or not isinstance(features, list)
            or not 1 <= len(features) <= 100_000
            or any(
                not isinstance(f, dict)
                or f.get("type") != "Feature"
                or not isinstance(f.get("properties"), dict)
                for f in features
            )
        ):
            raise ValueError("Incomplete feature collection")
        return [{"attributes": f["properties"]} for f in features]
    except (ValueError, KeyError, TypeError, AttributeError):
        raise DomainError(
            "INCOMPLETE_SOURCE", "Official restaurant snapshot is invalid or incomplete"
        ) from None


async def read_features(layer: str):
    query = layer + "/query"
    ids = await request_json(
        query, {"where": "1=1", "returnIdsOnly": "true", "f": "json"}
    )
    expected = ids.get("objectIds")
    if (
        not isinstance(expected, list)
        or not expected
        or len(expected) > 100_000
        or len(set(expected)) != len(expected)
    ):
        raise DomainError(
            "INVALID_SOURCE_IDS", "Government feature identities are invalid"
        )
    features = []
    # CSDI's gateway rejects long encoded objectIds URLs with 404. Keep requests
    # well below its URL limit while reconciling every requested identity.
    for start in range(0, len(expected), 100):
        chunk = expected[start : start + 100]
        page = await request_json(
            query,
            {
                "objectIds": ",".join(map(str, chunk)),
                "outFields": "*",
                "returnGeometry": "false",
                "outSR": 4326,
                "f": "json",
            },
        )
        rows = page.get("features", [])
        if (
            page.get("error")
            or page.get("exceededTransferLimit")
            or {f["attributes"]["OBJECTID"] for f in rows} != set(chunk)
        ):
            raise DomainError(
                "INCOMPLETE_SOURCE", "Government feature response is incomplete"
            )
        features.extend(rows)
    final = await request_json(
        query, {"where": "1=1", "returnIdsOnly": "true", "f": "json"}
    )
    if set(final.get("objectIds", [])) != set(expected):
        raise DomainError(
            "SOURCE_CHANGED_DURING_IMPORT",
            "Source identities changed while reading pages",
        )
    return features


async def refresh(store: Store, pack: str):
    started, run = time.time(), uuid.uuid4().hex
    previous = store.active(pack)
    with store.connect() as db:
        db.execute(
            "INSERT INTO ingestion_runs(id,pack,started,status) VALUES (?,?,?,?)",
            (run, pack, started, "running"),
        )
    try:
        if pack == "restaurants":
            features = await read_restaurant_features()
            rows = [parse_restaurant(f) for f in features]
            coverage = sum(r["latitude"] is not None for r in rows) / len(rows)
            if coverage < 0.95:
                raise DomainError(
                    "SPATIAL_COVERAGE_LOW",
                    "Less than 95% of source records have coordinates",
                )
        elif pack == "population":
            features = await read_features(POPULATION)
            rows = [parse_population(f) for f in features]
            if len(rows) != 18 or {r["districtId"] for r in rows} != {
                d["id"] for d in DISTRICTS
            }:
                raise DomainError(
                    "INCOMPLETE_DISTRICTS", "Expected all 18 distinct source districts"
                )
        else:
            raise DomainError("INVALID_PACK", "Choose restaurants or population", 400)
        # Immutable capture is private runtime state, not bundled or relicensed data.
        capture = Path(store.path).parent / "captures"
        capture.mkdir(exist_ok=True)
        raw = json.dumps(features, ensure_ascii=False, sort_keys=True).encode()
        digest = hashlib.sha256(raw).hexdigest()
        (capture / f"{digest}.json").write_bytes(raw)
        snapshot_id = store.publish(pack, rows, previous)
        with store.connect() as db:
            db.execute(
                "UPDATE ingestion_runs SET finished=?,status='success',snapshot=?,capture=? WHERE id=?",
                (time.time(), snapshot_id, digest, run),
            )
        return {
            "pack": pack,
            "snapshotId": snapshot_id,
            "records": len(rows),
            "captureHash": digest,
        }
    except Exception as exc:
        code = exc.code if isinstance(exc, DomainError) else "SOURCE_SCHEMA_CHANGED"
        store.check(pack, code)
        with store.connect() as db:
            db.execute(
                "UPDATE ingestion_runs SET finished=?,status='failed',error=? WHERE id=?",
                (time.time(), code, run),
            )
        if isinstance(exc, DomainError):
            raise
        raise DomainError(
            code, "Source schema or validation changed; previous snapshot retained"
        ) from exc


def main():
    parser = argparse.ArgumentParser(
        description="Refresh validated public-data snapshots"
    )
    parser.add_argument("pack", choices=["restaurants", "population", "all"])
    parser.add_argument(
        "--database", default=os.environ.get("MCP_HK_DATABASE", ".data/mcp-hk.sqlite3")
    )
    args = parser.parse_args()
    store = Store(args.database)

    async def run():
        for pack in (
            ["population", "restaurants"] if args.pack == "all" else [args.pack]
        ):
            print(json.dumps(await refresh(store, pack)))

    asyncio.run(run())


if __name__ == "__main__":
    main()
