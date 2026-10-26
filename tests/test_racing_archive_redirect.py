"""Only a same-meeting archive route can resolve the evidenced 302 hold."""

import hashlib
import json
import time
from urllib.parse import urlsplit

import httpx
import pytest

from mcp_open_data_hk.curated.racing.policy import RacingRejected
from mcp_open_data_hk.curated.racing.public_results import archive_redirect
from mcp_open_data_hk.curated.racing.prototype_store import PilotCollector
from mcp_open_data_hk.racing_inspection import inspect_redirect
from mcp_open_data_hk.racing_redirect import reconcile_archive_redirect
from test_racing_inspection import model as inspection_model
from test_racing_prototype import BASE, page, store as prototype_store

model = inspection_model
store = prototype_store
RELATIVE = (
    "/en-us/local/information/archive/localresults?racedate=2026/07/15&racecourse=HV"
)


@pytest.mark.parametrize(
    "location",
    [
        "https://other.example/en-us/local/information/archive/localresults?racedate=2026/07/15&racecourse=HV",
        RELATIVE.replace("2026/07/15", "2026/07/14"),
        RELATIVE.replace("racecourse=HV", "racecourse=ST"),
        RELATIVE.replace("en-us", "zh-hk"),
        RELATIVE + "&token=secret",
        RELATIVE + "#fragment",
        RELATIVE.replace("archive", "login"),
    ],
)
def test_unrelated_redirects_fail_closed(location):
    with pytest.raises(RacingRejected):
        archive_redirect(
            "https://racing.hkjc.com" + RELATIVE.replace("/archive", ""), location
        )


def test_each_redirect_and_target_reserve_separately_and_cache_mapping(store):
    seen = []
    target = BASE.replace("/localresults", "/archive/localresults")

    def handler(request):
        seen.append(str(request.url))
        if "/archive/" not in request.url.path:
            return httpx.Response(302, content=b"moved", headers={"location": target})
        return httpx.Response(
            200,
            text=page().replace(
                "/information/localresults", "/information/archive/localresults"
            ),
            headers={"content-type": "text/html"},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        parsed, capture = PilotCollector(store).fetch(BASE, client)
        assert capture["url"] == target and parsed["race"]["number"] == 1
        again, same = PilotCollector(store).fetch(BASE, client)
        assert (
            json.loads(json.dumps(parsed)) == again
            and same == capture
            and seen == [BASE, target]
        )
    with store.connect() as db:
        rows = [
            dict(r) for r in db.execute("SELECT * FROM racing_attempts ORDER BY id")
        ]
        assert len(rows) == 2 and all(r["state"] == "success" for r in rows)
        assert (
            rows[0]["bytes"] == 5 and rows[0]["error"] == "QUALIFIED_ARCHIVE_REDIRECT"
        )
    assert json.loads(store.page(BASE)["payload"])["target"] == target


def test_target_budget_denial_retains_redirect_without_unmetered_follow(store):
    seen = []
    target = BASE.replace("/localresults", "/archive/localresults")
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                seen.append(str(r.url))
                or httpx.Response(302, content=b"moved", headers={"location": target})
            )
        )
    ) as client:
        with pytest.raises(RacingRejected, match="RUN_BUDGET"):
            PilotCollector(store, max_requests=1).fetch(BASE, client)
    assert seen == [BASE] and store.page(BASE)


