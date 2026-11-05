"""Bounded HTTP/MCP point cohort; optional exact-file replay, never a full audit."""

import argparse
import asyncio
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlencode

import httpx
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.spatial_profiles import profiles


async def run(args, folder):
    replay = bool(args.school_file and args.clinic_file)
    if bool(args.school_file) != bool(args.clinic_file):
        raise ValueError("Provide both replay files or neither")
    patches = None
    if replay:
        service = Service(Store(str(Path(folder) / "cohort.sqlite3")))
        datasets, resources, bodies = [], [], {}
        for profile in profiles():
            url = "https://" + profile["host"] + profile["path"]
            if profile["query"]:
                url += "?" + urlencode({k: v[0] for k, v in profile["query"].items()})
            resources.append(
                {
                    "id": profile["resourceId"],
                    "datasetId": profile["datasetId"],
                    "format": profile["format"],
                    "url": url,
                    "sourceUrl": profile["evidence"][0],
                    "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                    "catalogue": "DATA.GOV.HK",
                }
            )
            datasets.append(
                {
                    "id": profile["datasetId"],
                    "title": profile["entityKind"],
                    "provider": (
                        "Education Bureau"
                        if profile["entityKind"] == "school"
                        else "Department of Health"
                    ),
                    "catalogue": "DATA.GOV.HK",
                }
            )
            bodies[url] = Path(
                args.school_file
                if profile["entityKind"] == "school"
                else args.clinic_file
            ).read_bytes()
        service.resources.catalogue.publish(datasets, resources, {})

        async def fetch(url, headers=None, **kwargs):
            if url not in bodies:
                raise AssertionError("Replay may only read the two fixed source files")
            return (
                bodies[url],
                {"_mcp_source_transport": "official_file_replay"},
                url,
                200,
            )

        patches = patch("mcp_open_data_hk.resources.fetch", fetch)
        patches.start()
        app = create_app(service)
        http = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        mcp = Client(app.state.mcp)
    else:
        http = httpx.AsyncClient(base_url=args.base_url.rstrip("/"), timeout=120)
        mcp = Client(args.base_url.rstrip("/") + "/mcp", timeout=120)
    receipts = []
    try:
        async with http, mcp:
            for profile in profiles():
                key = profile["resourceId"]
                started = time.perf_counter()
                response = await http.get("/api/v1/resources/" + key + "/schema")
                response.raise_for_status()
                schema = response.json()
                binding = schema["schema"]["semanticBinding"]
                assert binding["state"] == "available"
                cold = (time.perf_counter() - started) * 1000
                if profile["entityKind"] == "school":
                    query = {
                        "nearby": {
                            "lat": 22.32422718,
                            "lon": 114.23130613,
                            "radiusM": 500,
                        },
                        "fields": [
                            "SCHOOL NO.",
                            "ENGLISH NAME",
                            "中文名稱",
                            "SESSION",
                            "SCHOOL LEVEL",
                        ],
                        "limit": 3,
                    }
                else:
                    query = {
                        "nearby": {
                            "lat": 22.3152013725,
                            "lon": 114.2259935067,
                            "radiusM": 500,
                        },
                        "fields": [
                            "properties.OBJECTID",
                            "properties.NameEN",
                            "properties.NameTC",
                            "properties.CategoryEN",
                        ],
                        "limit": 3,
                    }
                started = time.perf_counter()
                response = await http.post(
                    "/api/v1/resources/" + key + "/query", json=query
                )
                response.raise_for_status()
                result = response.json()
                elapsed = (time.perf_counter() - started) * 1000
                call = await mcp.call_tool(
                    "hk_resource_query", {"resourceId": key, **query}
                )
                native = json.loads(call.content[0].text)
                assert (
                    native["data"] == result["data"]
                    and native["meta"]["nearby"] == result["meta"]["nearby"]
                )
                assert result["meta"]["total"] >= len(result["data"]["items"]) > 0
                assert [
                    r["distanceM"] for r in result["meta"]["nearby"]["matches"]
                ] == sorted(r["distanceM"] for r in result["meta"]["nearby"]["matches"])
                assert result["meta"]["nearby"]["uniqueFacilityCount"] is None
                assert schema["provenance"][0]["observedAt"] is None
                response = await http.get(
                    "/api/v1/catalogue/datasets",
                    params={
                        "capability": "nearby",
                        "entityKind": profile["entityKind"],
                    },
                )
                response.raise_for_status()
                assert profile["datasetId"] in {
                    r["id"] for r in response.json()["items"]
                }
                receipts.append(
                    {
                        "entityKind": profile["entityKind"],
                        "resourceId": key,
                        "version": result["meta"]["version"],
                        "profileFingerprint": binding["profileFingerprint"],
                        "coldSchemaMs": round(cold, 2),
                        "warmNearbyMs": round(elapsed, 2),
                        "matchingSourceRows": result["meta"]["total"],
                        "coverage": binding["coverage"],
                        "httpMcpParity": True,
                        "nativeFieldKindsPreserved": True,
                        "uniqueFacilityCount": None,
                    }
                )
    finally:
        if patches:
            patches.stop()
    report = {
        "scope": (
            "local_candidate_official_file_replay_not_deployed_source_path"
            if replay
            else "production_http_and_native_mcp"
        ),
        "cohort": receipts,
        "noModelCalls": True,
        "noCatalogueReimport": True,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://mcp.hk")
    parser.add_argument("--school-file")
    parser.add_argument("--clinic-file")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mcp-hk-capability-cohort-") as folder:
        asyncio.run(run(args, folder))
