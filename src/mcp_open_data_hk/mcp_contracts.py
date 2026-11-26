"""Stable public MCP envelopes and validation errors."""

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware
from pydantic import ValidationError

from .contracts import DistrictStatistics, DomainError
from .mcp_inputs import tool_input_schema

OBJECT = {"type": "object"}
NULLABLE_STRING = {"type": ["string", "null"]}
WARNING = {
    "type": "object",
    "properties": {"code": {"type": "string"}, "message": {"type": "string"}},
}
PROVENANCE = {
    "type": "object",
    "properties": {
        "sourceUrl": {"type": "string"},
        "attribution": {"type": "string"},
        "retrievedAt": {"type": ["string", "number", "null"]},
        "observedAt": {"type": ["string", "number", "null"]},
        "lastCheckedAt": {"type": ["string", "number", "null"]},
        "lastValidatedAt": {"type": ["string", "number", "null"]},
        "freshnessBasis": {"type": "string"},
        "referencePeriod": {"type": ["string", "integer", "null"]},
        "stale": {"type": "boolean"},
    },
}


def array(items):
    return {"type": "array", "items": items}


def obj(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required)}


def envelope(data, meta=OBJECT, required=("data", "meta", "provenance")):
    return obj(
        {
            "data": data,
            "meta": meta,
            "provenance": array(PROVENANCE),
            "warnings": array(WARNING),
        },
        required,
    )


DISTRICT_STATISTICS = envelope(
    DistrictStatistics.model_json_schema() | {"additionalProperties": True}
)
# The definitions must be at the root of the advertised schema for local refs.
DISTRICT_STATISTICS["$defs"] = DISTRICT_STATISTICS["properties"]["data"].pop("$defs")

VALIDATION_GUIDANCE = {
    "hk_transport_journey": "Supply both endpoints as stop names, TD stop IDs, or complete latitude and longitude pairs.",
    "hk_transport_stop_search": "Supply a stop name, TD stop ID, or a complete latitude and longitude pair.",
}


def published_output(tool):
    schema = OUTPUT_SCHEMAS.get(tool.name)
    if tool.name == "hk_district_statistics":
        schema = DISTRICT_STATISTICS
    if schema is None:
        return tool.output_schema
    # FastMCP 2.x decodes root properties as a dataclass or Pydantic model.
    # Keep dictionary decoding for existing Python callers while JSON Schema
    # validators still enforce the same fields and required keys.
    properties = {key: value for key, value in schema.items() if key != "$defs"}
    result = {**OBJECT, "additionalProperties": True, "allOf": [properties]}
    if "$defs" in schema:
        result["$defs"] = schema["$defs"]
    return result


class PublicToolContracts(Middleware):
    async def on_list_tools(self, context, call_next):
        tools = await call_next(context)
        return [
            tool.model_copy(
                update={
                    "parameters": tool_input_schema(tool),
                    "output_schema": published_output(tool),
                }
            )
            for tool in tools
        ]

    async def on_call_tool(self, context, call_next):
        try:
            return await call_next(context)
        except ValidationError as exc:
            details = exc.errors(
                include_url=False, include_context=False, include_input=False
            )
            tool = await context.fastmcp_context.fastmcp.get_tool(context.message.name)
            fields = tool.parameters.get("properties", {})
            guidance = []
            for detail in details:
                if detail["loc"] and detail["loc"][0] in fields:
                    issue = (
                        "required"
                        if detail["type"].startswith("missing")
                        else "invalid"
                    )
                    guidance.append(f"{detail['loc'][0]}: {issue}")
            hint = VALIDATION_GUIDANCE.get(
                context.message.name, "Check the tool's input schema for valid values."
            )
            if guidance:
                hint = " ".join([", ".join(dict.fromkeys(guidance)) + ".", hint])
            raise ToolError("INVALID_QUERY: " + hint) from None
        except ToolError as exc:
            if isinstance(exc.__cause__, DomainError):
                error = exc.__cause__
                raise ToolError(f"{error.code}: {error.message}") from None
            raise


