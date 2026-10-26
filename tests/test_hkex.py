"""HKEX normalized contract/gating tests. Every notice here is synthetic."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from hkex_support import day, filing, policy, window
from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.curated.hkex.contracts import (
    Filing,
    SourceDate,
    parse_filing,
    revision_closure,
)
from mcp_open_data_hk.hkex import DisclosuresQuery, IssuerQuery, Hkex
from mcp_open_data_hk.companies import Companies


def test_lossless_typed_interests_dates_and_scoped_parties():
    doc = filing().model_dump(mode="json")
    row = parse_filing(doc, policy())
    assert row.securities[0].stock_code == "00001"
    assert row.interests[0].shares == "9007199254740993.000000000000000001"
    assert row.published_date.value is None
    assert row.event_date.value.year == 2020
    assert row.filed_date.value.year == 2026
    from mcp_open_data_hk.hkex import DetailQuery

    assert (
        DetailQuery(filingId="hkex:di:TEST_001", version="hkex-" + "a" * 32).filingId
        == "TEST_001"
    )
    assert (
        DisclosuresQuery(
            issuerId="hkex:issuer:TEST_ISSUER",
            start="2026-10-12",
            end="2026-10-19",
            basis="filed",
        ).issuerId
        == "TEST_ISSUER"
    )
    assert row.particulars[0].shares is None
    for field in (
        "email",
        "address",
        "signature",
        "rawHtml",
        "attachment",
        "sourceUrl",
    ):
        with pytest.raises(ValidationError):
            Filing.model_validate(dict(doc, **{field: "private"}))
    doc["interests"][0]["shares"] = 1.1
    with pytest.raises(ValidationError):
        Filing.model_validate(doc)
    with pytest.raises(ValidationError):
        SourceDate(value="2026-01-01")


def test_associated_security_does_not_borrow_the_listed_issuer_stock_code():
    from mcp_open_data_hk.curated.hkex.contracts import Security

    associated = Security(
        source_id="filing-scoped-associated-1",
        name="Invented associated corporation",
        share_class="Ordinary",
    )
    assert associated.stock_code is None
    primary = Security(
        source_id="source-stock-02536", stock_code="02536", name="Invented issuer"
    )
    assert primary.share_class is None and primary.name_date.value is None
    with pytest.raises(ValidationError):
        Security(source_id="invalid-code", stock_code="2536", name="Wrong precision")


@pytest.mark.parametrize("form", ["1", "2", "3A", "3B", "3C", "3D"])
def test_form_contracts_and_unknown_codes_fail_closed(form):
    row = filing(form=form)
    assert parse_filing(row.model_dump(mode="json"), policy()).form == form
    with pytest.raises(ValueError, match="UNKNOWN_CAPACITY"):
        parse_filing(row.model_dump(mode="json"), policy(codes={}))
    with pytest.raises(ValueError, match="UNQUALIFIED_FIELDS"):
        parse_filing(row.model_dump(mode="json"), policy(allowed_fields=("serial",)))


def test_revisions_missing_branch_cycle_withdrawal():
    a = filing("A", state="superseded", superseded_by="B")
    b = filing("B", state="amendment", replaces="A")
    assert revision_closure([a])["missing"] == ["B"]
    assert revision_closure([a, b])["missing"] == []
    with pytest.raises(ValueError, match="SELF_REPLACING"):
        filing("A", replaces="A")
    with pytest.raises(ValueError, match="CYCLE"):
        revision_closure(
            [
                a.model_copy(update={"replaces": "B"}),
                b.model_copy(update={"superseded_by": "A"}),
            ]
        )
    with pytest.raises(ValueError, match="CROSS_IDENTITY"):
        revision_closure([a, b.model_copy(update={"issuer_id": "OTHER"})])
    withdrawn = filing("W", state="withdrawn", withdrawn_date=day("2026-10-15"))
    assert withdrawn.state == "withdrawn" and withdrawn.interests


def test_policy_modes_hash_route_and_expiry():
    p = policy()
    p.require("collect", "rest")
    for mode in p.modes:
        modes = dict(p.modes, **{mode: "unknown"})
        with pytest.raises(ValueError, match="UNQUALIFIED"):
            policy(modes=modes).require(mode)
    with pytest.raises(ValueError, match="UNQUALIFIED"):
        policy(revoked=True).require("collect")
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError, match="UNQUALIFIED"):
        policy(
            qualified_at=now - timedelta(days=2), expires_at=now - timedelta(days=1)
        ).require()
    with pytest.raises(ValueError, match="UNQUALIFIED_ROUTE"):
        policy(routes={"detail": "https://127.0.0.1/private"})
    with pytest.raises(ValueError, match="CURSOR_EXCEEDS"):
        policy(retention_seconds=5)


def test_query_bounds_and_date_basis():
    with pytest.raises(ValidationError):
        IssuerQuery(stockCode="00001", q="foo")
    with pytest.raises(ValidationError):
        IssuerQuery(stockCode="1")
    with pytest.raises(ValueError):
        window(end="2026-12-01")
    with pytest.raises(ValidationError):
        DisclosuresQuery(
            issuerId="TEST_ISSUER", start="2026-01-01", end="2026-02-15", basis="filed"
        )


def test_public_disabled_modes_hidden_and_status_available(tmp_path, monkeypatch):
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    monkeypatch.delenv("MCP_HK_HKEX_POLICY_FILE", raising=False)
    service = Service(Store(tmp_path / "gateway.sqlite3"))
    client = TestClient(create_app(service))
    status = client.get("/api/v1/hkex/status").json()
    assert status["state"] == "source_unqualified" and status["acceptedVersion"] is None
    schema = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/hkex/status" in schema
    assert "/api/v1/hkex/issuers" not in schema
    response = client.get("/api/v1/hkex/issuers?stockCode=00001")
    assert (
        response.status_code == 503
        and response.json()["error"]["code"] == "HKEX_SOURCE_UNQUALIFIED"
    )
    assert client.get("/hkex?lang=zh-Hant").status_code == 200
    assert "權益披露" in client.get("/hkex?lang=zh-Hant").text
    assert "di.hkex.com.hk" not in client.get("/hkex").text


@pytest.mark.asyncio
async def test_no_network_when_policy_missing_or_mode_denied(monkeypatch):
    from mcp_open_data_hk.contracts import DomainError

    monkeypatch.delenv("MCP_HK_HKEX_POLICY_FILE", raising=False)
    backend = Companies()
    backend.config = ("https://example.invalid", "x" * 40)
    adapter = Hkex(backend)
    assert (await adapter.query("status"))["modes"]["rest"] == "unknown"
    with pytest.raises(DomainError, match="not qualified"):
        await adapter.query("issuers", {"stockCode": "00001"})
    adapter = Hkex(backend, policy(modes=dict(policy().modes, rest="denied")))
    assert adapter.enabled("browser") and not adapter.enabled("rest")
    with pytest.raises(DomainError):
        await adapter.query("issuers", {"stockCode": "00001"})
