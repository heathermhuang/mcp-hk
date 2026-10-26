"""Version-pinned public racing REST/MCP interfaces."""

from typing import Annotated

from fastapi import Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import date

VERSION = r"^racing-results-v1-[a-f0-9]{64}$"


class RaceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: str | None = Field(None, pattern=VERSION)
    day: str | None = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    venue: str | None = Field(None, pattern=r"^(ST|HV)$")

    @field_validator("day")
    @classmethod
    def valid_day(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value


def register_http(app, service):
    @app.get("/api/v1/racing/status")
    async def status():
        return await service.racing.query("status")

    @app.get("/api/v1/racing/meetings")
    async def meetings(
        limit: int = Query(100, ge=1, le=100),
        after: str | None = Query(None, max_length=100),
    ):
        return {
            "data": {
                "items": await service.racing.query(
                    "meetings", limit=limit, after=after
                )
            }
        }

    @app.get("/api/v1/racing/races")
    async def races(query: Annotated[RaceQuery, Query()]):
        return await service.racing.query("races", **query.model_dump())

    @app.get("/api/v1/racing/races/{race_id}/results")
    async def results(race_id: str, version: str = Query(pattern=VERSION)):
        return await service.racing.query("results", race_id=race_id, version=version)

    @app.get("/api/v1/racing/participants/{participant_id}")
    async def profile(participant_id: str, version: str = Query(pattern=VERSION)):
        return await service.racing.query(
            "profile", participant_id=participant_id, version=version
        )

    @app.get("/api/v1/racing/exports")
    async def export(
        version: str = Query(pattern=VERSION), raceId: str = Query(max_length=200)
    ):
        packed = await service.racing.query("archive", version=version, race_id=raceId)
        return Response(
            packed,
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="racing-results.zip"',
                "Cache-Control": "private, max-age=0",
            },
        )


def register_mcp(server, current):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_racing_status() -> dict:
        """Read exact accepted racing coverage, ingestion progress and source holds. No collection on read."""
        return await current().racing.query("status")

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_racing_search(
        version: str | None = None, day: str | None = None, venue: str | None = None
    ) -> dict:
        """Read actual imported local meeting races. Pin returned version for results/profiles. Day ISO, venue ST/HV; coverage is explicit."""
        q = RaceQuery(version=version, day=day, venue=venue)
        return await current().racing.query("races", **q.model_dump())

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_racing_results(raceId: str, version: str) -> dict:
        """Read exact stored factual results and withdrawals at a returned version. Final published odds are not intraday odds history."""
        RaceQuery(version=version)
        return await current().racing.query("results", race_id=raceId, version=version)

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_racing_profile(participantId: str, version: str) -> dict:
        """Read participant identity and appearances in the selected imported meeting; not a complete historical profile."""
        RaceQuery(version=version)
        return await current().racing.query(
            "profile", participant_id=participantId, version=version
        )
