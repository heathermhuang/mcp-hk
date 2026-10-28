import json
import httpx
import pytest

from mcp_open_data_hk.curated.acceptance_admission import Admission
from mcp_open_data_hk.curated.company_verify import PublicVerifier


def test_public_verifier_waits_for_observed_headroom_across_instances(
    tmp_path, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr("time.time", lambda: clock[0])
    monkeypatch.setattr("time.monotonic", lambda: clock[0])
    monkeypatch.setattr(
        "time.sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    requests = []

    def serve(request):
        requests.append(clock[0])
        if len(requests) == 1:
            return httpx.Response(
                200,
                json={"ok": True},
                headers={"RateLimit-Remaining": "1", "RateLimit-Reset": "30"},
            )
        return httpx.Response(200 if clock[0] >= 130 else 429, json={"ok": True})

    for _ in range(2):
        verifier = PublicVerifier(
            tmp_path / "responses", transport=httpx.MockTransport(serve)
        )
        verifier.request("GET", "/api/v1/companies/example")
        verifier.client.close()
    assert requests == [100, 130]


def test_throttle_retains_response_and_shared_reset_without_retry(
    tmp_path, monkeypatch
):
    clock = [100.0]
    monkeypatch.setattr("time.time", lambda: clock[0])
    calls = []

    def serve(request):
        calls.append(request)
        return httpx.Response(
            429,
            json={"error": {"code": "RATE_LIMITED", "scope": "client_minute"}},
            headers={"Retry-After": "15"},
        )

    verifier = PublicVerifier(
        tmp_path / "responses", transport=httpx.MockTransport(serve)
    )
    with pytest.raises(ValueError, match="ACCEPTANCE_HTTP_429"):
        verifier.request("GET", "/api/v1/companies/example")
    assert len(calls) == 1
    assert Admission(tmp_path / "admission.json").read()["notBeforeMs"] == 115000
    failure = json.loads(
        next((tmp_path / "responses").glob("failure-*.json")).read_text()
    )
    assert failure["headers"]["retry-after"] == "15"
    assert json.loads(failure["body"])["error"]["scope"] == "client_minute"
    verifier.client.close()


def test_daily_hold_is_deferred_without_a_long_blocking_wait(tmp_path):
    admission = Admission(tmp_path / "admission.json")
    admission.observe(429, {"Retry-After": "86400"})
    with pytest.raises(ValueError, match="QUOTA_DEFERRED"):
        admission.before()
