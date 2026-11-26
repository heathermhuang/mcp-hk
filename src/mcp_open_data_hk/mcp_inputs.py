"""Agent-facing descriptions and constraints for the existing flat tool arguments."""

from functools import lru_cache

from .contracts import LEGACY_CATALOGUE_PAGE_LIMIT


PARAMETER_HELP = {
    "access": "Search connected services, source datasets, or both.",
    "all_fields": "Return category objects instead of category name strings.",
    "asOf": "ISO date for archive queries that support a dated cutoff.",
    "basis": "Which published date defines the filing window.",
    "buildingId": "Exact building ID returned by hk_property_search.",
    "capability": "Filter datasets by qualified record access or required selection.",
    "category_id": "Category ID or name returned by list_categories.",
    "ce": "Exact corporate central entity number for the qualified SFC cohort.",
    "channel": "Source filing channel for the selected window.",
    "contains": "Map source field names to literal case-insensitive substring filters.",
    "cursor": "Opaque cursor from the previous page. Reuse the query and version.",
    "dataset": "Plate.hk auction series. The all series includes the individual series.",
    "datasetId": "Exact dataset ID from hk_catalogue_search.",
    "dataset_id": "Exact DATA.GOV.HK dataset ID or name.",
    "day": "Local meeting date in YYYY-MM-DD.",
    "destination": "Destination stop name or TD stop ID. Coordinates may be used instead.",
    "destinationLat": "WGS84 destination latitude. Supply destinationLon with it.",
    "destinationLon": "WGS84 destination longitude. Supply destinationLat with it.",
    "district": "Administrative district ID from hk_district_list.",
    "districtId": "Administrative district ID from hk_district_list.",
    "end": "Exclusive ISO end date. Supply the start date when used.",
    "entityId": "Exact returned ID for the selected company view. Preserve string IDs.",
    "entityKind": "Filter by a reviewed entity kind for the source dataset.",
    "fields": "Exact source field names to include in each record.",
    "file_format": "DATA.GOV.HK format name, for example CSV or JSON.",
    "filingId": "Exact filing ID from the corresponding disclosures search.",
    "filters": "Map exact source field names to typed scalar equality values.",
    "format": "Resource file format, such as JSON or CSV.",
    "form": "Published HKEX disclosure form code.",
    "geoAddress": "Exact 19-character GeoAddress returned by the address lookup service.",
    "groupBy": "Group matching company name facts by organisation.",
    "includeArrivals": "Check qualified live operator arrivals when true.",
    "includeSummary": "Include counts for the complete filtered licence snapshot.",
    "include_dataset_count": "Include the publisher's total dataset count.",
    "include_datasets": "Include the category's bounded dataset sample.",
    "include_extras": "Include the category's extra source fields.",
    "include_followers": "Include the category's follower count.",
    "include_groups": "Include child groups.",
    "include_tags": "Include category tags.",
    "include_tracking": "Include source tracking metadata where available.",
    "include_users": "Include the publisher's public category users.",
    "issuerId": "Exact ID from the corresponding issuer search.",
    "kind": "Participant identity kind used by the racing profile source.",
    "lang": "Response or query language where supported.",
    "language": "DATA.GOV.HK catalogue language: en, tc, or sc.",
    "lat": "WGS84 latitude. Supply lon with it.",
    "layer": "ArcGIS layer number returned by hk_resource_schema.",
    "licenceId": "Exact licence ID returned by hk_restaurant_search.",
    "licenceType": "Exact FEHD licence type.",
    "limit": "Maximum number of results on this page.",
    "lon": "WGS84 longitude. Supply lat with it.",
    "mode": "Choose the match mode for the plate query.",
    "namespace": "Exact identifier namespace. Supply its value together.",
    "nearby": "WGS84 point and radius for a qualified spatial resource.",
    "offset": "Zero-based record offset. Use nextOffset from the preceding page.",
    "operator": "Restrict to one Transport Department operator code.",
    "order": "Order datasets by relevance or title.",
    "orderBy": "Ordered typed sort fields for a bounded resource result window.",
    "order_by": "Legacy category ordering selector. Prefer sort.",
    "origin": "Origin stop name or TD stop ID. Coordinates may be used instead.",
    "originLat": "WGS84 origin latitude. Supply originLon with it.",
    "originLon": "WGS84 origin longitude. Supply originLat with it.",
    "page": "One-based page number.",
    "pageSize": "Maximum number of rows per page.",
    "parameters": "Source argument names and values from hk_resource_schema.",
    "participantId": "Exact participant ID returned by the racing results.",
    "predicates": "Typed numeric, date or datetime comparisons on resource fields.",
    "presentation": "Include available source presentation metadata.",
    "provider": "Filter datasets by provider type.",
    "q": "Search text or identifier as documented for this tool.",
    "quality": "Use current to filter to recent, building-matched listing observations.",
    "query": "DATA.GOV.HK Solr query. Use *:* to match all datasets.",
    "raceId": "Exact race ID returned by hk_racing_search.",
    "radiusM": "Straight-line search radius in metres.",
    "recordId": "Exact ID returned by hk_hkex_latest_disclosures.",
    "recordPath": "Exact record or file selection returned by hk_resource_schema.",
    "requireFresh": "Require a current validation for the selected source or snapshot.",
    "resourceId": "Exact resource ID returned by hk_dataset_resources.",
    "sheet": "Exact worksheet from hk_resource_schema for the selected workbook.",
    "sort": "Sort order for the returned results.",
    "sourceId": "Exact published participant ID in the selected identity namespace.",
    "start": "Inclusive ISO start date. Supply the end date when used.",
    "status": "Resource validation status filter.",
    "stockCode": "Stock code as text. Preserve leading zeroes.",
    "stopId": "Exact TD stop ID returned by hk_transport_stop_search.",
    "typedFilters": "Exact equality filters with explicit scalar types and source fields.",
    "value": "Identifier text in the selected namespace. Preserve leading zeroes.",
    "venue": "Racing venue code, ST or HV.",
    "version": "Exact snapshot version from the preceding response.",
    "view": "Select archival or latest observed company records.",
    "year": "Published reference year. Omit for the latest accepted year.",
}

