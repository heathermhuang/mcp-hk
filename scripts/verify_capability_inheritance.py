"""Small inherited-service cohort; read-only HTTP/MCP, no collection or model calls."""

import argparse
import asyncio
import json
from pathlib import Path
from urllib.parse import quote

import httpx
from fastmcp import Client

from mcp_open_data_hk.capabilities import REVISION
from mcp_open_data_hk.spatial_profiles import manifest_fingerprint

WEATHER = "574e2fdcf4b1756347aedaf3ba2feeda"
WORKBOOK = "5ab93d9a957390f887364456f799eb79"


async def run(args):
    origin = args.base_url.rstrip("/")
    cases = []
    async with (
        httpx.AsyncClient(base_url=origin, timeout=120) as http,
        Client(origin + "/mcp", timeout=120) as mcp,
    ):

        async def call(name, arguments):
            result = await mcp.call_tool(name, arguments)
            return json.loads(result.content[0].text)

        health = (await http.get("/healthz")).json()
        if args.require_current:
            assert health["resourceCapabilities"] == REVISION
            assert health["pointBindings"] == manifest_fingerprint()
        tools = {t.name: t for t in await mcp.list_tools()}
        query = {
            "recordPath": "temperature/data",
            "fields": ["place", "value", "unit"],
            "limit": 3,
        }
        if args.require_current:
            query["predicates"] = [
                {"field": "value", "kind": "number", "op": "gte", "value": "-100"}
            ]
        response = await http.post(
            "/api/v1/resources/" + WEATHER + "/query", json=query
        )
        response.raise_for_status()
        weather = response.json()
        native = await call(
            "hk_resource_query",
            {"resourceId": WEATHER, **query, "version": weather["meta"]["version"]},
        )
        assert weather["data"] == native["data"]
        quality = weather["schema"]["observationQuality"]
        assert quality["unit"] == "C" and quality["series"] == "temperature"
        assert weather["observationFreshness"]["observedAt"] == quality["observedAt"]
        assert all(
            row["unit"] == "C" and type(row["value"]) in {int, float}
            for row in weather["data"]["items"]
        )
        cases.append(
            {
                "task": "station_temperature",
                "state": "accepted",
                "httpMcpParity": True,
                "unit": "C",
                "observationTime": quality["observedAt"],
                "version": weather["meta"]["version"],
                "spatialCoverage": "stations_are_not_a_radius_weather_surface",
            }
        )
        if args.require_current:
            root = await http.post(
                "/api/v1/resources/" + WEATHER + "/query",
                json={"fields": ["updateTime"], "limit": 1},
            )
            root.raise_for_status()
            root = root.json()
            timestamp = root["data"]["items"][0]["updateTime"]
            temporal = {
                "fields": ["updateTime"],
                "limit": 1,
                "version": root["meta"]["version"],
                "predicates": [
                    {
                        "field": "updateTime",
                        "kind": "datetime",
                        "op": "gte",
                        "value": timestamp,
                    }
                ],
            }
            compared = await http.post(
                "/api/v1/resources/" + WEATHER + "/query", json=temporal
            )
            compared.raise_for_status()
            native = await call(
                "hk_resource_query", {"resourceId": WEATHER, **temporal}
            )
            assert compared.json()["data"] == native["data"] == root["data"]
            cases.append(
                {
                    "task": "qualified_datetime_comparison",
                    "state": "accepted",
                    "httpMcpParity": True,
                    "version": root["meta"]["version"],
                    "sourceTimestampPreserved": timestamp,
                }
            )
        response = await http.get("/api/v1/districts/central-western/statistics")
        response.raise_for_status()
        stats = response.json()
        period = stats["data"]["referencePeriod"]
        native = await call(
            "hk_district_statistics", {"districtId": "central-western", "year": period}
        )
        assert stats["data"] == native["data"]
        assert (
            "radiusM" not in tools["hk_district_statistics"].inputSchema["properties"]
        )
        assert "district-wide" in tools["hk_district_statistics"].description
        cases.append(
            {
                "task": "district_statistics",
                "state": "accepted",
                "httpMcpParity": True,
                "districtId": "central-western",
                "referencePeriod": period,
                "scope": "whole_district_not_radius_population",
            }
        )
        response = await http.get(
            "/api/v1/companies",
            params={"q": "HONG KONG", "view": "latest_observed", "limit": 1},
        )
        response.raise_for_status()
        companies = response.json()
        version = companies["meta"]["version"]
        item = companies["data"]["items"][0]
        entity = item["entity_id"]
        native = await call(
            "hk_company_search",
            {
                "q": "HONG KONG",
                "view": "latest_observed",
                "limit": 1,
                "version": version,
            },
        )
        assert companies["data"] == native["data"]
        assert (
            companies["meta"]["view"] == "latest_observed"
            and companies["meta"]["currentVerification"] is False
        )
        response = await http.get(
            "/api/v1/companies/" + quote(entity, safe=":"),
            params={"view": "latest_observed", "version": version},
        )
        response.raise_for_status()
        detail = response.json()
        native = await call(
            "hk_company_get",
            {"entityId": entity, "view": "latest_observed", "version": version},
        )
        assert detail["data"] == native["data"] and detail["meta"]["version"] == version
        response = await http.get(
            "/api/v1/companies",
            params={
                "namespace": "cr:local:brn",
                "value": "00000001",
                "view": "latest_observed",
                "limit": 1,
            },
        )
        response.raise_for_status()
        zeros = response.json()
        native = await call(
            "hk_company_search",
            {
                "namespace": "cr:local:brn",
                "value": "00000001",
                "view": "latest_observed",
                "limit": 1,
                "version": zeros["meta"]["version"],
            },
        )
        assert zeros["data"] == native["data"]
        cases.append(
            {
                "task": "official_company_identity",
                "state": "accepted",
                "httpMcpParity": True,
                "entityId": entity,
                "identifier": item["identifier"],
                "version": version,
                "currentVerification": False,
                "leadingZeroInput": "00000001",
                "leadingZeroMatchCount": len(zeros["data"]["items"]),
                "emptySubsetDoesNotEstablishNonexistence": True,
            }
        )
        response = await http.get(
            "/api/v1/companies",
            params={"q": "HONG KONG", "view": "archive", "limit": 1},
        )
        response.raise_for_status()
        archive = response.json()
        assert archive["meta"]["view"] == "archive"
        cases.append(
            {
                "task": "company_archive_separation",
                "state": "accepted",
                "view": "archive",
                "version": archive["meta"].get("version"),
                "officialVersion": version,
                "identityJoinByNamePerformed": False,
            }
        )
        if args.require_current:
            options = await http.get("/api/v1/resources/" + WORKBOOK + "/schema")
            options.raise_for_status()
            options = options.json()
            assert options["selectionRequired"] == "sheet"
            assert (
                options["capabilities"]["operations"]["records"]["state"] == "available"
            )
            sheet_options = next(
                group for group in options["selections"] if group["kind"] == "sheet"
            )
            assert sheet_options["totalOptions"] == 84
            assert all(
                option["state"] == "unverified" for option in sheet_options["options"]
            )
        query = {"sheet": "E101e", "limit": 3}
        response = await http.post(
            "/api/v1/resources/" + WORKBOOK + "/query", json=query
        )
        response.raise_for_status()
        workbook = response.json()
        native = await call(
            "hk_resource_query",
            {"resourceId": WORKBOOK, **query, "version": workbook["meta"]["version"]},
        )
        assert (
            native["data"] == workbook["data"]
            and native["meta"]["total"] == workbook["meta"]["total"]
        )
        assert workbook["schema"]["sheet"] == "E101e"
        assert workbook["quality"]["semanticVerification"] == "not_performed"
        assert workbook["quality"]["fieldUnitsAnnotated"] is False
        cases.append(
            {
                "task": "explicit_historical_workbook_sheet",
                "state": "accepted",
                "httpMcpParity": True,
                "resourceId": WORKBOOK,
                "sheet": "E101e",
                "version": workbook["meta"]["version"],
                "sourceRows": workbook["meta"]["total"],
                "scope": "Selected raw historical grid includes published 2006/2011/2016 columns; no normalized housing-series or all-sheet qualification.",
                "units": "unknown_unconverted",
                "totalWorkbookSheets": 84,
            }
        )
    report = {
        "scope": (
            "production_current_contract_and_inherited_services"
            if args.require_current
            else "production_inherited_services_only_not_new_code_adoption"
        ),
        "noModelCalls": True,
        "collectionStarted": False,
        "cases": cases,
    }
    Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://mcp.hk")
    parser.add_argument("--require-current", action="store_true")
    parser.add_argument("--out", required=True)
    asyncio.run(run(parser.parse_args()))
