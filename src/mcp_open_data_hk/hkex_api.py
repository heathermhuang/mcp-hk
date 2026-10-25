"""REST/MCP registrations share one normalized, independently gated adapter."""

from typing import Annotated, Literal

from fastapi import Path, Query

from .hkex import DetailQuery, DisclosuresQuery, IssuerQuery


def register_rest(app, service):
    adapter = service.hkex

    @app.get("/api/v1/hkex/status", tags=["HKEX DI"])
    async def hkex_status():
        return await adapter.query("status")

    @app.get("/api/v1/hkex/browser/status", include_in_schema=False)
    async def browser_status():
        return await adapter.query("status", mode="browser")

    @app.get("/api/v1/hkex/browser/issuers", include_in_schema=False)
    async def browser_issuers(query: Annotated[IssuerQuery, Query()]):
        return await adapter.query("issuers", query.model_dump(), mode="browser")

    @app.get("/api/v1/hkex/browser/disclosures", include_in_schema=False)
    async def browser_disclosures(query: Annotated[DisclosuresQuery, Query()]):
        return await adapter.query("disclosures", query.model_dump(), mode="browser")

    @app.get("/api/v1/hkex/browser/disclosures/{filing_id}", include_in_schema=False)
    async def browser_disclosure(
        filing_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,80}$")],
        version: Annotated[str, Query(pattern=r"^hkex-[a-f0-9]{32}$")],
    ):
        query = DetailQuery(filingId=filing_id, version=version)
        return await adapter.query("disclosure", query.model_dump(), mode="browser")

    @app.get("/api/v1/hkex/issuers", include_in_schema=adapter.enabled("rest"))
    async def hkex_issuers(query: Annotated[IssuerQuery, Query()]):
        return await adapter.query("issuers", query.model_dump())

    @app.get("/api/v1/hkex/disclosures", include_in_schema=adapter.enabled("rest"))
    async def hkex_disclosures(query: Annotated[DisclosuresQuery, Query()]):
        return await adapter.query("disclosures", query.model_dump())

    @app.get(
        "/api/v1/hkex/disclosures/{filing_id}",
        include_in_schema=adapter.enabled("rest"),
    )
    async def hkex_disclosure(
        filing_id: Annotated[str, Path(pattern=r"^[A-Za-z0-9_-]{1,80}$")],
        version: Annotated[str, Query(pattern=r"^hkex-[a-f0-9]{32}$")],
    ):
        query = DetailQuery(filingId=filing_id, version=version)
        return await adapter.query("disclosure", query.model_dump())


def register_mcp(server, current):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_status() -> dict:
        """HKEX DI source qualification and accepted window status. Starts no collection. Disclosures are dated statements, not current holdings or executed trades."""
        return await current().hkex.query("status", mode="mcp")

    if not current().hkex.enabled("mcp"):
        return

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_issuers(
        stockCode: str | None = None,
        q: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Search exact five-digit stock code or literal issuer prefix within an accepted source version. Stock code/security class and issuer identity differ."""
        query = IssuerQuery(
            stockCode=stockCode, q=q, limit=limit, cursor=cursor, version=version
        )
        return await current().hkex.query("issuers", query.model_dump(), mode="mcp")

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_disclosures(
        issuerId: str,
        start: str,
        end: str,
        basis: Literal["filed", "published", "event"],
        channel: Literal["dion", "pre_dion"] = "dion",
        form: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read a bounded accepted disclosure window; end date is exclusive in Hong Kong time. Pin version. Event-date coverage never establishes filing-date completeness. Originals, amendments and withdrawals remain visible."""
        query = DisclosuresQuery(
            issuerId=issuerId,
            start=start,
            end=end,
            basis=basis,
            channel=channel,
            form=form,
            limit=limit,
            cursor=cursor,
            version=version,
        )
        return await current().hkex.query("disclosures", query.model_dump(), mode="mcp")

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_disclosure(filingId: str, version: str) -> dict:
        """Read an exact filing serial and revision trail in its pinned accepted version. Long/short/deemed interests remain separate; unknown source dates stay unknown."""
        query = DetailQuery(filingId=filingId, version=version)
        return await current().hkex.query("disclosure", query.model_dump(), mode="mcp")
