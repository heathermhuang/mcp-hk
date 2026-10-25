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


@pytest.mark.asyncio
async def test_official_view_keeps_source_identity_and_version_separate(monkeypatch):
    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://archive.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "x" * 32)
    version = "official-" + "a" * 32
    paths = []

    def upstream(request):
        paths.append(request.url.path)
        data = {"entity_id": "cr:local:00001234", "observations": []}
        return httpx.Response(
            200,
            json={
                "version": version,
                "provenance": {"view": "latest_observed"},
                "data": data if "entities" in request.url.path else [data],
                "nextCursor": None,
            },
        )

    client = Companies(transport=httpx.MockTransport(upstream))
    found = await client.query("search", {"q": "香港", "view": "latest_observed"})
    assert found["meta"]["view"] == "latest_observed"
    assert found["data"]["items"][0]["entity_id"] == "cr:local:00001234"
    detail = await client.query(
        "get",
        {"view": "latest_observed", "version": version},
        entity_id="cr:local:00001234",
    )
    assert detail["meta"]["version"] == version
    assert paths == [
        "/v1/official/companies",
        "/v1/official/entities/cr:local:00001234",
    ]
    with pytest.raises(DomainError):
        await client.query("get", {"view": "latest_observed"}, entity_id=1234)
    with pytest.raises(DomainError):
        await client.query(
            "search", {"view": "latest_observed", "q": "香港", "requireFresh": True}
        )
    assert len(paths) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("view", ["archive", "latest_observed"])
async def test_grouped_search_requires_adopted_backend_capability(monkeypatch, view):
    from mcp_open_data_hk.companies import ARCHIVE_SHA

    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://archive.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "x" * 32)

    def upstream(request):
        assert request.url.params["groupBy"] == "organisation"
        return httpx.Response(
            200,
            json={
                "version": "v1",
                "data": [],
                "provenance": {"view": view, "archiveSha256": ARCHIVE_SHA},
            },
        )

    adapter = Companies(httpx.MockTransport(upstream))
    with pytest.raises(DomainError) as error:
        await adapter.query(
            "search", {"q": "HSBC", "view": view, "groupBy": "organisation"}
        )
    assert error.value.code == "CAPABILITY_UNAVAILABLE"
