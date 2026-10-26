"""Public published-summary adapter. Collection is confined to the host timer."""

import asyncio
import json
import os
import re
from datetime import date
from typing import Annotated

import httpx
from fastapi import Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .contracts import DomainError, Envelope
from .curated.hkex_daily.contracts import NOTICE, RECORD_ID, SOURCE, VERSION

ATTRIBUTION = "Hong Kong Exchanges and Clearing Limited (HKEX), public Disclosure of Interests daily summaries"
REUSE_NOTICE = "Source: Hong Kong Exchanges and Clearing Limited (HKEX). These records are factual observations of its public Disclosure of Interests daily summaries. Source copyright and terms remain with HKEX; this package does not assert an HKEX licence or permission grant. Source: https://di.hkex.com.hk/di/summary/NSMSumMenu.htm\nDates: summary date is the report's date, not exact filing/publication time; event dates can precede it. This is summary coverage, not full forms, executed trades or current holdings. The historical Webb archive is a separate source.\n"


class DailyQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stockCode: str | None = Field(None, pattern=r"^[0-9]{1,5}$")
    start: str | None = Field(None, max_length=10)
    end: str | None = Field(None, max_length=10)
    limit: int = Field(20, ge=1, le=100)
    cursor: str | None = Field(None, max_length=2048)
    version: str | None = Field(None, pattern="^" + VERSION + "$")

    @model_validator(mode="after")
    def window(self):
        if bool(self.start) != bool(self.end):
            raise ValueError("Provide both summary dates")
        if (
            self.start
            and not 1
            <= (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days
            <= 31
        ):
            raise ValueError("Use 1–31 summary days, end exclusive")
        return self


class DailySummaries:
    def __init__(self, companies):
        self.backend = companies

    @property
    def configured(self):
        return (
            self.backend.configured
            and os.environ.get("MCP_HK_HKEX_DAILY_ENABLED") == "true"
        )

    async def query(self, operation, params=None, record_id=None):
        if not self.configured:
            if operation == "status":
                return {
                    "source": SOURCE,
                    "state": "not_published",
                    "version": None,
                    "coverage": None,
                    "updater": None,
                    "notice": NOTICE,
                }
            raise DomainError(
                "PACK_UNAVAILABLE", "Published daily-summary feed is not enabled", 503
            )
        if operation not in {"status", "disclosures", "disclosure"}:
            raise DomainError("INVALID_QUERY", "Unknown summary operation", 400)
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if operation == "disclosure":
            if (
                not isinstance(record_id, str)
                or not re.fullmatch(RECORD_ID, record_id)
                or not re.fullmatch(VERSION, params.get("version", ""))
            ):
                raise DomainError(
                    "INVALID_ID", "Use a returned record ID and pinned version", 400
                )
        path = "/v1/hkex-daily/" + (
            "disclosures/" + record_id if operation == "disclosure" else operation
        )
        try:
            await asyncio.wait_for(self.backend.slots.acquire(), 0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY", "Shared query slots are busy", 429, retry_after=1
            ) from exc
        try:
            payload = await asyncio.wait_for(self.backend.fetch(path, params), 12)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise DomainError("QUERY_TIMEOUT", "Summary query timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise DomainError(
                "PACK_UNAVAILABLE", "Summary backend unavailable", 503
            ) from exc
        finally:
            self.backend.slots.release()
        if not isinstance(payload, dict) or payload.get("source") != SOURCE:
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Summary source identity differs", 503
            )
        if operation == "status":
            return payload
        if (
            not re.fullmatch(VERSION, payload.get("version", ""))
            or params.get("version")
            and payload["version"] != params["version"]
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Pinned summary version differs", 503
            )
        data = payload.get("data")
        if operation == "disclosure":
            if not isinstance(data, dict) or data.get("id") != record_id:
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "Summary record identity differs", 503
                )
        elif (
            not isinstance(data, list)
            or len(data) > params.get("limit", 20)
            or any(not isinstance(r, dict) or r.get("source") != SOURCE for r in data)
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Summary page shape differs", 503
            )

        def public_record(record):
            record = dict(record)
            sid = record.pop("issuer_id", "")
            if not isinstance(sid, str) or not re.fullmatch(
                r"hkex:issuer:[0-9]{1,12}", sid
            ):
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "Source search reference differs", 503
                )
            record["source_search_ref"] = sid.removeprefix("hkex:issuer:")
            record["identity_qualification"] = (
                "Raw HKEX link sid for source traceability; not verified as a permanent issuer or security identity. Stock codes are not joined to Webb identities."
            )
            return record

        data = (
            [public_record(r) for r in data]
            if isinstance(data, list)
            else public_record(data)
        )
        result = Envelope(
            data={"items": data} if isinstance(data, list) else data,
            meta={
                "apiVersion": "v1",
                "version": payload["version"],
                "view": SOURCE,
                "nextCursor": payload.get("nextCursor"),
                "returnedCount": len(data) if isinstance(data, list) else 1,
                "countScope": "this_page",
                "coverage": payload["coverage"],
                "queryCoverage": payload.get("queryCoverage"),
                "currentVerification": False,
                "dateBasis": "daily_summary_date",
            },
            provenance=[
                {
                    "sourceId": SOURCE,
                    "sourceUrl": "https://di.hkex.com.hk/di/summary/NSMSumMenu.htm",
                    "attribution": ATTRIBUTION,
                    "noticeUrl": "/api/v1/hkex/latest/notice",
                    "licenceClaimed": False,
                }
            ],
            warnings=[{"code": "DAILY_SUMMARY_SCOPE", "message": NOTICE}],
        ).model_dump(mode="json")
        if payload.get("queryCoverage", {}).get("completeRequestedReports") is False:
            result["warnings"].append(
                {
                    "code": "UNOBSERVED_REPORT_DATES",
                    "message": "Some requested calendar dates/categories have no validated report in this version; an empty result is not proof of zero filings.",
                }
            )
        if len(json.dumps(result, ensure_ascii=False).encode()) > 2 * 1024**2:
            raise DomainError("OUTPUT_LIMIT", "Summary envelope exceeds 2 MiB", 413)
        return result


