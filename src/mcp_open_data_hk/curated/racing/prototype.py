"""Working local-only racing explorer, REST and MCP. Never mounted by production."""

import argparse
import csv
import hashlib
import io
import ipaddress
import json
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastmcp import FastMCP
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .policy import RacingRejected, canonical
from .prototype_store import PilotCollector, PrototypeStore

WEB = Path(__file__).parent
PUBLIC_WEB = WEB.parents[1] / "web"


class PrototypeReader:
    def __init__(self, store):
        self.store = store

    def envelope(self, snapshot, data):
        return {
            "data": data,
            "meta": {
                "version": snapshot["version"],
                "scope": "private_development",
                "sourceLicence": "unverified",
                "publicRedistributionEnabled": False,
            },
            "coverage": snapshot["coverage"],
            "provenance": snapshot["provenance"],
        }

    def status(self):
        return {
            "data": {
                "state": "private_development",
                "sourceLicence": "unverified",
                "publicRedistributionEnabled": False,
                "collectionOnRead": False,
                "scheduled": False,
                "meetings": self.store.meetings(),
            }
        }

    def races(self, version=None, day=None, venue=None):
        snapshot = self.store.read(version, day, venue)
        races = [
            {
                **{k: v for k, v in r.items() if k not in {"results", "provenance"}},
                "runnerCount": len(r["results"]),
            }
            for r in snapshot["races"]
        ]
        return self.envelope(snapshot, {"meeting": snapshot["meeting"], "items": races})

    def results(self, race_id, version):
        snapshot = self.store.read(version)
        found = next((r for r in snapshot["races"] if r["id"] == race_id), None)
        if found is None:
            raise RacingRejected("DEVELOPMENT_RACE_NOT_FOUND")
        return self.envelope(snapshot, found)

    def profile(self, participant_id, version):
        snapshot = self.store.read(version)
        appearances, identity = [], None
        for race in snapshot["races"]:
            for result in race["results"]:
                for kind in ("horse", "jockey", "trainer"):
                    if result[kind]["id"] == participant_id:
                        identity = dict(result[kind], kind=kind)
                        appearances.append(
                            {
                                "raceId": race["id"],
                                "raceNumber": race["number"],
                                "horse": result["horse"],
                                "placing": result["placing"],
                                "status": result["status"],
                                "timeSeconds": result["timeSeconds"],
                            }
                        )
        if identity is None:
            raise RacingRejected("DEVELOPMENT_PARTICIPANT_NOT_FOUND")
        return self.envelope(
            snapshot,
            {
                "identity": identity,
                "coverage": "identity_and_results_in_this_imported_meeting_only",
                "appearances": appearances,
            },
        )

    def archive(self, version, race_id):
        payload = self.results(race_id, version)
        fields = (
            "horseNumber",
            "placing",
            "status",
            "participantId",
            "draw",
            "timeSeconds",
            "weightLb",
            "bodyWeightLb",
            "winOddsFinal",
            "marginRaw",
        )
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(
            stream, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator="\n"
        )
        writer.writeheader()
        for row in payload["data"]["results"]:
            writer.writerow(
                {
                    k: (
                        "'" + str(row[k])
                        if str(row[k])
                        .lstrip()
                        .startswith(("=", "+", "-", "@", "\t", "\r"))
                        else row[k]
                    )
                    for k in fields
                }
            )
        files = {
            "results.json": canonical(payload),
            "results.csv": stream.getvalue().encode("utf-8-sig"),
            "NOTICE.txt": b"Private development copy. Source: HKJC public factual results. Source licence and public redistribution rights unverified. No commentary or media included.\n",
        }
        manifest = {
            "version": version,
            "raceId": race_id,
            "scope": "private_development",
            "sourceLicence": "unverified",
            "files": {
                name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
                for name, body in files.items()
            },
        }
        files["manifest.json"] = canonical(manifest)
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, body in sorted(files.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, body)
        if len(output.getvalue()) > 2 * 1024 * 1024:
            raise RacingRejected("DEVELOPMENT_OUTPUT_LIMIT")
        return output.getvalue()