STRING = {"type": "string"}
INTEGER = {"type": "integer"}
NUMBER = {"type": "number"}
BOOLEAN = {"type": "boolean"}
NULLABLE_INTEGER = {"type": ["integer", "null"]}
NULLABLE_OBJECT = {"type": ["object", "null"]}
ROWS = array(OBJECT)
ITEMS = obj({"items": ROWS}, ("items",))
META = obj(
    {
        "requestId": STRING,
        "snapshotIds": array(STRING),
        "version": NULLABLE_STRING,
        "nextCursor": NULLABLE_STRING,
        "returnedCount": INTEGER,
        "total": NULLABLE_INTEGER,
        "truncated": {"type": ["boolean", "null"]},
    }
)
PAGE_FIELDS = {
    "items": ROWS,
    "total": INTEGER,
    "offset": INTEGER,
    "nextOffset": NULLABLE_INTEGER,
    "generation": NULLABLE_STRING,
}
ARCHIVE_STATUS = obj(
    {
        "source": STRING,
        "state": STRING,
        "version": NULLABLE_STRING,
        "acceptedVersion": NULLABLE_STRING,
        "coverage": NULLABLE_OBJECT,
        "modes": OBJECT,
        "notice": STRING,
    },
    ("source", "state"),
)
SOURCE_STATUS = obj(
    {"state": STRING, "acceptedVersion": NULLABLE_STRING, "coverage": NULLABLE_OBJECT}
)
ARRIVAL_CONTEXT = obj(
    {
        "operator": STRING,
        "arrivalState": STRING,
        "freshnessBasis": STRING,
        "sourceTimestamp": NULLABLE_STRING,
        "sourceAgeSeconds": NUMBER,
        "freshUntil": NUMBER,
        "cacheTTLSeconds": NUMBER,
        "omittedStaleRecords": INTEGER,
        "advisories": array(STRING),
    }
)
RESOURCE_COLUMNS = obj({"format": STRING, "transport": ARRIVAL_CONTEXT})
RESOURCE_SCHEMA = obj(
    {
        "resource": OBJECT,
        "dataset": OBJECT,
        "schema": RESOURCE_COLUMNS,
        "transport": ARRIVAL_CONTEXT,
        "capabilities": OBJECT,
        "selectionRequired": STRING,
        "selections": ROWS,
        "parameters": array(STRING),
        "recordCount": NULLABLE_INTEGER,
        "structuredQueryable": BOOLEAN,
        "validationFreshness": OBJECT,
        "observationFreshness": {
            "type": ["object", "null"],
            "properties": {
                "observedAt": {"type": ["string", "number", "null"]},
                "stale": BOOLEAN,
            },
        },
        "provenance": array(PROVENANCE),
        "warnings": array(WARNING),
    },
    ("resource",),
)
RESOURCE_QUERY = envelope(
    ITEMS,
    obj(
        {
            "total": INTEGER,
            "offset": INTEGER,
            "nextOffset": NULLABLE_INTEGER,
            "version": NULLABLE_STRING,
            "structuredQueryable": BOOLEAN,
        },
        ("total", "offset", "nextOffset", "version"),
    ),
)
RESOURCE_QUERY["properties"].update(
    {
        key: value
        for key, value in RESOURCE_SCHEMA["properties"].items()
        if key
        not in {
            "recordCount",
            "selectionRequired",
            "selections",
            "parameters",
            "structuredQueryable",
        }
    }
)
RESOURCE_QUERY["required"] += ["resource", "schema"]
LEGACY_SEARCH_FIELDS = {"count": INTEGER, "results": ROWS, "has_more": BOOLEAN}
CURSOR_ENVELOPE = envelope(ITEMS, META)
DETAIL_ENVELOPE = envelope(OBJECT, META)
BUS_STOP = obj(
    {"stopId": STRING, "name": OBJECT, "latitude": NUMBER, "longitude": NUMBER},
    ("stopId", "name"),
)
BUS_CANDIDATE = obj(
    {
        "route": OBJECT,
        "direction": STRING,
        "board": OBJECT,
        "alight": OBJECT,
        "arrivalStatus": STRING,
        "arrivalError": obj({"code": STRING, "message": STRING}),
        "earliestPredictedDeparture": NULLABLE_STRING,
        "arrivals": OBJECT,
    },
    ("route", "direction", "board", "alight", "arrivalStatus"),
)
PLATE_PAGE_FIELDS = {
    "items": ROWS,
    "page": INTEGER,
    "pageSize": INTEGER,
    "nextPage": NULLABLE_INTEGER,
    "paginationConsistency": STRING,
}

