"""HTTP/MCP transport adapters for the common resource service."""

from typing import Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field


class ResourceSchemaQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    parameters: dict[str, str] = Field(default_factory=dict, max_length=10)
    recordPath: str = Field(default="", max_length=300)
    sheet: str = Field(default="", max_length=100)
    layer: int | None = Field(default=None, ge=0, le=10000)
    requireFresh: bool = False

    def arguments(self):
        data = self.model_dump()
        data["record_path"] = data.pop("recordPath")
        data["require_fresh"] = data.pop("requireFresh")
        return data


class ResourceQuery(ResourceSchemaQuery):
    filters: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, max_length=10
    )
    fields: list[str] = Field(default_factory=list, max_length=100)
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)
    version: str | None = Field(default=None, max_length=64)


def register_http(app, resources):
    @app.get("/api/v1/coverage")
    def coverage():
        return resources.catalogue.coverage()

    @app.get("/api/v1/catalogue/datasets")
    def search(
        q: str = Query(default="", max_length=200),
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
        access: Literal["all", "connected", "sources"] = "all",
    ):
        """Search connected services and the reconciled native catalogue inventory, independent of the incomplete CKAN search index."""
        return resources.catalogue.search(q, limit, offset, access)

    @app.get("/api/v1/catalogue/datasets/{datasetId}")
    def dataset(datasetId: str):
        return resources.catalogue.dataset(datasetId)

    @app.get("/api/v1/catalogue/datasets/{datasetId}/resources")
    def dataset_resources(
        datasetId: str,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
        format: str | None = Query(default=None, max_length=30),
        status: str | None = Query(default=None, max_length=30),
    ):
        resources.catalogue.dataset(datasetId)
        return resources.catalogue.resources(datasetId, status, format, limit, offset)

    @app.get("/api/v1/resources")
    def directory(
        datasetId: str | None = None,
        status: str | None = None,
        format: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
    ):
        return resources.catalogue.resources(datasetId, status, format, limit, offset)

    @app.get("/api/v1/resources/{resourceId}/schema")
    async def schema(
        resourceId: str,
        recordPath: str = Query(default="", max_length=300),
        sheet: str = Query(default="", max_length=100),
        layer: int | None = Query(default=None, ge=0, le=10000),
        requireFresh: bool = False,
    ):
        return await resources.schema(
            resourceId, recordPath, sheet, layer, requireFresh
        )

    @app.post("/api/v1/resources/{resourceId}/schema")
    async def schema_post(resourceId: str, query: ResourceSchemaQuery):
        """Read-only schema inspection with source parameters, equivalent to MCP."""
        return await resources.schema(resourceId, **query.arguments())

    @app.post("/api/v1/resources/{resourceId}/query")
    async def query(resourceId: str, query: ResourceQuery):
        """Read-only scalar equality filters and field selection. Source values keep their original types."""
        return await resources.query(resourceId, **query.arguments())

    @app.get("/api/v1/resources/{resourceId}/records")
    async def records(
        resourceId: str,
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0, le=100000),
        recordPath: str = Query(default="", max_length=300),
        sheet: str = Query(default="", max_length=100),
        layer: int | None = Query(default=None, ge=0, le=10000),
        version: str | None = Query(default=None, max_length=64),
    ):
        return await resources.query(
            resourceId,
            limit=limit,
            offset=offset,
            record_path=recordPath,
            sheet=sheet,
            layer=layer,
            version=version,
        )


def register_mcp(server, current):
    annotation = {"readOnlyHint": True, "destructiveHint": False}

    @server.tool(annotations=annotation)
    def hk_catalogue_search(
        q: str = "",
        limit: int = 20,
        offset: int = 0,
        access: Literal["all", "connected", "sources"] = "all",
    ) -> dict:
        """Search connected query services (including independent Plate.hk and SeeHouse) and harvested DATA.GOV.HK/CSDI sources. Connected entries include direct HTTP/MCP actions; source entries require resource inspection. Discovery is not record validation."""
        return current().resources.catalogue.search(q, limit, offset, access)

    @server.tool(annotations=annotation)
    def hk_dataset_resources(
        datasetId: str,
        limit: int = 20,
        offset: int = 0,
        format: str | None = None,
        status: str | None = None,
    ) -> dict:
        """Connected query entries return their direct HTTP/MCP access instructions. For source datasets, list actual resource IDs, formats, language aliases, original URLs and validation status. Use format="JSON" (or another exact uppercase format) and optional status to narrow large resource lists."""
        current().resources.catalogue.dataset(datasetId)
        return current().resources.catalogue.resources(
            datasetId, status, format, limit, offset
        )

    @server.tool(annotations=annotation)
    async def hk_resource_schema(
        resourceId: str,
        recordPath: str = "",
        sheet: str = "",
        layer: int | None = None,
        requireFresh: bool = False,
        parameters: dict[str, str] | None = None,
    ) -> dict:
        """Read actual source fields and required settings. Transport feeds return required line/station, route/stop or direction parameters before querying; use their exact names. Workbooks may require sheet; ArcGIS may require layer."""
        return await current().resources.schema(
            resourceId, recordPath, sheet, layer, requireFresh, parameters
        )

    @server.tool(annotations=annotation)
    async def hk_resource_query(
        resourceId: str,
        filters: dict | None = None,
        fields: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        recordPath: str = "",
        sheet: str = "",
        layer: int | None = None,
        requireFresh: bool = False,
        version: str | None = None,
        parameters: dict[str, str] | None = None,
    ) -> dict:
        """Query actual resource records with bounded pages (1..100). For transport arrivals, provide parameters from hk_resource_schema; responses have 10/20-second caches, checked provider timestamps, and no expired fallback. requireFresh forces an arrival-source read. Preserve scheduled/predicted flags and service advisories. Pass version for later pages. PDF is unverified text. A source read does not prove all routes/operators are covered."""
        query = ResourceQuery(
            filters=filters or {},
            fields=fields or [],
            limit=limit,
            offset=offset,
            recordPath=recordPath,
            sheet=sheet,
            layer=layer,
            requireFresh=requireFresh,
            version=version,
            parameters=parameters or {},
        )
        return await current().resources.query(resourceId, **query.arguments())

    @server.tool(annotations=annotation)
    def hk_coverage() -> dict:
        """Exact inventory/queryability denominators and failure reasons. Distinguishes pending, unavailable, restricted, unsupported, stale and document extraction. Never equate discovery or service health with all government data connected."""
        return current().resources.catalogue.coverage()
