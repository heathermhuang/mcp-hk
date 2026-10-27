"""Existing accepted racing data is enriched only through its single bounded queue."""

from test_racing_public import service as base_service, pilot as base_pilot, accept

service = base_service
pilot = base_pilot


def test_recapture_queues_once_without_reads_budget_or_pointer_change(
    service, pilot, tmp_path
):
    accepted, _ = accept(service, pilot, tmp_path)
    store = service.racing.store
    store.enqueue([{"date": "2026-10-21", "venue": "HV"}])
    with store.connect() as db:
        before = [tuple(r) for r in db.execute("SELECT * FROM racing_attempts")]
    result = store.queue_dividend_recapture()
    assert result["state"] == "queued" and result["providerRequests"] == 0
    assert result["baseVersion"] == accepted["version"]
    assert store.read()["version"] == accepted["version"]
    assert (
        store.queue_dividend_recapture()["state"] == "deferred_existing_owner_or_hold"
    )
    with store.connect() as db:
        assert [tuple(r) for r in db.execute("SELECT * FROM racing_attempts")] == before
        db.execute("UPDATE racing_queue SET state='accepted'")
        db.execute("DELETE FROM racing_control WHERE key LIKE 'refresh:%'")
    assert store.queue_dividend_recapture()["state"] == "unchanged"


def test_existing_explicit_refresh_is_preserved_without_duplicate_or_parser_marker(
    service, pilot, tmp_path
):
    accept(service, pilot, tmp_path)
    store = service.racing.store
    store.enqueue([{"date": "2026-10-21", "venue": "HV"}], refresh=True)
    with store.connect() as db:
        original = [tuple(r) for r in db.execute("SELECT * FROM racing_queue")]
        markers = [tuple(r) for r in db.execute("SELECT * FROM racing_control")]
    assert (
        store.queue_dividend_recapture()["state"] == "deferred_existing_owner_or_hold"
    )
    with store.connect() as db:
        assert [tuple(r) for r in db.execute("SELECT * FROM racing_queue")] == original
        assert [tuple(r) for r in db.execute("SELECT * FROM racing_control")] == markers


def test_new_staged_candidate_defers_enrichment_until_its_existing_recovery(
    service, pilot
):
    service.racing.store.import_bundle(pilot)
    assert (
        service.racing.store.queue_dividend_recapture()["state"]
        == "deferred_existing_owner_or_hold"
    )


def test_completed_explicit_refresh_counts_as_this_parser_and_is_not_requeued(
    service, pilot, tmp_path
):
    from test_racing_prototype import client
    from mcp_open_data_hk.racing_store import dividend_parser_hash

    accept(service, pilot, tmp_path)
    store = service.racing.store
    store.enqueue([{"date": "2026-10-21", "venue": "HV"}], refresh=True)
    result = store.advance(max_requests=40, client=client())
    assert result["state"] == "staged"
    with store.connect() as db:
        assert (
            db.execute(
                "SELECT value FROM racing_control WHERE key='dividend-recapture:hkjc:meeting:v1:2026-10-21:HV'"
            ).fetchone()[0]
            == dividend_parser_hash()
        )
        db.execute("UPDATE racing_publications SET state='accepted'")
        db.execute("UPDATE racing_queue SET state='accepted'")
    assert store.queue_dividend_recapture()["state"] == "unchanged"
