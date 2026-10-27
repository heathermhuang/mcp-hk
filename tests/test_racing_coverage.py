import json
from datetime import date

from mcp_open_data_hk.racing_coverage import inventory, families
from mcp_open_data_hk.racing_store import RacingStore


def test_fixture_exceptions_and_pending_history_are_not_complete_season(tmp_path):
    store = RacingStore(tmp_path / "racing.sqlite3")
    meetings = [
        {"date": "2025-09-07", "venue": "ST", "plannedRaces": 10},
        {
            "date": "2025-09-24",
            "venue": "HV",
            "plannedRaces": 0,
            "programmeStatusRaw": "24",
        },
    ]
    with store.connect() as db:
        db.execute(
            "INSERT INTO racing_calendar VALUES(?,?,?,?,?)",
            ("2025-09", "now", "available", json.dumps({"meetings": meetings}), "{}"),
        )
        db.execute(
            "INSERT INTO racing_calendar VALUES(?,?,?,?,?)",
            ("2025-10", "now", "period_unavailable", '{"meetings":[]}', "{}"),
        )
        db.execute(
            "INSERT INTO racing_queue VALUES(?,?,?,NULL,0)",
            ("2025-09-07", "ST", "partial"),
        )
        result = inventory(db, date(2026, 10, 27))[0]
    assert result["originalHistoricalTarget"]
    assert result["fixtureEntries"] == 2
    assert result["meetingStates"] == {"partial": 1, "programme_without_race_count": 1}
    assert result["unavailableFixtureMonths"] == ["2025-10"]
    assert result["exceptions"][0]["cancellationVerified"] is False
    assert not result["seasonComplete"]


def test_only_accepted_versions_count_as_available_families(tmp_path):
    store = RacingStore(tmp_path / "racing.sqlite3")
    race = {
        "goingRaw": "GOOD",
        "courseRaw": "TURF",
        "results": [{"winOddsFinal": "4.50"}, {"winOddsFinal": None}],
    }
    with store.connect() as db:
        for version in ("accepted", "private", "retired"):
            db.execute(
                "INSERT INTO racing_snapshots VALUES(?,?,?,?)",
                (version, version, "now", json.dumps({"races": [race]})),
            )
        db.execute(
            "INSERT INTO racing_accepted VALUES(?,?,?,?,?,?)",
            ("meeting", "2026-10-25", "ST", "accepted", "now", "{}"),
        )
        result = {
            r["id"]: r
            for r in families(
                db,
                {"races": 1, "resultRows": 2},
                {"observedRaces": 0, "quotedRows": 0},
                {"accepted": 3, "available": True},
            )
        }
    assert result["track_conditions"]["trackRaces"] == 1
    assert result["final_win_odds"]["observedResultRows"] == 1
    assert result["final_dividends"]["acceptedRacesWithoutObservedQuotes"] == 1
    assert result["dated_profiles"]["enabled"]
    assert not result["full_profiles"]["enabled"]
    assert not result["sectionals"]["enabled"]
    assert not result["intraday_observations"]["enabled"]


def test_future_fixture_and_accepted_meeting_remain_separate(tmp_path):
    store = RacingStore(tmp_path / "racing.sqlite3")
    with store.connect() as db:
        db.execute(
            "INSERT INTO racing_calendar VALUES(?,?,?,?,?)",
            (
                "2026-10",
                "now",
                "available",
                json.dumps(
                    {
                        "meetings": [
                            {"date": "2026-10-25", "venue": "ST", "plannedRaces": 11},
                            {"date": "2026-10-28", "venue": "ST", "plannedRaces": 9},
                        ]
                    }
                ),
                "{}",
            ),
        )
        db.execute(
            "INSERT INTO racing_accepted VALUES(?,?,?,?,?,?)",
            ("meeting", "2026-10-25", "ST", "accepted", "now", "{}"),
        )
        result = inventory(db, date(2026, 10, 27))[0]
    assert result["season"] == "2026/27"
    assert result["meetingStates"] == {"accepted": 1, "not_yet_due": 1}
    assert not result["originalHistoricalTarget"]
