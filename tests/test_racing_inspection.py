"""Diagnostic admission does not clear controls, follow routes or publish facts."""

import hashlib
import json
import time
import io
import tarfile

import httpx
import pytest

from test_racing_public import service as base_service
from mcp_open_data_hk.api import create_app

from mcp_open_data_hk.racing_store import RacingStore
from mcp_open_data_hk.racing_inspection import inspect_redirect, location_metadata
from mcp_open_data_hk.curated.racing.policy import RacingRejected

URL = "https://racing.hkjc.com/en-us/local/information/localresults?racedate=2026/07/15&Racecourse=HV"
REFERENCE = "a" * 32
service = base_service


@pytest.fixture
def model(tmp_path, monkeypatch):
    store = RacingStore(tmp_path / "racing.sqlite3")
    monkeypatch.setenv("MCP_HK_EDGE_MODE", "true")
    with store.connect() as db:
        old = db.execute(
            "INSERT INTO racing_attempts(at,url,state,error) VALUES(?,?,'held','DEVELOPMENT_HTTP_302')",
            (time.time(), URL),
        ).lastrowid
        db.execute("INSERT INTO racing_remote_requests VALUES(?,?)", (old, REFERENCE))
    calls = []

    def admission(body):
        calls.append(body)
        return (
            {"allowed": True}
            if body["action"] == "inspect_redirect"
            else {"settled": True}
        )

    monkeypatch.setattr(store, "admission", admission)
    return store, old, calls


def test_inspects_only_exact_recorded_url_once_without_follow_or_hold_change(model):
    store, old, calls = model
    requests = []
    target = "/racing/information/English/Racing/LocalResults.aspx?RaceDate=2026/07/15&Racecourse=HV"

    def handler(request):
        requests.append(str(request.url))
        assert "authorization" not in request.headers
        return httpx.Response(302, content=b"moved", headers={"location": target})

    result = inspect_redirect(
        store,
        old,
        httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )
    assert (
        requests == [URL]
        and result["providerRequests"] == 1
        and result["originalHoldRetained"]
    )
    assert (
        result["responseStatus"] == 302
        and result["state"] == "received"
        and result["settlementConfirmed"]
    )
    assert result["bodySha256"] == hashlib.sha256(b"moved").hexdigest()
    assert "LocalResults.aspx" in result["location"]
    assert calls[0]["referenceId"] == REFERENCE and calls[1]["action"] == "settle"
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT state,error FROM racing_attempts WHERE id=?", (old,)
            ).fetchone()["state"]
            == "held"
        )
        assert (
            json.loads(
                db.execute(
                    "SELECT payload FROM racing_redirect_inspections"
                ).fetchone()[0]
            )
            == result
        )
        assert db.execute("SELECT count(*) FROM racing_accepted").fetchone()[0] == 0
    with pytest.raises(RacingRejected, match="ALREADY_RECORDED"):
        inspect_redirect(store, old)
    assert len(requests) == 1


def test_denial_or_unknown_is_not_locally_eligible(model):
    store, old, calls = model
    for code in (
        "DEVELOPMENT_HTTP_403",
        "SOURCE_HTTP_429",
        "DEVELOPMENT_REQUEST_UNCERTAIN",
    ):
        with store.connect() as db:
            db.execute("UPDATE racing_attempts SET error=? WHERE id=?", (code, old))
        with pytest.raises(RacingRejected, match="NOT_ELIGIBLE"):
            inspect_redirect(store, old)
    assert calls == []


def test_no_durable_admission_means_zero_provider_dispatch(model, monkeypatch):
    store, old, calls = model
    monkeypatch.setattr(
        store,
        "admission",
        lambda body: {"allowed": False, "code": "RACING_DAILY_BUDGET"},
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda _: pytest.fail("No source dispatch allowed")
        )
    )
    result = inspect_redirect(store, old, client)
    assert result["providerRequests"] == 0 and result["state"] == "admission_denied"
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT state FROM racing_attempts WHERE id=?", (old,)
            ).fetchone()[0]
            == "held"
        )


def test_response_timeout_is_preserved_unknown_without_second_source_request(model):
    store, old, calls = model
    requests = []

    def handler(request):
        requests.append(str(request.url))
        raise httpx.ReadTimeout("fixture")

    result = inspect_redirect(
        store, old, httpx.Client(transport=httpx.MockTransport(handler))
    )
    assert (
        result["state"] == "unknown"
        and not result["settlementConfirmed"]
        and len(requests) == 1
    )
    with pytest.raises(RacingRejected, match="ALREADY_RECORDED"):
        inspect_redirect(store, old)
    assert len(calls) == 1


def test_new_denial_is_an_additional_hold_not_a_successful_inspection(model):
    store, old, calls = model
    result = inspect_redirect(
        store,
        old,
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(403, content=b"blocked")
            )
        ),
    )
    assert (
        result["responseStatus"] == 403
        and result["accountingState"] == "held"
        and not result["settlementConfirmed"]
    )
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT count(*) FROM racing_attempts WHERE state='held'"
            ).fetchone()[0]
            == 2
        )


@pytest.mark.asyncio
async def test_operator_returns_real_checkpoint_with_separate_inspection_metadata(
    service, monkeypatch
):
    token = "inspection-test-only-credential-at-least-32-bytes"
    monkeypatch.setenv("MCP_HK_OPS_TOKEN", token)
    metadata = {
        "state": "received",
        "originalAttempt": 298,
        "originalHoldRetained": True,
        "providerRequests": 1,
    }
    monkeypatch.setattr(
        "mcp_open_data_hk.racing_inspection.inspect_redirect", lambda *_: metadata
    )
    app = create_app(service)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://localhost"
    ) as c:
        assert (
            await c.post(
                "/__ops/racing", json={"action": "inspect_redirect", "attempt": 298}
            )
        ).status_code == 404
        response = await c.post(
            "/__ops/racing",
            headers={"Authorization": "Bearer " + token},
            json={"action": "inspect_redirect", "attempt": 298},
        )
    assert (
        response.status_code == 200
        and json.loads(response.headers["x-racing-inspection"]) == metadata
    )
    assert (
        hashlib.sha256(response.content).hexdigest()
        == response.headers["x-snapshot-sha256"]
    )
    with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
        assert "database.sqlite3" in archive.getnames()


@pytest.mark.parametrize(
    "location",
    [
        "https://example.invalid/private?token=secret",
        "https://racing.hkjc.com/login?token=secret",
        "https://racing.hkjc.com/session/secret",
        "https://user:secret@racing.hkjc.com/x",
        "https://racing.hkjc.com/x?RaceDate=2026/07/15&racedate=2026/07/16",
    ],
)
def test_location_does_not_leak_credentials_or_unknown_query_values(location):
    metadata = location_metadata(URL, location)
    assert metadata["location"] is None and "secret" not in json.dumps(metadata)
