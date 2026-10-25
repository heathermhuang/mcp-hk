"""The archived data is independently available from the fresh HKEX source gate."""

from pathlib import Path
from typing import Annotated

from fastapi import Query
from fastapi.responses import FileResponse

from .webb_sdi import IssuerQuery, DisclosureQuery


def register_http(app, service):
    @app.get("/api/v1/hkex/archive/status")
    async def archive_status():
        return await service.webb_sdi.query("status")

    @app.get("/api/v1/hkex/archive/notice")
    def archive_notice():
        return FileResponse(
            Path(__file__).with_name("webb-site-NOTICE.txt"), media_type="text/plain"
        )

    @app.get(
        "/api/v1/hkex/archive/issuers", include_in_schema=service.webb_sdi.configured
    )
    async def archive_issuers(query: Annotated[IssuerQuery, Query()]):
        return await service.webb_sdi.query("issuers", query.model_dump())

    @app.get(
        "/api/v1/hkex/archive/disclosures",
        include_in_schema=service.webb_sdi.configured,
    )
    async def archive_disclosures(query: Annotated[DisclosureQuery, Query()]):
        return await service.webb_sdi.query("disclosures", query.model_dump())

    @app.get(
        "/api/v1/hkex/archive/disclosures/{filing_id}",
        include_in_schema=service.webb_sdi.configured,
    )
    async def archive_disclosure(
        filing_id: str, version: str = Query(pattern=r"^webb-sdi-[A-Za-z0-9._-]{1,80}$")
    ):
        return await service.webb_sdi.query(
            "disclosure", {"version": version}, filing_id=filing_id
        )


def register_mcp(server, current):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_archive_status() -> dict:
        """Read the historical Webb Form3A archive's exact source counts/dates/readiness. Separate from fresh HKEX collection. Starts no collection."""
        return await current().webb_sdi.query("status")

    if not current().webb_sdi.configured:
        return

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_archive_issuers(
        stockCode: str | None = None,
        q: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Find historical Webb source issuers by stock code or literal name prefix. Codes can belong to different issuers over time. Pin the returned archive version; original data is dated, not current verification."""
        query = IssuerQuery(
            stockCode=stockCode, q=q, limit=limit, cursor=cursor, version=version
        )
        return await current().webb_sdi.query("issuers", query.model_dump())

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_archive_disclosures(
        issuerId: str,
        start: str | None = None,
        end: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read real archived Form3A records by exact returned Webb issuer ID. Optional event window is at most31 days, end exclusive. It is not a complete filing-date inventory. Preserve unknown dates, source numeric strings and unresolved amendments."""
        query = DisclosureQuery(
            issuerId=issuerId,
            start=start,
            end=end,
            limit=limit,
            cursor=cursor,
            version=version,
        )
        return await current().webb_sdi.query("disclosures", query.model_dump())

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_archive_disclosure(filingId: str, version: str) -> dict:
        """Read an exact archived Webb disclosure with before/after long/short positions, capacity/reason codes and amendment links. Source FLOAT/DOUBLE values do not establish exact original decimal input, executed trades or current holdings."""
        return await current().webb_sdi.query(
            "disclosure", {"version": version}, filing_id=filingId
        )