# Conventions specific to a single operation take precedence over shared names.
TOOL_HELP = {
    "hk_catalogue_search": {
        "q": "Dataset words, title, identifier, or a supported bilingual task phrase.",
    },
    "hk_resource_query": {
        "requireFresh": "Force a source read for arrival feeds and reject stale observations where checked.",
    },
    "hk_racing_profile_history": {"language": "Racing source language: en or zhHant."},
    "hk_company_officers": {
        "asOf": "Exact as-of reconstruction is unsupported for archive appointments."
    },
}

CONSTRAINT_KEYS = {
    "minimum",
    "maximum",
    "pattern",
    "maxLength",
    "minLength",
    "maxItems",
}
LEGACY_LIMIT = {"minimum": 0, "maximum": LEGACY_CATALOGUE_PAGE_LIMIT}
LEGACY_OFFSET = {"minimum": 0}
DIRECT_CONSTRAINTS = {
    "list_datasets": {"limit": LEGACY_LIMIT, "offset": LEGACY_OFFSET},
    "list_categories": {"limit": LEGACY_LIMIT, "offset": LEGACY_OFFSET},
    "search_datasets": {"limit": LEGACY_LIMIT, "offset": LEGACY_OFFSET},
    "get_datasets_by_format": {"limit": LEGACY_LIMIT},
    "hk_address_search": {
        "q": {"minLength": 1, "maxLength": 200},
        "limit": {"minimum": 1, "maximum": 10},
    },
    "hk_address_get": {"geoAddress": {"minLength": 19, "maxLength": 19}},
    "hk_catalogue_search": {
        "q": {"maxLength": 200},
        "limit": {"minimum": 1, "maximum": 100},
        "offset": {"minimum": 0, "maximum": 100000},
    },
    "hk_dataset_resources": {
        "limit": {"minimum": 1, "maximum": 100},
        "offset": {"minimum": 0, "maximum": 100000},
    },
    "hk_sfc_history": {"limit": {"minimum": 1, "maximum": 100}},
}


@lru_cache(maxsize=1)
def model_properties():
    from .contracts import (
        CompanyHistoryQuery,
        CompanyReadQuery,
        CompanySearchQuery,
        PlateComparablesQuery,
        PlateSearchQuery,
        PropertyBuildingQuery,
        PropertyListingsQuery,
        PropertySearchQuery,
        RestaurantQuery,
    )
    from .hkex import DetailQuery, DisclosuresQuery, IssuerQuery
    from .hkex_daily import DailyQuery
    from .racing_api import ProfileQuery, RaceQuery
    from .resource_api import ResourceQuery, ResourceSchemaQuery
    from .transport_api import JourneyQuery, StopQuery
    from .webb_sdi import DisclosureQuery, IssuerQuery as WebbIssuerQuery

    sources = {
        "hk_resource_schema": ResourceSchemaQuery,
        "hk_resource_query": ResourceQuery,
        "hk_transport_stop_search": StopQuery,
        "hk_transport_journey": JourneyQuery,
        "hk_restaurant_search": RestaurantQuery,
        "hk_property_search": PropertySearchQuery,
        "hk_property_building": PropertyListingsQuery,
        "hk_property_price_history": PropertyBuildingQuery,
        "hk_plate_search": PlateSearchQuery,
        "hk_plate_comparables": PlateComparablesQuery,
        "hk_company_search": CompanySearchQuery,
        "hk_company_get": CompanyReadQuery,
        "hk_company_address_history": CompanyHistoryQuery,
        "hk_company_name_history": CompanyHistoryQuery,
        "hk_company_officers": CompanyHistoryQuery,
        "hk_company_licences": CompanyHistoryQuery,
        "hk_company_licence_relationships": CompanyHistoryQuery,
        "hk_hkex_issuers": IssuerQuery,
        "hk_hkex_disclosures": DisclosuresQuery,
        "hk_hkex_disclosure": DetailQuery,
        "hk_hkex_archive_issuers": WebbIssuerQuery,
        "hk_hkex_archive_disclosures": DisclosureQuery,
        "hk_hkex_latest_disclosures": DailyQuery,
        "hk_racing_search": RaceQuery,
        "hk_racing_results": RaceQuery,
        "hk_racing_profile": RaceQuery,
        "hk_racing_profile_observation": ProfileQuery,
        "hk_racing_profile_history": ProfileQuery,
    }
    return {
        name: model.model_json_schema()["properties"] for name, model in sources.items()
    }


def tool_input_schema(tool):
    schema = tool.parameters
    properties = schema.get("properties", {})
    if not properties:
        return {**schema, "additionalProperties": False}
    fields = model_properties().get(tool.name, {})
    descriptions = TOOL_HELP.get(tool.name, {})
    direct = DIRECT_CONSTRAINTS.get(tool.name, {})
    result = {}
    for name, original in properties.items():
        field = fields.get(name, {})
        variants = field.get("anyOf", [field])
        constraints = {
            key: value
            for variant in variants
            for key, value in variant.items()
            if key in CONSTRAINT_KEYS
        }
        description = (
            original.get("description")
            or descriptions.get(name)
            or PARAMETER_HELP.get(name)
        )
        result[name] = {
            **original,
            **constraints,
            **direct.get(name, {}),
        }
        if description:
            result[name]["description"] = description
    return {**schema, "properties": result}