def create_app(store):
    reader = PrototypeReader(store)
    mcp = FastMCP("mcp.hk private racing development")

    @mcp.tool()
    async def hk_racing_status() -> dict:
        """Private development coverage, independent of source licensing and public gates."""
        return await run_in_threadpool(reader.status)

    @mcp.tool()
    async def hk_racing_search(
        version: str | None = None, day: str | None = None, venue: str | None = None
    ) -> dict:
        """Read locally imported races. No source request is made."""
        return await run_in_threadpool(reader.races, version, day, venue)

    @mcp.tool()
    async def hk_racing_results(raceId: str, version: str) -> dict:
        """Read real results pinned to one immutable private development snapshot."""
        return await run_in_threadpool(reader.results, raceId, version)

    @mcp.tool()
    async def hk_racing_profile(participantId: str, version: str) -> dict:
        """Participant identity and imported-meeting appearances, not a full HKJC profile."""
        return await run_in_threadpool(reader.profile, participantId, version)

    mcp_app = mcp.http_app(path="/mcp", stateless_http=True)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_app.lifespan(app):
            yield

    app = FastAPI(
        title="Private racing prototype",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.state.mcp = mcp
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["127.0.0.1", "localhost", "[::1]", "testserver"],
    )

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        origin_header = request.headers.get("origin")
        origin = urlsplit(origin_header or "")
        try:
            local = ipaddress.ip_address(request.client.host).is_loopback
        except (ValueError, AttributeError):
            local = False
        if not local or (
            origin_header is not None
            and (
                origin.scheme != "http"
                or origin.hostname not in {"127.0.0.1", "localhost", "::1"}
                or origin.netloc != request.headers.get("host")
                or origin.path
                or origin.query
                or origin.fragment
            )
        ):
            return JSONResponse(
                {"error": {"code": "LOCAL_DEVELOPMENT_ONLY"}}, status_code=403
            )
        response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Robots-Tag": "noindex, nofollow",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
            }
        )
        return response

    @app.exception_handler(RacingRejected)
    async def rejected(request, exc):
        return JSONResponse(
            {"error": {"code": str(exc)}},
            status_code=404 if "NOT_FOUND" in str(exc) else 400,
        )

    @app.get("/")
    def index():
        return FileResponse(WEB / "prototype.html")

    @app.get("/docs", include_in_schema=False)
    def docs():
        return HTMLResponse(
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Private racing API</title><link rel="stylesheet" href="/assets/swagger-ui.css"><script src="/assets/swagger-ui-bundle.js" defer></script><script src="/assets/api-docs.js" defer></script></head><body><h1>Private racing REST API</h1><p><a href="/">Return to racing</a> · <a href="/openapi.json">OpenAPI</a></p><p id="docs-status">Loading local API reference…</p><main id="swagger-ui"></main></body></html>'
        )

    @app.get("/assets/{name}")
    def asset(name: str):
        allowed = {
            "prototype.js": WEB / "prototype.js",
            "prototype.css": WEB / "prototype.css",
            "style.css": PUBLIC_WEB / "style.css",
            "swagger-ui.css": PUBLIC_WEB / "swagger-ui.css",
            "swagger-ui-bundle.js": PUBLIC_WEB / "swagger-ui-bundle.js",
            "api-docs.js": PUBLIC_WEB / "api-docs.js",
        }
        if name not in allowed:
            raise RacingRejected("DEVELOPMENT_ASSET_NOT_FOUND")
        return FileResponse(allowed[name])

    @app.get("/api/v1/racing/status")
    def status():
        return reader.status()

    @app.get("/api/v1/racing/races")
    def races(
        version: str | None = Query(None, max_length=100),
        day: str | None = Query(None, max_length=10),
        venue: str | None = Query(None, max_length=2),
    ):
        return reader.races(version, day, venue)

    @app.get("/api/v1/racing/races/{race_id}/results")
    def results(race_id: str, version: str = Query(max_length=100)):
        return reader.results(race_id, version)

    @app.get("/api/v1/racing/participants/{participant_id}")
    def profile(participant_id: str, version: str = Query(max_length=100)):
        return reader.profile(participant_id, version)

    @app.get("/api/v1/racing/exports")
    def export(
        version: str = Query(max_length=100), raceId: str = Query(max_length=200)
    ):
        return Response(
            reader.archive(version, raceId),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="private-racing-results.zip"'
            },
        )

    app.mount("/", mcp_app)
    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database", default=".data/racing-development/prototype.sqlite3"
    )
    sub = parser.add_subparsers(dest="action", required=True)
    collect = sub.add_parser(
        "collect",
        help="Import one completed public meeting privately; cached checkpoint resume",
    )
    collect.add_argument("--date", required=True)
    collect.add_argument("--venue", choices=["HV", "ST"], required=True)
    collect.add_argument(
        "--refresh",
        action="store_true",
        help="Bounded reread creates a new immutable private snapshot; old versions remain readable",
    )
    serve = sub.add_parser(
        "serve", help="Serve imported data on 127.0.0.1 only; never collects on read"
    )
    serve.add_argument("--port", type=int, default=18844)
    args = parser.parse_args()
    store = PrototypeStore(args.database)
    if args.action == "collect":
        snapshot = PilotCollector(store, refresh=args.refresh).collect(
            args.date, args.venue
        )
        print(
            json.dumps(
                {
                    "version": snapshot["version"],
                    "coverage": snapshot["coverage"],
                    "sourceLicence": "unverified",
                    "publicRedistributionEnabled": False,
                }
            )
        )
    else:
        if not 1024 <= args.port <= 65535:
            parser.error("Choose a local port from 1024 to 65535")
        import uvicorn

        uvicorn.run(
            create_app(store),
            host="127.0.0.1",
            port=args.port,
            proxy_headers=False,
            access_log=False,
        )


if __name__ == "__main__":
    main()
