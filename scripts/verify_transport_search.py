"""Rehearse bilingual bus discovery and real Citybus joins over HTTP and MCP.

--local runs this checkout with a temporary database and public catalogue
metadata. It does not deploy, seed or change production.
"""

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

import httpx
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


def identities(payload):
    return [
        (r["route"]["routeId"], r["board"]["stopId"], r["alight"]["stopId"])
        for r in payload["data"]["items"]
    ]


async def main(args):
    origin = args.base_url.rstrip("/")
    if args.local:
        dataset = "ctb-eta-transport-realtime-eta"
        async with httpx.AsyncClient(timeout=120) as public:
            responses = await asyncio.gather(
                public.get(origin + "/api/v1/catalogue/datasets/" + dataset),
                public.get(
                    origin
                    + "/api/v1/catalogue/datasets/"
                    + dataset
                    + "/resources?limit=10"
                ),
            )
        for response in responses:
            response.raise_for_status()
        service = Service(Store(str(Path(args.tempdir) / "rehearsal.sqlite3")))
        service.resources.catalogue.publish(
            [responses[0].json()], responses[1].json()["items"], {}
        )
        app = create_app(service)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        )
        mcp = Client(app.state.mcp)
    else:
        client = httpx.AsyncClient(base_url=origin, timeout=120)
        mcp = Client(origin + "/mcp", timeout=120)
    async with client, mcp:
        english = await client.get(
            "/api/v1/transport/stops", params={"q": "Lan Kwai Fong"}
        )
        english.raise_for_status()
        zh = await mcp.call_tool("hk_transport_stop_search", {"q": "蘭桂坊"})
        chinese = json.loads(zh.content[0].text)
        assert {r["stopId"] for r in english.json()["data"]["items"]} == {
            r["stopId"] for r in chinese["data"]["items"]
        }
        search = {
            "origin": "Lan Kwai Fong",
            "destination": "Seymour Road",
            "operator": "CTB",
            "limit": 3,
        }
        response = await client.post("/api/v1/transport/journeys", json=search)
        response.raise_for_status()
        journey = response.json()
        call = await mcp.call_tool(
            "hk_transport_journey", {**search, "includeArrivals": False}
        )
        reference = json.loads(call.content[0].text)
        reference_http = await client.post(
            "/api/v1/transport/journeys", json={**search, "includeArrivals": False}
        )
        reference_http.raise_for_status()
        assert identities(reference_http.json()) == identities(reference)
        live_call = await mcp.call_tool("hk_transport_journey", search)
        mcp_journey = json.loads(live_call.content[0].text)
        for actual in (journey, mcp_journey):
            coverage = actual["data"]["coverage"]
            assert coverage["candidate"] == coverage["checked"] + coverage["unchecked"]
            assert coverage["failed"] <= coverage["checked"]
            assert coverage["sourceRequests"] <= coverage["requestLimit"] == 64
            comparison = actual["data"]["departureComparison"]
            assert (
                comparison["scope"]
                == "earliest_reported_departure_among_checked_candidates"
            )
            assert comparison["globallyEarliest"] is False
            if coverage["failed"] or coverage["unchecked"]:
                assert coverage["complete"] is False
        candidates = journey["data"]["items"]
        verified = [
            r
            for r in candidates
            if r["route"]["route"] == "12" and r["arrivalStatus"] == "live"
        ]
        receipt = {
            "scope": "local_candidate_live_sources" if args.local else "production",
            "httpMcpReferenceParity": True,
            "bilingualSearchParity": True,
            "indexVersion": journey["meta"]["indexVersion"],
            "provenance": journey["provenance"],
            "candidates": candidates,
            "httpCoverage": journey["data"]["coverage"],
            "mcpCoverage": mcp_journey["data"]["coverage"],
            "departureComparison": journey["data"]["departureComparison"],
            "verifiedRoute12": bool(verified),
        }
        Path(args.out).write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            json.dumps(
                {
                    "scope": receipt["scope"],
                    "verifiedRoute12": bool(verified),
                    "candidates": [
                        {
                            "route": r["route"]["route"],
                            "status": r["arrivalStatus"],
                            "operatorBoardStopId": r.get("operatorBoardStopId"),
                            "operatorAlightStopId": r.get("operatorAlightStopId"),
                            "operatorStopCount": r.get("operatorStopCount"),
                            "error": r.get("arrivalError"),
                        }
                        for r in candidates
                    ],
                },
                ensure_ascii=False,
            )
        )
        if not any(r["arrivalStatus"] == "live" for r in candidates):
            raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://mcp.hk")
    parser.add_argument("--local", action="store_true")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="mcp-hk-bus-rehearsal-") as folder:
        args.tempdir = folder
        asyncio.run(main(args))
