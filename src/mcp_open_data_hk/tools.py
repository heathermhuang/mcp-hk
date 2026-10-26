"""Queryable government and independent data packs alongside catalogue tools."""

from typing import Literal

from .contracts import (
    PlateComparablesQuery,
    PlateDataset,
    PlateSearchQuery,
    PropertySearchQuery,
    PropertyBuildingQuery,
    PropertyListingsQuery,
    RestaurantQuery,
)
from .services import get_service


def register_data_tools(server, service=None):
    def current():
        return service or get_service()

    from .resource_api import register_mcp

    register_mcp(server, current)

    from .sfc import register_mcp as register_sfc_mcp

    register_sfc_mcp(server, current)

    from .hkex_api import register_mcp as register_hkex_mcp

    register_hkex_mcp(server, current)

    from .webb_sdi_api import register_mcp as register_webb_archive

    register_webb_archive(server, current)

    from .hkex_daily import register_mcp as register_daily

    register_daily(server, current)

    from .racing_api import register_mcp as register_racing_mcp

    register_racing_mcp(server, current)

    from .company_api import register_company_tools

    from .companies import settings

    if settings() is not None:
        register_company_tools(server, current)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_address_search(
        q: str, limit: int = 5, lang: Literal["en", "zh-Hant"] = "en"
    ) -> dict:
        """Resolve a Hong Kong address. Choose a candidate; scores are source rankings, not probabilities."""
        return await current().addresses(q, limit)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_address_get(geoAddress: str) -> dict:
        """Look up a 19-character GeoAddress returned by ALS."""
        return await current().addresses(geoAddress, 1, geo=True)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_restaurant_search(
        q: str = "",
        district: str | None = None,
        licenceType: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radiusM: int | None = None,
        limit: int = 20,
        cursor: str | None = None,
        includeSummary: bool = False,
        requireFresh: bool = False,
        lang: Literal["en", "zh-Hant"] = "en",
    ) -> dict:
        """Search accepted FEHD licences. Distances are straight-line; summary counts cover all matches, not one page."""
        params = {
            key: value
            for key, value in locals().items()
            if key in RestaurantQuery.model_fields
        }
        return current().restaurants(RestaurantQuery(**params))

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_restaurant_get(licenceId: str) -> dict:
        """Retrieve a licence in the current accepted snapshot; listing does not prove current trading status."""
        return current().restaurant(licenceId)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_district_list() -> dict:
        """List the 18 administrative districts with bilingual names and stable IDs."""
        return current().districts()

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_district_statistics(
        districtId: str, year: int | None = None, requireFresh: bool = False
    ) -> dict:
        """Published district-wide population, area, density and reference year; never radius-level population."""
        return current().statistics(districtId, year, requireFresh)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_source_status() -> dict:
        """Source freshness and failure receipts, independently of service availability."""
        return current().status()

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    def hk_data_packs() -> dict:
        """Discover queryable packs, providers and HTTP/MCP interfaces. Plate.hk and SeeHouse are independent."""
        return current().packs()

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_property_search(
        q: str, limit: int = 10, lang: Literal["en", "zh-Hant"] = "en"
    ) -> dict:
        """Search SeeHouse Hong Kong buildings by name, estate or address. Select a buildingId for listings. Limited ranked candidates, not a complete inventory or total. Independent provider; listing freshness is separate from API retrieval."""
        return await current().properties.search(
            PropertySearchQuery(q=q, limit=limit, lang=lang)
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_property_building(
        buildingId: str,
        lang: Literal["en", "zh-Hant"] = "en",
        quality: Literal["all", "current"] = "all",
    ) -> dict:
        """Read SeeHouse source-linked sale/rental listings for a buildingId from hk_property_search. Keep mode, HKD asking price, area in ft², freshness, matching and dedupe context. Advertisements are not verified availability, valuations or completed transactions; unit matching is not guaranteed. quality=current filters returned cards to observations within 48 hours, building-level matches and unexpired links; availability is not verified."""
        return await current().properties.building(
            PropertyListingsQuery(buildingId=buildingId, lang=lang, quality=quality)
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_property_price_history(
        buildingId: str, lang: Literal["en", "zh-Hant"] = "en"
    ) -> dict:
        """Observed SeeHouse asking-price changes for a selected building. Preserve source, sourceListingId, observedAt, old/new HKD prices and caveats. These are not Land Registry transactions or a full market history."""
        return await current().properties.history(
            PropertyBuildingQuery(buildingId=buildingId, lang=lang)
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_property_coverage() -> dict:
        """SeeHouse dated building-index and listing-coverage counts, including fresh/aging/stale and unmatched records. Distinguish indexed buildings from buildings with listings; not complete Hong Kong inventory. Metadata read only, no crawler or refresh is triggered."""
        return await current().properties.query("coverage")

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_plate_search(
        q: str,
        dataset: PlateDataset = "all",
        mode: Literal["exact", "exact_prefix", "contains"] = "exact",
        sort: Literal[
            "amount_desc", "amount_asc", "date_desc", "plate_asc"
        ] = "date_desc",
        page: int = 1,
        pageSize: int = 20,
    ) -> dict:
        """Search Plate.hk historical HK auction records. Exact match by default; contains for discovery.

        Independent provider, not government. Preserve plate spaces, two-row layout,
        dates/year ranges, disposition and original source links. Auction amounts
        are not current values, asking prices, ownership or availability. Pagination
        is live, not snapshot-pinned. pageSize 1–50, page 1–100.
        """
        return await current().plates.search(
            PlateSearchQuery(
                q=q,
                dataset=dataset,
                mode=mode,
                sort=sort,
                page=page,
                pageSize=pageSize,
            )
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_plate_comparables(q: str, page: int = 1, pageSize: int = 8) -> dict:
        """Plate.hk source-linked historical comparisons, not valuation or official classification.

        A cohort can exist without an exact sale. Preserve method, sampleSize and
        date range; null statistics mean no qualified distribution. pageSize 1–50.
        """
        return await current().plates.comparables(
            PlateComparablesQuery(
                q=q,
                page=page,
                pageSize=pageSize,
            )
        )

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_plate_datasets() -> dict:
        """Plate.hk index coverage, publication date, original-source manifests and record counts.

        Independent external pack. The all collection includes the other datasets;
        do not add its count to the component counts. Data is not relicensed as MIT.
        """
        return await current().plates.query("datasets")
