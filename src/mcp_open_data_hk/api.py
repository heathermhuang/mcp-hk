"""Public read-only HTTP and remote MCP application."""

import os
import time
import uuid
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import server as catalogue
from .contracts import (
    DomainError,
    PlateComparablesQuery,
    PlateSearchQuery,
    RestaurantQuery,
)
from .services import get_service


def create_app(service=None):
    service = service or get_service()
    mcp = catalogue.create_server(service)
    mcp_app = mcp.http_app(path="/mcp", stateless_http=True)

    @asynccontextmanager
    async def lifespan(app):
        async with mcp_app.lifespan(app):
            yield

    app = FastAPI(title="mcp.hk HTTP API", version="0.1.0", lifespan=lifespan)
    app.state.service = service
    app.state.mcp = mcp
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "MCP-Protocol-Version", "Mcp-Session-Id"],
        expose_headers=["MCP-Protocol-Version", "Mcp-Session-Id"],
    )
    buckets = OrderedDict()
    hosts = set(
        os.environ.get(
            "MCP_HK_ALLOWED_HOSTS", "mcp.hk,localhost,127.0.0.1,testserver"
        ).split(",")
    )
    origins = set(
        os.environ.get(
            "MCP_HK_ALLOWED_ORIGINS",
            "https://mcp.hk,http://localhost:8000,http://127.0.0.1:8000",
        ).split(",")
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        edge_mode = os.environ.get("MCP_HK_EDGE_MODE") == "true"
        if edge_mode:
            from .operations import authorized

            if not authorized("Bearer " + request.headers.get("x-mcp-edge-token", "")):
                return JSONResponse(
                    {"error": {"code": "INVALID_EDGE"}}, status_code=403
                )
        host = request.url.hostname
        if host not in hosts:
            return JSONResponse(
                {"error": {"code": "INVALID_HOST", "message": "Host not allowed"}},
                status_code=403,
            )
        if (
            request.url.path.startswith("/mcp")
            and request.headers.get("origin")
            and request.headers["origin"] not in origins
        ):
            return JSONResponse(
                {"error": {"code": "INVALID_ORIGIN", "message": "Origin not allowed"}},
                status_code=403,
            )
        try:
            length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"error": {"code": "INVALID_BODY"}}, status_code=400)
        if length > 65536:
            return JSONResponse({"error": {"code": "BODY_TOO_LARGE"}}, status_code=413)
        # Enforce the same cap for chunked bodies and dishonest Content-Length.
        if request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 65536:
                    return JSONResponse(
                        {"error": {"code": "BODY_TOO_LARGE"}}, status_code=413
                    )
            request._body = bytes(body)
        if not edge_mode and request.url.path.startswith(("/api/", "/mcp")):
            now = time.monotonic()
            ip = request.client.host if request.client else "unknown"
            kind = (
                "address" if request.url.path.startswith("/api/v1/addresses") else "all"
            )
            for bucket, limit in [
                ("all", 60),
                *([(kind, 10)] if kind == "address" else []),
            ]:
                key = (ip, bucket)
                start, count = buckets.get(key, (now, 0))
                if now - start >= 60:
                    start, count = now, 0
                if count >= limit:
                    return JSONResponse(
                        {
                            "error": {
                                "code": "RATE_LIMITED",
                                "message": "Try again shortly",
                            }
                        },
                        status_code=429,
                        headers={"Retry-After": str(max(1, int(60 - (now - start))))},
                    )
                buckets[key] = (start, count + 1)
                buckets.move_to_end(key)
            while len(buckets) > 10000:
                buckets.popitem(last=False)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
        )
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "requestId": uuid.uuid4().hex,
                }
            },
            status_code=exc.status,
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": "INVALID_QUERY",
                    "message": "Query parameters do not match the documented contract",
                    "requestId": uuid.uuid4().hex,
                }
            },
            status_code=400,
        )

    @app.get("/healthz")
    def health():
        return {"status": "ok"}

    @app.get("/readyz")
    def ready():
        state = service.status()
        return JSONResponse(state, status_code=200 if state["ready"] else 503)

    @app.get("/api/v1/status")
    def status():
        return service.status()

    @app.get("/api/v1/packs")
    def packs():
        """Queryable packs, including independent external providers."""
        return service.packs()

    @app.get("/api/v1/plates/search")
    async def plate_search(query: Annotated[PlateSearchQuery, Query()]):
        """Historical Plate.hk auction records; exact match by default."""
        return await service.plates.search(query)

    @app.get("/api/v1/plates/comparables")
    async def plate_comparables(query: Annotated[PlateComparablesQuery, Query()]):
        """Historical structural comparisons, never a current valuation."""
        return await service.plates.comparables(query)

    @app.get("/api/v1/plates/datasets")
    async def plate_datasets():
        """Plate.hk coverage and source publication date; counts overlap with all."""
        return await service.plates.query("datasets")

    @app.get("/api/v1/addresses/search")
    async def addresses(
        q: str = Query(min_length=1, max_length=200),
        limit: int = Query(default=5, ge=1, le=10),
        lang: Literal["en", "zh-Hant"] = "en",
    ):
        return await service.addresses(q, limit)

    @app.get("/api/v1/addresses/{geoAddress}")
    async def address(geoAddress: str):
        return await service.addresses(geoAddress, 1, geo=True)

    @app.get("/api/v1/restaurants")
    def restaurants(query: Annotated[RestaurantQuery, Query()]):
        return service.restaurants(query)

    @app.get("/api/v1/restaurants/{licenceId}")
    def restaurant(licenceId: str):
        return service.restaurant(licenceId)

    @app.get("/api/v1/districts")
    def districts():
        return service.districts()

    @app.get("/api/v1/districts/{districtId}/statistics")
    def statistics(
        districtId: str,
        year: int | None = Query(default=None, ge=2000, le=2100),
        requireFresh: bool = False,
    ):
        return service.statistics(districtId, year, requireFresh)

    @app.get("/api/v1/datasets")
    async def datasets(
        q: str = Query(default="*:*", max_length=200),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=10000),
        lang: Literal["en", "zh-Hant"] = "en",
    ):
        payload = await catalogue.search_datasets(
            q, limit, offset, "tc" if lang == "zh-Hant" else "en"
        )
        service.store.check("catalogue")
        return service.envelope(
            {
                "items": [
                    {**r, "capability": "catalogue_only"} for r in payload["results"]
                ]
            },
            "catalogue",
            total=payload["count"],
            truncated=payload["has_more"],
        )

    @app.get("/api/v1/datasets/{datasetId}")
    async def dataset(datasetId: str, lang: Literal["en", "zh-Hant"] = "en"):
        payload = await catalogue.get_dataset_details(
            datasetId, "tc" if lang == "zh-Hant" else "en"
        )
        service.store.check("catalogue")
        return service.envelope(
            {**payload, "capability": "catalogue_only"}, "catalogue"
        )

    from .resource_api import register_http

    register_http(app, service.resources)
    from .operations import register_operations

    register_operations(app, service)
    web = Path(__file__).parent / "web"
    if web.exists():

        @app.get("/", include_in_schema=False)
        @app.get("/demo", include_in_schema=False)
        @app.get("/sources", include_in_schema=False)
        @app.get("/connect", include_in_schema=False)
        @app.get("/plates", include_in_schema=False)
        def homepage():
            return FileResponse(web / "index.html")

        @app.get("/coverage", include_in_schema=False)
        @app.get("/data", include_in_schema=False)
        def coverage_page():
            return FileResponse(web / "coverage.html")

        app.mount("/assets", StaticFiles(directory=web), name="assets")
    # The MCP app owns /mcp. Mount at root last to avoid /mcp/mcp and keep REST routes.
    app.mount("/", mcp_app)
    return app


def main():
    import uvicorn

    uvicorn.run(
        create_app(),
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        access_log=False,
        proxy_headers=False,
    )
