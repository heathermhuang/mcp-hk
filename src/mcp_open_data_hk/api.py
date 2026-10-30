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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from . import server as catalogue
from .contracts import (
    DomainError,
    CompanySearchQuery,
    CompanyHistoryQuery,
    CompanyReadQuery,
    PlateComparablesQuery,
    PlateSearchQuery,
    PropertySearchQuery,
    PropertyBuildingQuery,
    PropertyListingsQuery,
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

    app = FastAPI(
        title="mcp.hk HTTP API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
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
        from .operations import authorized

        body_cap = (
            16 * 1024 * 1024
            if request.url.path == "/__ops/racing"
            and authorized(request.headers.get("authorization"))
            else 65536
        )
        if length > body_cap:
            return JSONResponse({"error": {"code": "BODY_TOO_LARGE"}}, status_code=413)
        # Enforce the same cap for chunked bodies and dishonest Content-Length.
        if request.method in {"POST", "PUT", "PATCH"}:
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > body_cap:
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
        from .racing_service import ingestion_context

        budget = None
        if edge_mode:
            raw = request.headers.get("x-mcp-racing-budget", "")
            if raw and len(raw) <= 4096:
                try:
                    import json

                    value = json.loads(raw)
                    if isinstance(value, dict) and value.get("durable") is True:
                        budget = value
                except ValueError:
                    pass
        context_token = ingestion_context.set(budget)
        try:
            response = await call_next(request)
        finally:
            ingestion_context.reset(context_token)
        if (
            request.url.path.startswith(("/api/v1/resources", "/api/v1/sfc"))
            or request.url.path == "/api/v1/coverage"
        ):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data: https://hk.app/badges/; frame-ancestors 'none'; base-uri 'none'"
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
            headers={"Retry-After": str(exc.retry_after)} if exc.retry_after else None,
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
        from .quality import REVISION

        return {
            "status": "ok",
            "sourceReviewPolicy": REVISION,
            "racingPipeline": "results-r2-v1",
            "racingProfilesPipeline": "profile-observations-r2-v1",
        }

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

    from .hkex_api import register_rest as register_hkex_rest

    from .webb_sdi_api import register_http as register_webb_archive

    register_webb_archive(app, service)
    from .hkex_daily import register_http as register_daily

    register_daily(app, service)
    register_hkex_rest(app, service)

    from .racing_api import register_http as register_racing_http

    register_racing_http(app, service)

    @app.get("/api/v1/companies")
    async def company_search(query: Annotated[CompanySearchQuery, Query()]):
        return await service.companies.query("search", query.model_dump())

    @app.get("/api/v1/companies/notice")
    def company_notice():
        return FileResponse(
            Path(__file__).with_name("webb-site-NOTICE.txt"), media_type="text/plain"
        )

    @app.get("/api/v1/companies/updates/status")
    async def official_company_status():
        return await service.companies.query("status", {"view": "latest_observed"})

    @app.get("/api/v1/companies/{entity_id}")
    async def company_get(entity_id: str, query: Annotated[CompanyReadQuery, Query()]):
        return await service.companies.query(
            "get",
            query.model_dump(),
            entity_id=int(entity_id) if entity_id.isdigit() else entity_id,
        )

    @app.get("/api/v1/companies/{entity_id}/{family}")
    async def company_history(
        entity_id: str,
        family: Literal[
            "names", "officers", "licences", "licence_relationships", "addresses"
        ],
        query: Annotated[CompanyHistoryQuery, Query()],
    ):
        return await service.companies.query(
            "related",
            query.model_dump(),
            entity_id=int(entity_id) if entity_id.isdigit() else entity_id,
            family=family,
        )

    @app.get("/api/v1/properties/search")
    async def property_search(query: Annotated[PropertySearchQuery, Query()]):
        return await service.properties.search(query)

    @app.get("/api/v1/properties/building")
    async def property_building(query: Annotated[PropertyListingsQuery, Query()]):
        return await service.properties.building(query)

    @app.get("/api/v1/properties/price-history")
    async def property_history(query: Annotated[PropertyBuildingQuery, Query()]):
        return await service.properties.history(query)

    @app.get("/api/v1/properties/coverage")
    async def property_coverage():
        return await service.properties.query("coverage")

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

    from .sfc import register_http as register_sfc_http

    register_sfc_http(app, service)

    from .resource_api import register_http

    register_http(app, service.resources)
    from .operations import register_operations

    register_operations(app, service)
    web = Path(__file__).parent / "web"
    if web.exists():
        from . import discovery
        from .agent_discovery import (
            LINKS,
            agent_documents,
            markdown_document,
            markdown_path,
            prefers_markdown,
        )
        from .discovery import INDEX, locale, public_paths, render_page, text_response

        documents = agent_documents(discovery)
        markdown_pages = {
            markdown_path(path): path
            for path in public_paths()
            if not discovery.content()["pages"][path].get("noindex")
        }

        def public_page(request: Request):
            alias = request.url.path in markdown_pages
            path = markdown_pages.get(request.url.path, request.url.path)
            lang = locale(request.query_params.get("lang"))
            filtered = path in {
                "/playground",
                "/",
                "/coverage",
                "/companies",
                "/hkex",
                "/sfc",
            } and any(
                key != "lang" and not key.startswith("utm_")
                for key in request.query_params
            )
            noindex = alias or filtered or path in {"/terms", "/privacy"}
            markdown = path not in {"/terms", "/privacy"} and (
                alias or prefers_markdown(request.headers.get("accept", ""))
            )
            return Response(
                (
                    markdown_document(discovery, path, lang, filtered)
                    if markdown
                    else render_page(path, lang, filtered)
                ),
                media_type="text/markdown" if markdown else "text/html",
                headers={
                    "Content-Language": lang,
                    "X-Robots-Tag": "noindex, follow" if noindex else INDEX,
                    "Vary": "Accept",
                    "Link": LINKS,
                },
            )

        for path in public_paths() + list(markdown_pages):
            app.add_api_route(
                path, public_page, methods=["GET", "HEAD"], include_in_schema=False
            )

        def discovery_file(request: Request):
            body, media_type = documents.get(request.url.path) or text_response(
                request.url.path
            )
            return Response(
                body,
                media_type=media_type,
                headers={"Link": LINKS, "Access-Control-Allow-Origin": "*"},
            )

        for path in ["/robots.txt", "/sitemap.xml", "/llms.txt", *documents]:
            app.add_api_route(
                path, discovery_file, methods=["GET", "HEAD"], include_in_schema=False
            )

        @app.get("/data", include_in_schema=False)
        def data_alias(request: Request):
            suffix = "?" + request.url.query if request.url.query else ""
            return RedirectResponse("/coverage" + suffix, status_code=308)

        @app.get("/docs", include_in_schema=False)
        def api_docs(request: Request):
            lang = locale(request.query_params.get("lang"))
            filtered = any(key in request.query_params for key in ("q", "group"))
            return Response(
                discovery.render_api_docs(lang, filtered),
                media_type="text/html",
                headers={
                    "Content-Language": lang,
                    "X-Robots-Tag": "noindex, follow" if filtered else INDEX,
                },
            )

        @app.get("/redoc", include_in_schema=False)
        def docs_alias():
            return RedirectResponse("/docs", status_code=308)

        app.mount("/assets", StaticFiles(directory=web), name="assets")
    from fastapi.routing import APIRoute

    groups = [
        ("/api/v1/catalogue", "Discovery"),
        ("/api/v1/resources", "Resource records"),
        ("/api/v1/companies", "Companies"),
        ("/api/v1/properties", "Properties"),
        ("/api/v1/plates", "Plates"),
        ("/api/v1/addresses", "Addresses, restaurants and districts"),
        ("/api/v1/restaurants", "Addresses, restaurants and districts"),
        ("/api/v1/districts", "Addresses, restaurants and districts"),
    ]
    app.openapi_tags = [
        {"name": name}
        for name in dict.fromkeys([name for _, name in groups] + ["Service status"])
    ]
    for route in app.routes:
        if isinstance(route, APIRoute) and route.include_in_schema:
            route.tags = [
                next(
                    (name for prefix, name in groups if route.path.startswith(prefix)),
                    "Service status",
                )
            ]
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
