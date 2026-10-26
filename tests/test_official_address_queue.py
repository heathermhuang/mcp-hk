"""Capacity and cross-batch fairness, including one-read batches."""

from mcp_open_data_hk.curated.official_address_queue import capacity, interleave, retry


def test_one_read_batches_cannot_starve_refresh_or_initial():
    cohorts = {
        name: [{"entity_id": f"{name}:{i}"} for i in range(100)]
        for name in ["priority", "refresh", "initial", "retry"]
    }
    offset = 0
    seen = []
    for _ in range(20):
        target = interleave(cohorts, 1, offset)[0]
        offset = target["next_offset"]
        seen.append(target["cohort"])
        cohorts[target["cohort"]].pop(0)
    assert seen.count("priority") == 4
    assert seen.count("refresh") == 8
    assert seen.count("initial") == 6
    assert seen.count("retry") == 2
    assert len(interleave({"initial": cohorts["initial"]}, 10)) == 10


def test_capacity_is_optimistic_bound_and_never_claims_impossible_cycle():
    result = capacity(133108, 250)
    assert result["fullPassMinimumDaysAtCurrentCap"] == 533
    assert result["successfulReadsPerDayNeededFor90Days"] == 1479
    assert result["wholeSubset90DayCycleFeasible"] is False
    assert result["guaranteedWholeSubsetCycleDays"] is None


def test_no_match_schema_and_transient_retries_are_distinct():
    assert retry("SOURCE_NO_MATCH") == ("source_no_match", 30)
    assert retry("SOURCE_HTTP_400") == ("unresolved", 7)
    assert retry("INVALID_ADDRESS_JSON") == ("input_or_schema", 7)
    assert retry("SOURCE_NETWORK_FAILURE") == ("transient_or_budget", 1)
    assert retry("success") == ("observed", 90)


def test_due_no_match_retries_get_a_turn_during_large_initial_backlog():
    cohorts = {
        name: [{"entity_id": f"{name}:{i}"} for i in range(100)]
        for name in ["priority", "refresh", "initial", "retry"]
    }
    selected = interleave(cohorts, 10)
    assert [x["cohort"] for x in selected].count("retry") == 1
    assert [x["cohort"] for x in selected].count("initial") == 3
