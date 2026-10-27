import pytest

from mcp_open_data_hk.curated.racing.families import (
    declarations,
    sectionals,
    career,
    trial,
    rankings,
    jackpot,
    prospective,
)
from mcp_open_data_hk.curated.racing.policy import RacingRejected


def test_independent_declarations_preserve_withdrawal_reserve_and_unreported():
    declared = [
        {"participantId": "a", "state": "declared"},
        {"participantId": "b", "state": "withdrawn"},
        {"participantId": "c", "state": "reserve"},
    ]
    args = dict(
        expected=["a", "b", "c"],
        declared=declared,
        results=[{"participantId": "a", "status": "finished"}],
        declaration_capture="one",
        result_capture="two",
    )
    result = declarations(**args)
    assert (
        result["complete"]
        and result["withdrawnOrScratchedIds"] == ["b"]
        and result["reserveIds"] == ["c"]
    )
    with pytest.raises(RacingRejected, match="INDEPENDENT"):
        declarations(**dict(args, result_capture="one"))
    assert not declarations(**dict(args, results=[]))["complete"]
    with pytest.raises(RacingRejected, match="CONFLICT"):
        declarations(
            **dict(args, results=[{"participantId": "b", "status": "finished"}])
        )


def test_sectionals_reconcile_distance_order_and_source_precision_without_fabricating_total():
    rows = [
        {"segment": 1, "endDistanceM": 400, "unit": "seconds", "seconds": "23.41"},
        {"segment": 2, "endDistanceM": 800, "unit": "seconds", "seconds": "22.59"},
    ]
    assert sectionals(rows, distance_m=800, total_seconds="46.00")["totalReconciled"]
    assert not sectionals(rows, distance_m=800)["totalReconciled"]
    for changed in [rows[::-1], rows[:1]]:
        with pytest.raises(RacingRejected):
            sectionals(changed, distance_m=800)
    with pytest.raises(RacingRejected, match="TOTAL_MISMATCH"):
        sectionals(rows, distance_m=800, total_seconds="47.00")


def test_career_requires_exact_source_inventory_and_never_claims_lifetime():
    rows = [{"sourceRaceId": "001", "participantId": "hkjc:horse:HK_2026_A001"}]
    assert not career(
        ["001"], rows, kind="horse", source_id="HK_2026_A001", source_total=1
    )["completeLifetimeHistory"]
    with pytest.raises(RacingRejected, match="TOTAL_GAP"):
        career(["001"], rows, kind="jockey", source_id="HK_2026_A001", source_total=1)


def test_trials_rankings_and_jackpots_do_not_infer_source_semantics():
    with pytest.raises(RacingRejected, match="PLACING_NOT_DECLARED"):
        trial(
            {
                "kind": "barrier_trial",
                "orderMeaning": "running_order",
                "officialPlacing": 1,
                "date": "2026-10-01",
            }
        )
    rows = [
        {"sourceId": "001", "rank": 1, "tied": False, "value": "2"},
        {"sourceId": "002", "rank": 1, "tied": False, "value": "2"},
    ]
    with pytest.raises(RacingRejected, match="TIE_UNQUALIFIED"):
        rankings(
            ["001", "002"],
            rows,
            kind="jockey",
            start="2026-09-01",
            end="2026-10-01",
            metric="source_wins",
            unit="wins",
        )
    assert (
        jackpot(
            {
                "kind": "carryover",
                "currency": "HKD",
                "pool": "SOURCE_POOL",
                "amount": "00050.00",
                "observedAt": "2026-10-28T00:00:00Z",
            }
        )["amount"]
        == "50.00"
    )


def test_prospective_contract_records_actual_start_and_gaps_and_rejects_past_ticks():
    spec = {
        "kind": "odds",
        "market": "SOURCE_WIN",
        "unit": "source_quote",
        "notBefore": "2026-10-28T00:00:00Z",
        "retentionSeconds": 3600,
        "cadenceSeconds": 60,
    }
    row = {
        "kind": "odds",
        "market": "SOURCE_WIN",
        "rawUnit": "source_quote",
        "seriesId": "series",
        "sequence": 0,
        "selection": "01",
        "state": "open",
        "value": "2.50",
        "observedAt": "2026-10-28T00:01:00Z",
        "sourceAt": "2026-10-28T00:00:59Z",
    }
    receipt = prospective(spec, [row], end="2026-10-28T00:04:00Z")
    assert (
        receipt["samples"] == 1
        and receipt["gaps"]
        and not receipt["historicalTicksInferred"]
    )
    with pytest.raises(RacingRejected, match="HISTORICAL_TICK_REJECTED"):
        prospective(
            spec,
            [dict(row, sourceAt="2026-10-27T23:59:00Z")],
            end="2026-10-28T00:04:00Z",
        )
