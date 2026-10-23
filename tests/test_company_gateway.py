"""Gateway failure boundaries without an optional database/driver."""

import httpx
import pytest

from mcp_open_data_hk.companies import Companies, settings
from mcp_open_data_hk.contracts import DomainError


@pytest.mark.parametrize(
    "origin",
    [
        "http://public.example",
        "https://user:password@example.com",
        "https://archive.example/path",
        "https://archive.example?url=other",
        "https://archive.example:1234",
    ],
)
def test_configuration_cannot_change_request_origin_boundaries(monkeypatch, origin):
    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", origin)
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "x" * 32)
    assert settings() is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,code",
    [
        ("offline", "PACK_UNAVAILABLE"),
        ("redirect", "PACK_UNAVAILABLE"),
        ("secret_error", "PACK_UNAVAILABLE"),
        ("oversized", "OUTPUT_LIMIT"),
        ("invalid_json", "SOURCE_SCHEMA_CHANGED"),
        ("bad_record", "SOURCE_SCHEMA_CHANGED"),
        ("bad_temporal", "SOURCE_SCHEMA_CHANGED"),
    ],
)
async def test_failed_backend_never_becomes_empty_data_or_leaks_credentials(
    monkeypatch, kind, code
):
    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://archive.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "never-leak-this-secret-credential-32")
    calls = []

    def upstream(request):
        calls.append(request)
        if kind == "offline":
            raise httpx.ConnectError("private connection details", request=request)
        if kind == "oversized":
            return httpx.Response(200, content=b"x" * (2 * 1024 * 1024 + 1))
        if kind == "invalid_json":
            return httpx.Response(200, content=b"invalid")
        if kind in {"bad_record", "bad_temporal"}:
            from mcp_open_data_hk.companies import ARCHIVE_SHA

            return httpx.Response(
                200,
                json={
                    "version": "v1",
                    "provenance": {
                        "archiveSha256": ARCHIVE_SHA,
                        "view": "archive",
                        "temporalQualification": (
                            "invalid" if kind == "bad_temporal" else None
                        ),
                    },
                    "data": {} if kind == "bad_record" else [],
                    "nextCursor": None,
                },
            )
        if kind == "redirect":
            return httpx.Response(
                307,
                headers={"Location": "https://untrusted.example"},
                json={"detail": {"code": "REDIRECT"}},
            )
        return httpx.Response(
            401, json={"detail": "never-leak-this-secret-credential-32"}
        )

    client = Companies(transport=httpx.MockTransport(upstream))
    with pytest.raises(DomainError) as error:
        await client.query(
            "get" if kind == "bad_record" else "search",
            {"q": "香港"},
            entity_id=1 if kind == "bad_record" else None,
        )
    assert error.value.code == code
    assert "secret" not in str(error.value) and "private connection" not in str(
        error.value
    )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unconfigured_backend_is_optional_and_unavailable(monkeypatch):
    monkeypatch.delenv("MCP_HK_CURATED_ORIGIN", raising=False)
    monkeypatch.delenv("MCP_HK_CURATED_TOKEN", raising=False)
    client = Companies()
    assert not client.configured
    with pytest.raises(DomainError) as error:
        await client.query("search", {"q": "香港"})
    assert error.value.code == "PACK_UNAVAILABLE"