def prepare_review(model, monkeypatch):
    source, old, calls = model
    previous = source.admission

    def admission(body):
        if body["action"] == "review_archive_redirect":
            calls.append(body)
            return {"reviewed": True}
        return previous(body)

    monkeypatch.setattr(source, "admission", admission)
    transport = httpx.MockTransport(
        lambda r: httpx.Response(302, content=b"moved", headers={"location": RELATIVE})
    )
    first = inspect_redirect(source, old, httpx.Client(transport=transport))
    # Replay the old deployed receipt, before routing-shape metadata existed.
    with source.connect() as db:
        db.execute(
            "UPDATE racing_redirect_inspections SET payload=json_remove(payload,'$.locationShape')"
        )
    second = inspect_redirect(
        source, old, httpx.Client(transport=transport), shape=True
    )
    assert (
        first["locationSha256"]
        == second["locationSha256"]
        == hashlib.sha256(RELATIVE.encode()).hexdigest()
    )
    with source.connect() as db:
        for day, error in [
            ("2026-07-15", "DEVELOPMENT_HTTP_302"),
            ("2026-07-12", "DEVELOPMENT_SOURCE_HELD"),
            ("2026-07-08", "DEVELOPMENT_HTTP_403"),
        ]:
            db.execute(
                "INSERT INTO racing_queue VALUES(?,?,'held',?,?)",
                (day, "HV", error, time.time()),
            )
    return source, old, calls


def test_review_preserves_original_charge_errors_and_inspections_and_only_resumes_related_queue(
    model, monkeypatch
):
    source, old, calls = prepare_review(model, monkeypatch)
    receipt = reconcile_archive_redirect(source, old)
    assert receipt["providerRequests"] == 0 and not receipt["targetResultsVerified"]
    assert receipt["relatedQueueResumed"] == receipt["globalHoldOnlyQueueResumed"] == 1
    assert reconcile_archive_redirect(source, old) == receipt
    assert sum(c["action"] == "review_archive_redirect" for c in calls) == 1
    with source.connect() as db:
        original = db.execute(
            "SELECT state,error,bytes FROM racing_attempts WHERE id=?", (old,)
        ).fetchone()
        assert tuple(original) == ("reviewed_redirect", "DEVELOPMENT_HTTP_302", 409600)
        assert (
            db.execute("SELECT count(*) FROM racing_redirect_inspections").fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "SELECT state FROM racing_queue WHERE day='2026-07-08'"
            ).fetchone()[0]
            == "held"
        )
        assert db.execute("SELECT count(*) FROM racing_accepted").fetchone()[0] == 0
    assert urlsplit(
        json.loads(
            source.page(receipt["inspections"]["location"]["sourceUrl"])["payload"]
        )["target"]
    ).path.endswith("/archive/localresults")


def test_hash_mismatch_never_resolves_local_hold(model, monkeypatch):
    source, old, calls = prepare_review(model, monkeypatch)
    with source.connect() as db:
        db.execute(
            "UPDATE racing_redirect_inspections SET payload=json_set(payload,'$.locationSha256',?)",
            ("f" * 64,),
        )
    with pytest.raises(RacingRejected, match="HASH_PROOF_REQUIRED"):
        reconcile_archive_redirect(source, old)
    assert not any(c["action"] == "review_archive_redirect" for c in calls)


def test_remote_unknown_preserves_local_hold_and_resumable_proof(model, monkeypatch):
    source, old, calls = prepare_review(model, monkeypatch)
    monkeypatch.setattr(source, "admission", lambda body: {"reviewed": False})
    with pytest.raises(RacingRejected, match="REVIEW_UNCONFIRMED"):
        reconcile_archive_redirect(source, old)
    with source.connect() as db:
        assert (
            db.execute(
                "SELECT state FROM racing_attempts WHERE id=?", (old,)
            ).fetchone()[0]
            == "held"
        )
        assert (
            db.execute(
                "SELECT count(*) FROM racing_control WHERE key LIKE 'qualified-archive-redirect:%'"
            ).fetchone()[0]
            == 0
        )


def test_archive_target_cannot_redirect_again_or_bypass_hold(store):
    target = BASE.replace("/localresults", "/archive/localresults")
    seen = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda r: (
                seen.append(str(r.url))
                or httpx.Response(302, content=b"moved", headers={"location": BASE})
            )
        )
    ) as client:
        with pytest.raises(RacingRejected, match="HTTP_302"):
            PilotCollector(store).fetch(target, client)
    assert seen == [target]
    with pytest.raises(RacingRejected, match="SOURCE_HELD"):
        store.reserve(BASE)
