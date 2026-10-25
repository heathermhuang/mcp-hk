"""Single policy-gated HKEX adapter for REST, MCP and browser consumers."""

import asyncio
import json
import os
from pathlib import Path
from typing import Literal

import httpx
from pydantic import Field, model_validator

from .contracts import DomainError
from .curated.hkex.contracts import (
    Policy,
    ServedFiling,
    ServedIssuer,
    Strict,
    Window,
    digest,
    exact,
)
from .curated.hkex.contracts import unavailable_status

ERRORS = {
    "INVALID_QUERY": 400,
    "INVALID_ID": 400,
    "INVALID_CURSOR": 400,
    "NOT_FOUND": 404,
    "VERSION_EXPIRED": 409,
    "COVERAGE_UNAVAILABLE": 422,
    "QUERY_BUSY": 429,
    "QUERY_TIMEOUT": 504,
    "OUTPUT_LIMIT": 413,
    "HKEX_SOURCE_UNQUALIFIED": 503,
    "PACK_UNAVAILABLE": 503,
}


class IssuerQuery(Strict):
    stockCode: str | None = Field(None, pattern=r"^[0-9]{5}$")
    q: str | None = Field(None, min_length=2, max_length=200)
    limit: int = Field(20, ge=1, le=100, strict=True)
    cursor: str | None = Field(None, max_length=2048)
    version: str | None = Field(None, pattern=r"^hkex-[a-f0-9]{32}$")

    @model_validator(mode="after")
    def one_selector(self):
        if bool(self.stockCode) == bool(self.q):
            raise ValueError("Use exact stockCode or a name prefix")
        return self


class DisclosuresQuery(Strict):
    issuerId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    start: str
    end: str
    basis: Literal["filed", "published", "event"]
    channel: Literal["dion", "pre_dion"] = "dion"
    form: Literal["1", "2", "3A", "3B", "3C", "3D"] | None = None
    limit: int = Field(20, ge=1, le=100, strict=True)
    cursor: str | None = Field(None, max_length=2048)
    version: str | None = Field(None, pattern=r"^hkex-[a-f0-9]{32}$")

    @model_validator(mode="after")
    def window(self):
        Window(
            issuer_id=self.issuerId,
            start=self.start,
            end=self.end,
            basis=self.basis,
            channel=self.channel,
        )
        return self


class DetailQuery(Strict):
    filingId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    version: str = Field(pattern=r"^hkex-[a-f0-9]{32}$")


def configured_policy():
    """Operator-owned file plus separately pinned checksum; never caller input."""
    path, checksum = os.environ.get("MCP_HK_HKEX_POLICY_FILE"), os.environ.get(
        "MCP_HK_HKEX_POLICY_SHA256"
    )
    if not path or not checksum:
        return None
    try:
        policy = Policy.model_validate_json(Path(path).read_bytes())
        if digest(policy) != checksum:
            return None
        policy.require()
        return policy
    except (OSError, ValueError):
        return None


class Hkex:
    def __init__(self, companies, policy=None):
        self.backend = companies
        self.policy = policy if policy is not None else configured_policy()

    def enabled(self, mode):
        try:
            if not self.policy or not self.backend.configured:
                return False
            self.policy.require(mode, "retain", "history")
            return True
        except ValueError:
            return False

    async def query(self, operation, params=None, mode="rest"):
        if operation == "status" and (not self.policy or not self.backend.configured):
            return unavailable_status()
        if operation != "status":
            if not self.enabled(mode):
                raise DomainError(
                    "HKEX_SOURCE_UNQUALIFIED",
                    "HKEX DI access and output rights are not qualified",
                    503,
                )
            if operation == "issuers":
                query = IssuerQuery.model_validate(params)
            elif operation == "disclosures":
                query = DisclosuresQuery.model_validate(params)
            elif operation == "disclosure":
                query = DetailQuery.model_validate(params)
            else:
                raise DomainError("INVALID_QUERY", "Unknown HKEX operation", 400)
            params = query.model_dump(exclude_none=True)
        else:
            params = {}
        path = (
            "/v1/hkex/"
            + {
                "status": "status",
                "issuers": "issuers",
                "disclosures": "disclosures",
                "disclosure": (
                    "disclosures/" + exact(params["filingId"])
                    if operation == "disclosure"
                    else ""
                ),
            }[operation]
        )
        if operation == "disclosure":
            params.pop("filingId")
        # Consumer mode is fixed by trusted registration, not a public parameter.
        params["mode"] = mode
        try:
            await asyncio.wait_for(self.backend.slots.acquire(), 0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY", "Shared query concurrency reached", 429, retry_after=1
            ) from exc
        try:
            payload = await asyncio.wait_for(self._fetch(path, params), 12)
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise DomainError("QUERY_TIMEOUT", "HKEX backend timed out", 504) from exc
        except httpx.HTTPError as exc:
            raise DomainError(
                "PACK_UNAVAILABLE", "HKEX backend unavailable", 503
            ) from exc
        finally:
            self.backend.slots.release()
        if operation == "status":
            # Never forward private policy evidence, routes or request journals.
            return {
                key: payload[key]
                for key in (
                    "source",
                    "state",
                    "acceptedVersion",
                    "modes",
                    "coverage",
                    "notice",
                    "code",
                    "hold",
                )
                if key in payload
            }
        try:
            if set(payload) != {
                "source",
                "version",
                "policyHash",
                "coverage",
                "notice",
                "dictionaries",
                "data",
                "nextCursor",
            }:
                raise ValueError()
            if (
                payload["source"] != "hkex_di"
                or payload["policyHash"] != digest(self.policy)
                or (params.get("version") and params["version"] != payload["version"])
            ):
                raise ValueError()
            Window.model_validate(payload["coverage"]["window"])
            data = payload["data"]
            rows = [data] if operation == "disclosure" else data
            if not isinstance(rows, list) or len(rows) > params.get("limit", 20):
                raise ValueError()
            if operation != "issuers":
                for row in rows:
                    ServedFiling.model_validate(row)
            else:
                for row in rows:
                    ServedIssuer.model_validate(row)
            if payload.get("nextCursor") is not None and (
                not isinstance(payload["nextCursor"], str)
                or len(payload["nextCursor"]) > 2048
            ):
                raise ValueError()
            self.policy.require(mode, "retain", "history")
        except (ValueError, KeyError, TypeError) as exc:
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "HKEX backend contract changed", 503
            ) from exc
        return payload

    async def _fetch(self, path, params):
        origin, token = self.backend.config
        async with httpx.AsyncClient(
            transport=self.backend.transport,
            trust_env=False,
            follow_redirects=False,
            timeout=10,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            async with client.stream("GET", origin + path, params=params) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > 2 * 1024 * 1024:
                        raise DomainError(
                            "OUTPUT_LIMIT", "HKEX response exceeds its bound", 413
                        )
                    body.extend(chunk)
                try:
                    payload = json.loads(body)
                except (ValueError, UnicodeError) as exc:
                    raise DomainError(
                        "SOURCE_SCHEMA_CHANGED",
                        "HKEX backend returned invalid JSON",
                        503,
                    ) from exc
                if response.status_code != 200:
                    code = (
                        payload.get("detail", {}).get("code")
                        if isinstance(payload, dict)
                        else None
                    )
                    raise DomainError(
                        code if code in ERRORS else "PACK_UNAVAILABLE",
                        "HKEX request unavailable under its source contract",
                        ERRORS.get(code, 503),
                    )
                if not isinstance(payload, dict):
                    raise DomainError(
                        "SOURCE_SCHEMA_CHANGED", "HKEX response is not an object", 503
                    )
                return payload
