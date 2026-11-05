"""Identical validated bus discovery contracts for HTTP and MCP."""

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StopQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    q: str = Field(default="", max_length=200)
    lat: float | None = Field(default=None, ge=22, le=23)
    lon: float | None = Field(default=None, ge=113, le=115)
    radiusM: int = Field(default=500, ge=1, le=2000)
    operator: str = Field(default="", pattern=r"^[A-Za-z]{0,20}$")
    limit: int = Field(default=20, ge=1, le=50)

    @model_validator(mode="after")
    def selection(self):
        if (self.lat is None) != (self.lon is None):
            raise ValueError("Provide both latitude and longitude")
        if not self.q.strip() and self.lat is None:
            raise ValueError("Provide a stop name, TD stopId, or coordinates")
        return self


class JourneyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    origin: str = Field(default="", max_length=200)
    destination: str = Field(default="", max_length=200)
    originLat: float | None = Field(default=None, ge=22, le=23)
    originLon: float | None = Field(default=None, ge=113, le=115)
    destinationLat: float | None = Field(default=None, ge=22, le=23)
    destinationLon: float | None = Field(default=None, ge=113, le=115)
    radiusM: int = Field(default=500, ge=1, le=2000)
    operator: str = Field(default="", pattern=r"^[A-Za-z]{0,20}$")
    includeArrivals: bool = True
    limit: int = Field(default=3, ge=1, le=5)

    @model_validator(mode="after")
    def endpoints(self):
        StopQuery(q=self.origin, lat=self.originLat, lon=self.originLon)
        StopQuery(q=self.destination, lat=self.destinationLat, lon=self.destinationLon)
        return self


def register_http(app, transport):
    @app.get("/api/v1/transport/stops")
    async def stops(query: Annotated[StopQuery, Query()]):
        """Search bus stops by bilingual partial name, TD stopId or WGS84 radius."""
        return await transport.stops(query)

    @app.get("/api/v1/transport/stops/{stopId}/routes")
    async def routes(
        stopId: str, operator: str = Query(default="", pattern=r"^[A-Za-z]{0,20}$")
    ):
        """Read directional route memberships. Stop IDs use the TD namespace."""
        return await transport.routes(stopId, operator)

    @app.post("/api/v1/transport/journeys")
    async def journeys(query: JourneyQuery):
        """Find direct bus routes and attach independently verified Citybus live arrivals."""
        return await transport.journey(query)


def register_mcp(server, current):
    annotation = {"readOnlyHint": True, "destructiveHint": False}

    @server.tool(annotations=annotation)
    async def hk_transport_stop_search(
        q: str = "",
        lat: float | None = None,
        lon: float | None = None,
        radiusM: int = 500,
        operator: str = "",
        limit: int = 20,
    ) -> dict:
        """Search bilingual bus stop names or nearby WGS84 locations. Returns TD stop IDs, not operator ETA IDs. Select a stop, then read routes or find a direct journey. Use hk_address_search first for an arbitrary landmark; distances are straight-line."""
        return await current().transport.stops(
            StopQuery(
                q=q, lat=lat, lon=lon, radiusM=radiusM, operator=operator, limit=limit
            )
        )

    @server.tool(annotations=annotation)
    async def hk_transport_stop_routes(stopId: str, operator: str = "") -> dict:
        """Read directional bus route memberships for a TD stopId from stop search. Preserve regular/special service flags. This does not establish current operation."""
        query = StopQuery(q=stopId, operator=operator)
        return await current().transport.routes(query.q, query.operator)

    @server.tool(annotations=annotation)
    async def hk_transport_journey(
        origin: str = "",
        destination: str = "",
        operator: str = "",
        originLat: float | None = None,
        originLon: float | None = None,
        destinationLat: float | None = None,
        destinationLon: float | None = None,
        radiusM: int = 500,
        includeArrivals: bool = True,
        limit: int = 3,
    ) -> dict:
        """Find direct bus routes between partial bilingual stop names, TD stop IDs or WGS84 locations. Citybus arrivals verify current operator stop identities and route order, then read live ETA with a maximum 20-second cache. Other operators return dated route references; use their generic resource arrival tools. Check each arrivalStatus/error, source dates and service flags. No transfer, walking-time, fastest-route or current-service guarantee."""
        return await current().transport.journey(
            JourneyQuery(
                origin=origin,
                destination=destination,
                operator=operator,
                originLat=originLat,
                originLon=originLon,
                destinationLat=destinationLat,
                destinationLon=destinationLon,
                radiusM=radiusM,
                includeArrivals=includeArrivals,
                limit=limit,
            )
        )
