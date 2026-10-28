"""Fabricated SFC contracts only: never source facts or permission evidence."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.curated.sfc.contracts import (
    MODES,
    CORPORATE_FIELDS,
    Rejected,
    SourceDate,
    ce_reference,
    parse_normalized,
)
from mcp_open_data_hk.curated.sfc.policy import POLICY, Policy
from mcp_open_data_hk.sfc import status


def fake_fact(ce="ZZZ001"):
    return {
        "ce": ce,
        "entityType": "corporation",
        "regime": "SFO",
        "licenceType": "licensed_corporation",
        "nameEn": "Fabricated fixture corporation",
        "nameZhHant": "虛構測試法團",
        "statusCode": "SOURCE_ACTIVE",
        "statusLabel": "Fixture active",
        "observedAt": datetime.now(timezone.utc).isoformat(),
        "activities": [
            {
                "code": "1",
                "label": "Fixture dealing",
                "statusCode": "SOURCE_ACTIVE",
                "statusLabel": "Fixture active",
                "start": {"raw": "2020-01", "value": "2020-01", "precision": "month"},
            }
        ],
    }


def fake_policy(**updates):
    now = datetime.now(timezone.utc)
    fields = dict(
        purpose="intended_dealing_corporate_verification",
        route="https://apps.sfc.hk/publicregWeb/synthetic-contract-only",
        evidenceRef="SYNTHETIC TEST POLICY — NOT SOURCE PERMISSION",
        evidenceSha256="a" * 64,
        qualifiedAt=now - timedelta(days=1),
        recheckAt=now + timedelta(days=1),
        modes={
            mode: (
                "allowed"
                if mode
                in {"automation", "retention", "backup", "rest", "mcp", "browser"}
                else "denied"
            )
            for mode in MODES
        },
        allowedFields=CORPORATE_FIELDS,
        trackedCorporateReferences=("ZZZ001", "ZZZ002", "ZZZ003"),
        retentionSeconds=86400,
        backupSeconds=86400,
    )
    fields.update(updates)
    return Policy(**fields)


@pytest.mark.parametrize(
    "value",
    [
        "ＡＢＣ123",
        "ABC１２３",
        "ABС123",
        " ABC123",
        "ABC123 ",
        "ABC12",
        "123ABC",
        "ABC123'",
        "abc123\n",
        None,
        123456,
    ],
)
def test_identity_rejects_lookalikes_and_injection(value):
    with pytest.raises(Rejected, match="INVALID_CE"):
        ce_reference(value)


def test_exact_identity_and_unknown_intervals_never_infer_status():
    record = parse_normalized(json.dumps(fake_fact("zzz001")).encode(), "ZZZ001")
    assert record.subject_id == "sfc:ce:ZZZ001"
    assert record.activities[0].end.value is None
    assert record.activities[0].end.precision == "unknown"
    assert record.sourceCutoff.value is None
    assert record.observedAt.tzinfo is not None
    for code in ("SOURCE_SUSPENDED", "SOURCE_CEASED", "SOURCE_REVOKED", "unknown"):
        raw = fake_fact()
        raw["statusCode"] = code
        assert parse_normalized(json.dumps(raw).encode(), "ZZZ001").statusCode == code


@pytest.mark.parametrize(
    "change",
    [
        {"entityType": "individual"},
        {"regime": "AMLO"},
        {"licenceType": "registered_institution"},
        {"ce": "ZZZ002"},
        {"email": "private@example.com"},
        {"brn": "12345678"},
        {"representatives": []},
        {"observedAt": "2026-10-25T01:00:00"},
        {
            "activities": [
                {
                    "code": "1",
                    "label": "x",
                    "statusCode": "x",
                    "statusLabel": "x",
                    "phone": "123",
                }
            ]
        },
    ],
)
def test_parser_rejects_scope_drift_and_excluded_fields(change):
    raw = fake_fact()
    raw.update(change)
    with pytest.raises(Rejected, match="SCHEMA_CHANGED"):
        parse_normalized(json.dumps(raw).encode(), "ZZZ001")


@pytest.mark.parametrize(
    "raw",
    [
        b"<html>Login</html>",
        b"{}",
        b'{"ce":"ZZZ001","ce":"ZZZ002"}',
        b"null",
        b"x" * 262145,
    ],
)
def test_bad_response_cannot_become_empty_or_revoked(raw):
    with pytest.raises(Rejected):
        parse_normalized(raw, "ZZZ001")


@pytest.mark.parametrize(
    "value",
    [
        dict(raw=None, value="2020-01-01", precision="unknown"),
        dict(raw="2020", value="2020-01-01", precision="day"),
        dict(raw="2020-13", value="2020-13", precision="month"),
    ],
)
def test_source_dates_do_not_manufacture_precision(value):
    with pytest.raises(ValueError):
        SourceDate(**value)


def test_multiple_intervals_and_future_effective_dates_are_source_claims():
    raw = fake_fact()
    raw["activities"].append(
        {
            **raw["activities"][0],
            "start": {"raw": "2099-01-01", "value": "2099-01-01", "precision": "day"},
        }
    )
    record = parse_normalized(json.dumps(raw).encode(), "ZZZ001")
    assert (
        len(record.activities) == 2 and record.activities[1].start.value == "2099-01-01"
    )
    raw["activities"].append(raw["activities"][0])
    with pytest.raises(Rejected):
        parse_normalized(json.dumps(raw).encode(), "ZZZ001")


def test_policy_independent_modes_expiry_and_no_public_override():
    for mode in MODES:
        with pytest.raises(Rejected):
            POLICY.require(mode)
    p = fake_policy()
    p.require("automation", "rest")
    with pytest.raises(Rejected):
        p.require("search")
    with pytest.raises(Rejected):
        p.require("rest", now=p.recheckAt)
    with pytest.raises(ValueError):
        fake_policy(route="https://evil.example/publicregWeb/")
    with pytest.raises(ValueError):
        fake_policy(cacheSeconds=10)
    with pytest.raises(ValueError):
        fake_policy(retentionSeconds=0)
    with pytest.raises(ValueError):
        fake_policy(modes={"rest": "allowed"})
    with pytest.raises(ValueError):
        fake_policy(purpose="marketing")


def test_http_denied_modes_and_public_schema(tmp_path):
    client = TestClient(create_app(Service(Store(str(tmp_path / "sfc.sqlite3")))))
    response = client.get("/api/v1/sfc/status")
    assert response.json() == status()
    assert response.json()["data"]["acceptedVersion"] is None
    assert response.headers["cache-control"] == "no-store"
    for path in (
        "/api/v1/sfc/corporations",
        "/api/v1/sfc/corporations/ZZZ001",
        "/api/v1/sfc/corporations/ZZZ001/history",
    ):
        r = client.get(
            path,
            params={
                "purpose": "intended_dealing_corporate_verification",
                "enabled": "true",
            },
        )
        assert (
            r.status_code == 503
            and r.json()["error"]["code"] == "SFC_SOURCE_UNQUALIFIED"
        )
    assert client.get("/api/v1/sfc/corporations/ＡＢＣ123").status_code == 400
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/sfc/status" in paths
    assert not any(p.startswith("/api/v1/sfc/corporations") for p in paths)
    for lang, title in (
        ("en", "SFC licence archive"),
        ("zh-Hant", "證監會牌照歷史檔案"),
    ):
        r = client.get("/sfc", params={"lang": lang})
        assert title in r.text and 'id="sfc-ce"' in r.text and " disabled" in r.text
        from mcp_open_data_hk.discovery import Document

        assert not any("download" in n.attrs for n in Document(r.text).elements())
        assert "noindex" in r.text


@pytest.mark.asyncio
async def test_mcp_advertises_only_status_and_matches_http(tmp_path):
    app = create_app(Service(Store(str(tmp_path / "sfc.sqlite3"))))
    async with Client(app.state.mcp) as client:
        tools = await client.list_tools()
        assert {t.name for t in tools if t.name.startswith("hk_sfc_")} == {
            "hk_sfc_status"
        }
        result = await client.call_tool("hk_sfc_status", {})
        assert result.data == status()


def test_private_backend_authentication_and_gate_without_database():
    from mcp_open_data_hk.curated.backend import create_app as backend
    from mcp_open_data_hk.curated.read import Reader

    client = TestClient(
        backend(Reader("not-a-dsn", b"x" * 32), "test-sfc-backend-token-32-characters")
    )
    auth = {"Authorization": "Bearer test-sfc-backend-token-32-characters"}
    assert client.get("/v1/sfc/status").status_code == 401
    assert client.get("/v1/sfc/status", headers=auth).status_code == 503
    assert client.get("/v1/sfc/corporations/ZZZ001", headers=auth).status_code == 503
    assert client.get("/v1/sfc/corporations/ＡＢＣ123", headers=auth).status_code == 400


@pytest.mark.asyncio
async def test_public_sfc_reads_use_private_reader_and_pin_identity(tmp_path):
    import httpx
    from mcp_open_data_hk.companies import Companies
    from mcp_open_data_hk.sfc import Sfc

    policy = fake_policy()
    version = "sfc-" + "a" * 32
    fact = fake_fact()
    calls = []

    def backend(request):
        calls.append(request)
        if request.url.path == "/v1/sfc/status":
            return httpx.Response(
                200,
                json={
                    "sourceId": "sfc_register",
                    "state": "available",
                    "acceptedVersion": version,
                    "enabledModes": ["rest", "mcp"],
                    "freshnessBasis": "dated_observation_not_realtime",
                },
            )
        return httpx.Response(
            200,
            json={
                "version": version,
                "data": fact,
                "provenance": {
                    "sourceId": "sfc_register",
                    "policySha256": policy.sha256,
                    "view": "sfc_observation",
                    "captureFormat": "sfc-public-register-v1",
                },
            },
        )

    companies = Companies(transport=httpx.MockTransport(backend))
    companies.config = ("https://curated.example", "test-credential-never-a-real-token")
    adapter = Sfc(companies, policy)
    result = await adapter.query("status")
    assert result["meta"]["version"] == version
    rest = await adapter.query("verify", ce="zzz001", version=version)
    mcp = await adapter.query("verify", ce="ZZZ001", version=version, mode="mcp")
    assert rest == mcp
    assert rest["data"]["activities"][0]["end"]["value"] is None
    assert rest["meta"]["currentVerification"] is False
    assert [r.url.params.get("mode") for r in calls[1:]] == ["rest", "mcp"]
    from mcp_open_data_hk.contracts import DomainError

    with pytest.raises(DomainError, match="identity"):
        await adapter.query("verify", ce="ZZZ002", version=version)
    with pytest.raises(DomainError):
        await adapter.query("verify", ce="ZZZ001", version="sfc-" + "b" * 32)


def test_policy_binds_fields_and_exact_tracked_cohort():
    with pytest.raises(ValueError, match="every contract field"):
        fake_policy(allowedFields=("ce",))
    with pytest.raises(ValueError, match="Unsupported"):
        fake_policy(allowedFields=CORPORATE_FIELDS + ("email",))
    with pytest.raises(ValueError, match="exact qualified tracked cohort"):
        fake_policy(trackedCorporateReferences=())
    with pytest.raises(ValueError, match="canonical"):
        fake_policy(trackedCorporateReferences=("zzz001",))
    with pytest.raises(ValueError):
        fake_policy(trackedCorporateReferences=("ZZZ001",) * 2)


def test_private_development_is_not_blocked_by_a_feed_licence_or_public_grant():
    base = fake_policy()
    modes = {**base.modes, "rest": "denied", "mcp": "denied", "browser": "denied"}
    private = fake_policy(purpose="connector_development", modes=modes)
    private.require("automation", "retention", "backup")
    for mode in ("rest", "mcp", "browser", "search", "history", "export"):
        with pytest.raises(Rejected):
            private.require(mode)
        with pytest.raises(ValueError):
            fake_policy(
                purpose="connector_development", modes={**modes, mode: "allowed"}
            )


def test_runtime_policy_requires_matching_checksum_not_an_enable_flag(monkeypatch):
    from mcp_open_data_hk.curated.sfc.policy import configured_policy

    monkeypatch.setenv("MCP_HK_SFC_ENABLED", "true")
    for name in [
        "MCP_HK_SFC_POLICY_FILE",
        "MCP_HK_SFC_POLICY_JSON",
        "MCP_HK_SFC_POLICY_SHA256",
    ]:
        monkeypatch.delenv(name, raising=False)
    assert configured_policy() == POLICY
    policy = fake_policy()
    monkeypatch.setenv("MCP_HK_SFC_POLICY_JSON", policy.model_dump_json())
    monkeypatch.setenv("MCP_HK_SFC_POLICY_SHA256", "0" * 64)
    assert configured_policy() == POLICY
    monkeypatch.setenv("MCP_HK_SFC_POLICY_SHA256", policy.sha256)
    assert configured_policy() == policy
