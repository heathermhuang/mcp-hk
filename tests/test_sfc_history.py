"""Gateway contract and closed defaults; no SFC network traffic."""

from datetime import datetime, timezone, timedelta

import httpx
import pytest

from test_sfc import fake_policy
from mcp_open_data_hk.companies import Companies
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.sfc import Sfc


@pytest.mark.asyncio
async def test_history_rest_mcp_parity_and_mode_gate_before_backend_dispatch():
    calls = []
    base = fake_policy()
    policy = fake_policy(modes={**base.modes, "history": "allowed"})
    version = "sfc-" + "a" * 32
    now = datetime.now(timezone.utc)
    item = {
        "ce": "ZZZ001",
        "version": version,
        "observedAt": now.isoformat(),
        "publishedAt": now.isoformat(),
        "expiresAt": (now + timedelta(hours=1)).isoformat(),
    }

    def backend(request):
        calls.append(request)
        assert request.url.path == "/v1/sfc/corporations/ZZZ001/history"
        assert request.url.params["limit"] == "1"
        return httpx.Response(
            200,
            json={
                "version": version,
                "data": [item],
                "nextCursor": None,
                "provenance": {
                    "sourceId": "sfc_register",
                    "policySha256": policy.sha256,
                    "captureFormat": "sfc-public-register-v1",
                },
            },
        )

    companies = Companies(transport=httpx.MockTransport(backend))
    companies.config = ("https://curated.example", "test-credential-never-a-real-token")
    adapter = Sfc(companies, policy)
    rest = await adapter.query("history", ce="zzz001", version=version, limit=1)
    mcp = await adapter.query(
        "history", ce="ZZZ001", version=version, limit=1, mode="mcp"
    )
    assert rest == mcp and rest["meta"]["completeRegulatoryHistory"] is False
    assert [r.url.params["mode"] for r in calls] == ["rest", "mcp"]
    adapter.policy = base
    with pytest.raises(DomainError):
        await adapter.query("history", ce="ZZZ001")
    assert len(calls) == 2
    adapter.policy = policy
    item["ce"] = "ZZZ002"
    with pytest.raises(DomainError, match="identity"):
        await adapter.query("history", ce="ZZZ001", limit=1)
