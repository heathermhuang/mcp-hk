"""Bounded source reads. No redirects or user-supplied destinations."""

import json
from urllib.parse import urlsplit

import httpx

from .contracts import DomainError

HOSTS = {"data.gov.hk", "www.als.gov.hk", "portal.csdi.gov.hk"}


async def request_json(url: str, params: dict | None = None):
    if urlsplit(url).scheme != "https" or urlsplit(url).hostname not in HOSTS:
        raise DomainError("INVALID_SOURCE", "Source is not allowed", 400)
    try:
        async with httpx.AsyncClient(
            timeout=5,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "Accept-Language": "en,zh-Hant",
                "User-Agent": "mcp.hk/0.1 (+https://mcp.hk)",
            },
        ) as client:
            async with client.stream("GET", url, params=params) as response:
                response.raise_for_status()
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 8_000_000:
                        raise DomainError(
                            "SOURCE_TOO_LARGE", "Source response exceeds the size limit"
                        )
        return json.loads(body)
    except httpx.TimeoutException:
        raise DomainError(
            "UPSTREAM_TIMEOUT", "Government source timed out", 504
        ) from None
    except (httpx.HTTPError, ValueError):
        raise DomainError(
            "UPSTREAM_UNAVAILABLE",
            "Government source is unavailable or returned invalid JSON",
        ) from None
