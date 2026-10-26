"""Bounded shared HTTP/MCP adapter for the original Enigma archive backend."""

import asyncio
import json
import os
import re
from datetime import datetime, timezone
import uuid
from urllib.parse import urlsplit

import httpx

from .contracts import DomainError, Envelope

SOURCE_URL = "https://drive.google.com/drive/folders/13mzAvvufXC3QmH8OvMVx2juUi7qdnVLL"
ARCHIVE_SHA = "9c2c42ae5e762d34b60954f43b37199b92b546033e229a292ed08b76323f6de2"
MAX_BYTES = 2 * 1024 * 1024
ERRORS = {
    "SFC_INVALID_CE": 400,
    "SFC_MODE_UNQUALIFIED": 503,
    "SFC_POLICY_UNQUALIFIED": 503,
    "SFC_POLICY_CHANGED": 503,
    "SFC_VERSION_UNAVAILABLE": 503,
    "SFC_SCHEMA_CHANGED": 503,
    "SFC_POINTER_UNQUALIFIED": 503,
    "INVALID_QUERY": 400,
    "INVALID_LIMIT": 400,
    "INVALID_ID": 400,
    "INVALID_CURSOR": 400,
    "NOT_FOUND": 404,
    "VERSION_EXPIRED": 409,
    "AS_OF_UNSUPPORTED": 422,
    "QUERY_BUSY": 429,
    "QUERY_TIMEOUT": 504,
    "OUTPUT_LIMIT": 413,
    "PACK_UNAVAILABLE": 503,
    "UNSAFE_READER": 503,
}


def settings():
    origin = os.environ.get("MCP_HK_CURATED_ORIGIN", "").rstrip("/")
    token = os.environ.get("MCP_HK_CURATED_TOKEN", "")
    try:
        url = urlsplit(origin)
        local = (
            os.environ.get("MCP_HK_CURATED_ALLOW_LOCAL") == "true"
            and url.scheme == "http"
            and url.hostname in {"localhost", "127.0.0.1", "::1", "backend"}
        )
        secure = url.scheme == "https" and url.hostname and url.port in {None, 443}
        if (
            not (local or secure)
            or url.username
            or url.password
            or url.path
            or url.query
            or url.fragment
            or len(token) < 32
        ):
            return None
    except ValueError:
        return None
    return origin, token


