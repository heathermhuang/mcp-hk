"""Company tool registration reuses exactly the public HTTP service contracts."""

from typing import Literal

from .contracts import CompanySearchQuery, CompanyHistoryQuery, CompanyReadQuery


def register_company_tools(server, current):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_search(
        groupBy: Literal["organisation"] | None = None,
        q: str | None = None,
        namespace: str | None = None,
        value: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
        view: Literal["archive", "latest_observed"] = "archive",
        requireFresh: bool = False,
    ) -> dict:
        """Search organisation name prefixes or explicit identifiers. view=archive selects Enigma; view=latest_observed selects the separately maintained official Registry subset (cr:local:brn, cr:foreign:brn, cr:mlr). Historical observations, not current company verification. Preserve source IDs and leading zeros. Multiple name facts can match one organisation. Pass returned version to detail/history reads and the signed cursor to the next page."""
        query = CompanySearchQuery(
            groupBy=groupBy,
            q=q,
            namespace=namespace,
            value=value,
            limit=limit,
            cursor=cursor,
            version=version,
            view=view,
            requireFresh=requireFresh,
        )
        return await current().companies.query("search", query.model_dump())

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_get(
        entityId: int | str,
        version: str | None = None,
        view: Literal["archive", "latest_observed"] = "archive",
        requireFresh: bool = False,
    ) -> dict:
        """Read a source-linked organisation. For view=latest_observed pass the exact string entityId from official search; detail returns dated events/addresses/lender records with raw source fields. An incorporation number is not a verified BRN. Pin the search result's version; this archive does not prove current registration or trading status."""
        query = CompanyReadQuery(version=version, view=view, requireFresh=requireFresh)
        return await current().companies.query(
            "get", query.model_dump(), entity_id=entityId
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_updates_status() -> dict:
        """Read accepted official subset coverage, missing weeks, address denominator, source cutoff, bounded schedule and recent production ingestion receipts. No live crawl is started."""
        return await current().companies.query("status", {"view": "latest_observed"})

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_address_history(
        entityId: str,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read version-pinned official address observation occurrences by exact company BRN namespace. Dates are observations, not effective move dates. Unchanged checks are separate from address changes. No collection is started."""
        query = CompanyHistoryQuery(
            limit=limit, cursor=cursor, version=version, view="latest_observed"
        )
        return await current().companies.query(
            "related", query.model_dump(), entity_id=entityId, family="addresses"
        )

    async def history(entityId, family, limit, cursor, version, asOf):
        query = CompanyHistoryQuery(
            limit=limit, cursor=cursor, version=version, asOf=asOf
        )
        return await current().companies.query(
            "related", query.model_dump(), entity_id=entityId, family=family
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_name_history(
        entityId: int,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read original and former bilingual source-name facts; unknown start dates stay unknown. Pin the selected version; ordering is by stable fact ID."""
        return await history(entityId, "names", limit, cursor, version, None)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_officers(
        entityId: int,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
        asOf: str | None = None,
    ) -> dict:
        """Read archival officer appointments with original roles, source IDs and date precision. Conflicting/unknown bounds are preserved; exact asOf is unsupported. This is not a current ownership graph."""
        return await history(entityId, "officers", limit, cursor, version, asOf)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_licences(
        entityId: int,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read original corporate SFC activity/licence observations; absence of an end date does not prove current licensing."""
        return await history(entityId, "licences", limit, cursor, version, None)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_company_licence_relationships(
        entityId: int,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read archived SFC staff/activity relationships: source role 0=representative, 1=responsible officer. Licence relationships and corporate appointments are separate facts."""
        return await history(
            entityId, "licence_relationships", limit, cursor, version, None
        )