OUTPUT_SCHEMAS = {
    "get_category_details": obj(
        {"id": STRING, "name": STRING, "title": STRING, "package_count": INTEGER}
    ),
    "get_dataset_details": obj(
        {"id": STRING, "name": STRING, "title": STRING, "resources": ROWS}
    ),
    "get_datasets_by_format": obj(
        {"count": INTEGER, "results": ROWS}, ("count", "results")
    ),
    "search_datasets": obj(LEGACY_SEARCH_FIELDS, LEGACY_SEARCH_FIELDS),
    "search_datasets_with_facets": obj(
        {**LEGACY_SEARCH_FIELDS, "search_facets": OBJECT},
        (*LEGACY_SEARCH_FIELDS, "search_facets"),
    ),
    "hk_address_search": envelope(
        obj(
            {"items": ROWS, "selectionRequired": BOOLEAN},
            ("items", "selectionRequired"),
        ),
        META,
    ),
    "hk_address_get": DETAIL_ENVELOPE,
    "hk_catalogue_search": obj(
        {
            **PAGE_FIELDS,
            "connectedTotal": INTEGER,
            "sourceTotal": INTEGER,
            "scope": STRING,
        },
        PAGE_FIELDS,
    ),
    "hk_dataset_resources": obj(
        {**PAGE_FIELDS, "connected": OBJECT, "access": OBJECT, "scope": STRING},
        PAGE_FIELDS,
    ),
    "hk_coverage": obj(
        {
            "generation": STRING,
            "validationFreshness": OBJECT,
            "resources": OBJECT,
            "datasets": OBJECT,
            "cache": OBJECT,
            "allGovernmentDataConnected": BOOLEAN,
        },
        ("generation", "resources", "datasets"),
    ),
    "hk_resource_schema": RESOURCE_SCHEMA,
    "hk_resource_query": RESOURCE_QUERY,
    "hk_district_list": obj(
        {"items": array(obj({"id": STRING, "name": OBJECT}, ("id", "name")))},
        ("items",),
    ),
    "hk_data_packs": ITEMS,
    "hk_source_status": obj({"sources": ROWS, "ready": BOOLEAN}, ("sources", "ready")),
    "hk_restaurant_search": CURSOR_ENVELOPE,
    "hk_restaurant_get": DETAIL_ENVELOPE,
    "hk_company_search": CURSOR_ENVELOPE,
    "hk_company_get": DETAIL_ENVELOPE,
    "hk_company_name_history": CURSOR_ENVELOPE,
    "hk_company_address_history": CURSOR_ENVELOPE,
    "hk_company_officers": CURSOR_ENVELOPE,
    "hk_company_licences": CURSOR_ENVELOPE,
    "hk_company_licence_relationships": CURSOR_ENVELOPE,
    "hk_company_updates_status": envelope(
        obj({"coverage": OBJECT, "recentRuns": ROWS, "maintenance": NULLABLE_OBJECT}),
        META,
    ),
    "hk_hkex_status": ARCHIVE_STATUS,
    "hk_hkex_latest_status": ARCHIVE_STATUS,
    "hk_hkex_archive_status": ARCHIVE_STATUS,
    "hk_hkex_archive_issuers": CURSOR_ENVELOPE,
    "hk_hkex_archive_disclosures": CURSOR_ENVELOPE,
    "hk_hkex_archive_disclosure": DETAIL_ENVELOPE,
    "hk_hkex_latest_disclosures": CURSOR_ENVELOPE,
    "hk_hkex_latest_disclosure": DETAIL_ENVELOPE,
    "hk_hkex_issuers": obj(
        {
            "source": STRING,
            "version": STRING,
            "data": ROWS,
            "nextCursor": NULLABLE_STRING,
        },
        ("data", "version"),
    ),
    "hk_hkex_disclosures": obj(
        {
            "source": STRING,
            "version": STRING,
            "data": ROWS,
            "nextCursor": NULLABLE_STRING,
        },
        ("data", "version"),
    ),
    "hk_hkex_disclosure": obj(
        {
            "source": STRING,
            "version": STRING,
            "data": OBJECT,
            "nextCursor": NULLABLE_STRING,
        },
        ("data", "version"),
    ),
    "hk_plate_search": envelope(
        obj({**PLATE_PAGE_FIELDS, "total": INTEGER}, PLATE_PAGE_FIELDS), META
    ),
    "hk_plate_comparables": envelope(
        obj(
            {
                **PLATE_PAGE_FIELDS,
                "method": STRING,
                "sampleSize": INTEGER,
                "statistics": NULLABLE_OBJECT,
            },
            PLATE_PAGE_FIELDS,
        ),
        META,
    ),
    "hk_plate_datasets": envelope(
        obj({"provider": STRING, "generatedAt": STRING, "items": ROWS}, ("items",)),
        META,
    ),
    "hk_property_search": envelope(
        obj({"candidates": ROWS, "releaseScope": NULLABLE_OBJECT}, ("candidates",)),
        META,
    ),
    "hk_property_building": envelope(obj({"id": STRING, "listings": ROWS}), META),
    "hk_property_price_history": envelope(
        obj({"buildingId": STRING, "events": ROWS, "eventCount": INTEGER}), META
    ),
    "hk_property_coverage": envelope(
        obj({"officialIndex": NULLABLE_OBJECT, "productionCoverage": NULLABLE_OBJECT}),
        META,
    ),
    "hk_racing_status": envelope(SOURCE_STATUS, META),
    "hk_racing_search": CURSOR_ENVELOPE,
    "hk_racing_results": DETAIL_ENVELOPE,
    "hk_racing_profile": DETAIL_ENVELOPE,
    "hk_racing_profile_observation": envelope(OBJECT, META, ("data", "meta")),
    "hk_racing_profile_history": envelope(ITEMS, META, ("data", "meta")),
    "hk_sfc_status": envelope(SOURCE_STATUS, META),
    "hk_sfc_verify": DETAIL_ENVELOPE,
    "hk_sfc_history": envelope(ROWS, META),
    "hk_sfc_export": obj(
        {
            "version": STRING,
            "bytes": INTEGER,
            "sha256": STRING,
            "url": STRING,
            "scope": STRING,
        },
        ("version", "bytes", "sha256", "url"),
    ),
    "hk_transport_stop_search": envelope(
        obj(
            {
                "items": array(BUS_STOP),
                "totalMatched": INTEGER,
                "selectionRequired": BOOLEAN,
            },
            ("items", "totalMatched", "selectionRequired"),
        ),
        META,
    ),
    "hk_transport_stop_routes": envelope(
        obj({"stop": BUS_STOP, "items": ROWS}, ("stop", "items")), META
    ),
    "hk_transport_journey": envelope(
        obj(
            {
                "items": array(BUS_CANDIDATE),
                "originCandidates": array(BUS_STOP),
                "destinationCandidates": array(BUS_STOP),
                "coverage": OBJECT,
                "departureComparison": OBJECT,
            },
            ("items", "originCandidates", "destinationCandidates", "coverage"),
        ),
        META,
    ),
}
