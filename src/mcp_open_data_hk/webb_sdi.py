"""Public archive adapter. Reuses the already-granted Webb release, not live HKEX."""

import asyncio
import json
import os
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator
from datetime import date

from .contracts import DomainError, Envelope
from .curated.webb_sdi_source import ARCHIVE_SHA

SOURCE_URL = "https://drive.google.com/drive/folders/13mzAvvufXC3QmH8OvMVx2juUi7qdnVLL"
NOTICE = "Historical Webb Form 3A disclosures; not complete/current HKEX coverage, current holdings or executed trades. Source FLOAT/DOUBLE numeric strings preserve the dump representation, not original exact decimal input. Filing/publication dates are unknown."


class IssuerQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stockCode: str | None = Field(None, pattern=r"^[0-9]{1,5}$")
    q: str | None = Field(None, min_length=2, max_length=200)
    limit: int = Field(20, ge=1, le=100)
    cursor: str | None = Field(None, max_length=2048)
    version: str | None = Field(None, pattern=r"^webb-sdi-[A-Za-z0-9._-]{1,80}$")

    @model_validator(mode="after")
    def one(self):
        if bool(self.stockCode) == bool(self.q):
            raise ValueError("Use exact stock code or issuer-name prefix")
        return self


class DisclosureQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuerId: str = Field(pattern=r"^(?:webb:person:)?[1-9][0-9]{0,9}$")
    start: str | None = None
    end: str | None = None
    limit: int = Field(20, ge=1, le=100)
    cursor: str | None = Field(None, max_length=2048)
    version: str | None = Field(None, pattern=r"^webb-sdi-[A-Za-z0-9._-]{1,80}$")

    @model_validator(mode="after")
    def window(self):
        if bool(self.start) != bool(self.end):
            raise ValueError("Provide both event-date endpoints")
        if (
            self.start
            and not 1
            <= (date.fromisoformat(self.end) - date.fromisoformat(self.start)).days
            <= 31
        ):
            raise ValueError("Event window must be 1–31 days, end exclusive")
        return self


class WebbSdi:
    def __init__(self, companies):
        self.backend = companies

    @property
    def configured(self):
        return (
            self.backend.configured
            and os.environ.get("MCP_HK_WEBB_SDI_ENABLED") == "true"
        )

    async def query(self, operation, params=None, filing_id=None):
        if not self.configured:
            if operation == "status":
                return {
                    "source": "webb_sdi_archive",
                    "state": "not_published",
                    "version": None,
                    "coverage": None,
                    "notice": NOTICE,
                }
            raise DomainError(
                "PACK_UNAVAILABLE",
                "Historical Webb disclosure archive is not published on this gateway",
                503,
            )
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if operation not in {"status", "issuers", "disclosures", "disclosure"}:
            raise DomainError("INVALID_QUERY", "Unknown archive operation", 400)
        if operation == "disclosure":
            if not isinstance(filing_id, str) or not re.fullmatch(
                r"(?:webb:sdi:)?[1-9][0-9]{0,9}", filing_id
            ):
                raise DomainError(
                    "INVALID_ID", "Use an exact returned Webb disclosure ID", 400
                )
            path = "/v1/webb-sdi/disclosures/" + filing_id
        else:
            path = "/v1/webb-sdi/" + operation
        try:
            await asyncio.wait_for(self.backend.slots.acquire(), 0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY", "Shared query slots busy", 429, retry_after=1
            ) from exc
        try:
            payload = await asyncio.wait_for(self.backend.fetch(path, params), 12)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise DomainError("QUERY_TIMEOUT", "Archive query timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise DomainError(
                "PACK_UNAVAILABLE", "Archive backend unavailable", 503
            ) from exc
        finally:
            self.backend.slots.release()
        if operation == "status":
            if payload.get("source") != "webb_sdi_archive":
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "Archive status identity differs", 503
                )
            return payload
        if (
            payload.get("source") != "webb_sdi_archive"
            or payload.get("coverage", {}).get("archiveSha256") != ARCHIVE_SHA
            or not re.fullmatch(
                r"webb-sdi-[A-Za-z0-9._-]{1,80}", payload.get("version", "")
            )
            or (params.get("version") and params["version"] != payload["version"])
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Archive source/version identity differs", 503
            )
        data = payload.get("data")
        items = data if isinstance(data, list) else None
        if (
            operation == "disclosure"
            and not isinstance(data, dict)
            or operation != "disclosure"
            and (
                items is None
                or len(items) > params.get("limit", 20)
                or any(not isinstance(r, dict) for r in items)
            )
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Archive response shape differs", 503
            )
        result = Envelope(
            data={"items": items} if items is not None else data,
            meta={
                "apiVersion": "v1",
                "version": payload["version"],
                "view": "webb_sdi_archive",
                "snapshotIds": [payload["version"]],
                "nextCursor": payload.get("nextCursor"),
                "returnedCount": len(items) if items is not None else 1,
                "countScope": "this_page",
                "currentVerification": False,
                "coverage": payload["coverage"],
            },
            provenance=[
                {
                    "sourceId": "webb_sdi_archive",
                    "sourceUrl": SOURCE_URL,
                    "archiveSha256": ARCHIVE_SHA,
                    "licenceNoticeUrl": "/api/v1/hkex/archive/notice",
                    "attribution": "David Webb / Webb-site, original released archive",
                    "freshnessBasis": "historical_archive",
                    "currentVerification": False,
                }
            ],
            warnings=[{"code": "HISTORICAL_DISCLOSURES", "message": NOTICE}],
        ).model_dump(mode="json")
        if len(json.dumps(result, ensure_ascii=False).encode()) > 2 * 1024 * 1024:
            raise DomainError("OUTPUT_LIMIT", "Archive envelope exceeds 2 MiB", 413)
        return result