def register_http(app, service):
    @app.get("/api/v1/hkex/latest/status", tags=["HKEX published daily summaries"])
    async def daily_status():
        return await service.hkex_daily.query("status")

    @app.get("/api/v1/hkex/latest/notice")
    async def daily_notice():
        return PlainTextResponse(REUSE_NOTICE)

    @app.get(
        "/api/v1/hkex/latest/disclosures",
        include_in_schema=service.hkex_daily.configured,
    )
    async def daily_disclosures(query: Annotated[DailyQuery, Query()]):
        return await service.hkex_daily.query("disclosures", query.model_dump())

    @app.get(
        "/api/v1/hkex/latest/disclosures/{record_id}",
        include_in_schema=service.hkex_daily.configured,
    )
    async def daily_detail(
        record_id: str, version: str = Query(pattern="^" + VERSION + "$")
    ):
        return await service.hkex_daily.query(
            "disclosure", {"version": version}, record_id
        )


def register_mcp(server, current):
    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_latest_status() -> dict:
        """Read current HKEX daily-summary publication date, last source check, scheduled updater and holds. This starts no collection; source summary date is not event date or exact filing time. Webb archive is separate."""
        return await current().hkex_daily.query("status")

    if not current().hkex_daily.configured:
        return

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_latest_disclosures(
        stockCode: str | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
        version: str | None = None,
    ) -> dict:
        """Read latest published HKEX daily-summary rows, optionally by stock code or summary-date interval (1–31 days, end exclusive). Defaults to seven days ending at latest observed summary. Pin version for pagination. Includes shareholder/director categories; this is summary facts, not full forms or current holdings."""
        query = DailyQuery(
            stockCode=stockCode,
            start=start,
            end=end,
            limit=limit,
            cursor=cursor,
            version=version,
        )
        return await current().hkex_daily.query("disclosures", query.model_dump())

    @server.tool(annotations={"readOnlyHint": True, "destructiveHint": False})
    async def hk_hkex_latest_disclosure(recordId: str, version: str) -> dict:
        """Read a returned HKEX daily-summary record in its pinned source version, including separate before/after long/short/lending positions, reason and price as disclosed, and source amendment remarks. Unknown dates remain unknown; full filing text is not fetched by this tool."""
        return await current().hkex_daily.query(
            "disclosure", {"version": version}, recordId
        )