class Companies:
    def __init__(self, transport=None):
        self.config = settings()
        self.transport = transport
        self.slots = asyncio.Semaphore(4)

    @property
    def configured(self):
        return self.config is not None

    async def query(self, operation, params=None, entity_id=None, family=None):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        if params.get("view") == "latest_observed":
            return await self.official_query(operation, params, entity_id, family)
        if (
            params.pop("requireFresh", False)
            or params.pop("view", "archive") != "archive"
        ):
            raise DomainError(
                "ARCHIVE_NOT_CURRENT",
                "This pack contains historical source observations only",
                422,
            )
        if not self.config:
            raise DomainError(
                "PACK_UNAVAILABLE", "The archival company backend is not configured"
            )
        if entity_id is not None and (
            type(entity_id) is not int or not 0 < entity_id < 2**63
        ):
            raise DomainError("INVALID_ID", "Use a positive Webb source entity ID", 400)
        if operation == "search":
            path = "/v1/companies"
            if "q" in params:
                params["name"] = params.pop("q")
        elif operation == "get":
            path = f"/v1/entities/{entity_id}"
        elif operation == "related" and family in {
            "names",
            "officers",
            "licences",
            "licence_relationships",
        }:
            path = f"/v1/entities/{entity_id}/{family}"
        else:
            raise DomainError("INVALID_QUERY", "Unsupported archival operation", 400)
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY",
                "Company query concurrency limit reached",
                429,
                retry_after=1,
            ) from exc
        try:
            payload = await asyncio.wait_for(self.fetch(path, params), timeout=12)
            if params.get("groupBy") and (
                not isinstance(payload, dict)
                or payload.get("groupBy") != params["groupBy"]
            ):
                raise DomainError(
                    "CAPABILITY_UNAVAILABLE",
                    "Grouped company search has not been adopted by the backend",
                    503,
                )
        except (asyncio.TimeoutError, httpx.TimeoutException) as exc:
            raise DomainError(
                "QUERY_TIMEOUT", "Archival query exceeded its time bound", 504
            ) from exc
        except httpx.HTTPError as exc:
            raise DomainError(
                "PACK_UNAVAILABLE", "Archival backend is unavailable"
            ) from exc
        finally:
            self.slots.release()
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("version"), str)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", payload["version"])
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Archival response identity is invalid"
            )
        source = payload.get("provenance")
        data = payload.get("data")
        cursor = payload.get("nextCursor")
        if (
            not isinstance(source, dict)
            or source.get("archiveSha256") != ARCHIVE_SHA
            or source.get("view") != "archive"
            or not isinstance(data, (dict, list))
            or (
                isinstance(data, list)
                and (len(data) > 100 or any(not isinstance(row, dict) for row in data))
            )
            or (
                cursor is not None
                and (not isinstance(cursor, str) or len(cursor) > 2048)
            )
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED",
                "Archival response violates its bounded source contract",
            )
        if (
            (operation == "get" and not isinstance(data, dict))
            or (operation != "get" and not isinstance(data, list))
            or (params.get("version") and payload["version"] != params["version"])
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED",
                "Archival response does not match the requested view or version",
            )
        if operation == "get" and (
            type(data.get("entity_id")) is not int
            or data["entity_id"] != entity_id
            or data.get("kind") not in {"organisation", "person"}
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Archival record identity is invalid"
            )
        if operation == "get" and data.get("kind") != "organisation":
            raise DomainError(
                "NOT_FOUND", "This archive ID is not an organisation", 404
            )
        warnings = [
            {
                "code": "ARCHIVAL_DATA",
                "message": "Original Enigma archive observations; not current government verification",
                "affectedSourceId": "enigma",
            }
        ]
        temporal = source.get("temporalQualification") or {}
        if not isinstance(temporal, dict) or not isinstance(
            temporal.get("officer_appointments", {}), dict
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Archival temporal qualification is invalid"
            )
        conflicts = temporal.get("officer_appointments", {}).get("reversed_bounds", 0)
        if type(conflicts) is not int or conflicts < 0:
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Archival temporal qualification is invalid"
            )
        if conflicts:
            warnings.append(
                {
                    "code": "SOURCE_INTERVAL_CONFLICTS",
                    "message": "Conflicting source officer dates are preserved; exact as-of reconstruction is unsupported",
                    "affectedSourceId": "enigma",
                    "sourceRowCount": conflicts,
                }
            )
        result = Envelope(
            data={"items": data} if isinstance(data, list) else data,
            meta={
                "requestId": uuid.uuid4().hex,
                "apiVersion": "v1",
                "snapshotIds": [payload["version"]],
                "version": payload["version"],
                "view": "archive",
                "asOfSupported": False,
                "nextCursor": cursor,
                "truncated": bool(cursor),
                "returnedCount": len(data) if isinstance(data, list) else 1,
                "countScope": "this_page",
                **({"groupBy": payload["groupBy"]} if payload.get("groupBy") else {}),
            },
            provenance=[
                dict(
                    source,
                    sourceId="enigma",
                    licenceNoticeUrl="/api/v1/companies/notice",
                    sourceUrl=SOURCE_URL,
                    attribution="David Webb / Webb-site, original Enigma release",
                    retrievedAt=datetime.now(timezone.utc).isoformat(),
                    freshnessBasis="fixed_archive",
                    currentVerification=False,
                )
            ],
            warnings=warnings,
        ).model_dump(mode="json")
        if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_BYTES:
            raise DomainError(
                "OUTPUT_LIMIT", "Archival envelope exceeded its byte bound", 413
            )
        return result

    async def official_query(self, operation, params, entity_id=None, family=None):
        from .curated.official import LIMITATIONS

        params = dict(params)
        params.pop("view", None)
        if params.pop("requireFresh", False):
            raise DomainError(
                "ARCHIVE_NOT_CURRENT",
                "Official observations have source dates and subset coverage; freshness cannot be guaranteed",
                422,
            )
        if not self.config:
            raise DomainError("PACK_UNAVAILABLE", "Company backend is not configured")
        if operation == "search":
            path = "/v1/official/companies"
            if "q" in params:
                params["name"] = params.pop("q")
        elif (
            operation == "get"
            and isinstance(entity_id, str)
            and re.fullmatch(r"cr:(?:local|foreign|mlr):[A-Za-z0-9]{1,20}", entity_id)
        ):
            path = "/v1/official/entities/" + entity_id
        elif (
            operation == "related"
            and family == "addresses"
            and isinstance(entity_id, str)
            and re.fullmatch(r"cr:(?:local|foreign):[A-Za-z0-9]{1,20}", entity_id)
        ):
            path = "/v1/official/entities/" + entity_id + "/addresses"
        elif operation == "status":
            path = "/v1/official/status"
        else:
            raise DomainError(
                "INVALID_QUERY",
                "Use an official source identity for observed detail; archival histories remain separate",
                400,
            )
        try:
            await asyncio.wait_for(self.slots.acquire(), timeout=0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY", "Company query concurrency limit reached", 429
            ) from exc
        try:
            payload = await asyncio.wait_for(self.fetch(path, params), timeout=12)
            if params.get("groupBy") and (
                not isinstance(payload, dict)
                or payload.get("groupBy") != params["groupBy"]
            ):
                raise DomainError(
                    "CAPABILITY_UNAVAILABLE",
                    "Grouped company search has not been adopted by the backend",
                    503,
                )
        except (httpx.HTTPError, asyncio.TimeoutError) as exc:
            raise DomainError(
                "PACK_UNAVAILABLE", "Official observations are unavailable"
            ) from exc
        finally:
            self.slots.release()
        source, data, version = (
            payload.get("provenance"),
            payload.get("data"),
            payload.get("version"),
        )
        if (
            not isinstance(source, dict)
            or source.get("view") != "latest_observed"
            or not isinstance(version, str)
            or not re.fullmatch(r"official-[a-f0-9]{32}", version)
            or not isinstance(data, (dict, list))
            or isinstance(data, list)
            and (len(data) > 100 or any(not isinstance(r, dict) for r in data))
            or params.get("version")
            and version != params["version"]
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED",
                "Official response violates its bounded version contract",
            )
        if operation == "get" and (
            not isinstance(data, dict) or data.get("entity_id") != entity_id
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED", "Official record identity differs"
            )
        return Envelope(
            data={"items": data} if isinstance(data, list) else data,
            meta={
                "version": version,
                "view": "latest_observed",
                "snapshotIds": [version],
                "nextCursor": payload.get("nextCursor"),
                "returnedCount": len(data) if isinstance(data, list) else 1,
                "countScope": "this_page",
                **({"groupBy": payload["groupBy"]} if payload.get("groupBy") else {}),
                "currentVerification": False,
            },
            provenance=[source],
            warnings=[
                {
                    "code": "OFFICIAL_OBSERVED_SUBSET",
                    "message": message,
                    "affectedSourceId": "companies_registry",
                }
                for message in LIMITATIONS
            ],
        ).model_dump(mode="json")

    async def fetch(self, path, params):
        origin, token = self.config
        async with httpx.AsyncClient(
            transport=self.transport,
            timeout=httpx.Timeout(10, connect=5),
            trust_env=False,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + token},
        ) as client:
            async with client.stream("GET", origin + path, params=params) as response:
                content = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(content) + len(chunk) > MAX_BYTES:
                        raise DomainError(
                            "OUTPUT_LIMIT",
                            "Archival response exceeded its byte bound",
                            413,
                        )
                    content.extend(chunk)
                try:
                    payload = json.loads(content)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise DomainError(
                        "SOURCE_SCHEMA_CHANGED",
                        "Archival backend returned invalid JSON",
                    ) from exc
                if response.status_code != 200:
                    detail = (
                        payload.get("detail", {}) if isinstance(payload, dict) else {}
                    )
                    code = detail.get("code") if isinstance(detail, dict) else None
                    if code not in ERRORS:
                        raise DomainError(
                            "PACK_UNAVAILABLE",
                            "Archival backend could not complete this request",
                        )
                    raise DomainError(
                        code,
                        {
                            "AS_OF_UNSUPPORTED": "Exact as-of reconstruction is unsupported",
                            "VERSION_EXPIRED": "Restart the query; its version or cursor expired",
                            "NOT_FOUND": "No matching organisation in the selected archive version",
                        }.get(
                            code,
                            "Archival query could not complete under its documented contract",
                        ),
                        ERRORS[code],
                        retry_after=1 if code == "QUERY_BUSY" else None,
                    )
                return payload
