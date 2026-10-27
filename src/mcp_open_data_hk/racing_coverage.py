"""Accepted factual coverage and explicit fixture exceptions; no source requests."""

import json
from collections import Counter
from datetime import date, datetime, timezone


def season(day):
    year = day.year if day.month >= 9 else day.year - 1
    return f"{year}/{str(year + 1)[-2:]}"


def inventory(db, today=None):
    today = today or datetime.now(timezone.utc).date()
    queued = {
        (r["day"], r["venue"]): r["state"]
        for r in db.execute("SELECT day,venue,state FROM racing_queue")
    }
    accepted = {
        (r["day"], r["venue"])
        for r in db.execute("SELECT day,venue FROM racing_accepted")
    }
    groups = {}
    for row in db.execute(
        "SELECT period,state,payload FROM racing_calendar ORDER BY period"
    ):
        period = date.fromisoformat(row["period"] + "-01")
        group = groups.setdefault(
            season(period),
            {
                "observedFixtureMonths": [],
                "meetings": {},
                "unavailableFixtureMonths": [],
            },
        )
        if row["state"] != "available":
            group["unavailableFixtureMonths"].append(row["period"])
            continue
        group["observedFixtureMonths"].append(row["period"])
        for meeting in json.loads(row["payload"])["meetings"]:
            group["meetings"][(meeting["date"], meeting["venue"])] = meeting
    result = []
    for name, group in sorted(groups.items()):
        first_year = int(name[:4])
        all_months = [f"{first_year}-{month:02d}" for month in range(9, 13)] + [
            f"{first_year + 1}-{month:02d}" for month in range(1, 9)
        ]
        states, exceptions = Counter(), []
        for key, meeting in sorted(group["meetings"].items()):
            if date.fromisoformat(key[0]) >= today:
                states["not_yet_due"] += 1
            elif key in accepted:
                states["accepted"] += 1
            elif meeting["plannedRaces"] == 0:
                states["programme_without_race_count"] += 1
                exceptions.append(
                    {
                        **meeting,
                        "state": "programme_without_race_count",
                        "cancellationVerified": False,
                    }
                )
            else:
                states[queued.get(key, "not_queued")] += 1
        result.append(
            {
                "season": name,
                "originalHistoricalTarget": name == "2025/26",
                "observedFixtureMonths": group["observedFixtureMonths"],
                "unavailableFixtureMonths": group["unavailableFixtureMonths"],
                "unobservedFixtureMonths": [
                    month
                    for month in all_months
                    if month not in group["observedFixtureMonths"]
                    and month not in group["unavailableFixtureMonths"]
                ],
                "fixtureEntries": len(group["meetings"]),
                "meetingStates": dict(sorted(states.items())),
                "exceptions": exceptions,
                "seasonComplete": False,
                "scope": "retained fixture inventory; missing months and zero-count programme entries do not establish no racing",
            }
        )
    return result


def families(db, totals, dividends, profiles):
    # Only accepted versions contribute. Private candidates and retired versions
    # must never inflate current coverage or make a missing family look available.
    races = totals["races"]
    observed = dict(
        db.execute(
            "SELECT coalesce(sum(coalesce(trim(json_extract(r.value,'$.goingRaw')),'')<>''),0) AS trackRaces,coalesce(sum(coalesce(trim(json_extract(r.value,'$.courseRaw')),'')<>''),0) AS courseRaces FROM racing_accepted a JOIN racing_snapshots s USING(version),json_each(s.payload,'$.races') r"
        ).fetchone()
    )
    odds = db.execute(
        "SELECT count(*) FROM racing_accepted a JOIN racing_snapshots s USING(version),json_each(s.payload,'$.races') r,json_each(r.value,'$.results') f WHERE json_extract(f.value,'$.winOddsFinal') IS NOT NULL"
    ).fetchone()[0]
    enabled = [
        {"id": "results", "enabled": bool(races), "observedRaces": races},
        {
            "id": "participant_identities",
            "enabled": bool(races),
            "observedRaces": races,
        },
        {
            "id": "dated_profiles",
            "enabled": profiles["available"],
            "acceptedParticipants": profiles["accepted"],
            "completeCareerHistory": False,
        },
        {
            "id": "final_dividends",
            "enabled": bool(dividends["observedRaces"]),
            "observedRaces": dividends["observedRaces"],
            "acceptedRacesWithoutObservedQuotes": races - dividends["observedRaces"],
            "quotedRows": dividends["quotedRows"],
            "stakeNormalized": False,
        },
        {
            "id": "final_win_odds",
            "enabled": bool(odds),
            "observedResultRows": odds,
            "acceptedResultRows": totals["resultRows"],
            "intradayHistory": False,
        },
        {
            "id": "track_conditions",
            "enabled": bool(observed["trackRaces"]),
            **observed,
            "acceptedRaces": races,
            "scope": "source-displayed going and course in accepted results",
        },
    ]
    for name, reason in (
        ("declarations", "independent_declared_runner_inventory_not_reconciled"),
        ("full_profiles", "complete_participant_and_career_history_not_established"),
        ("sectionals", "no_accepted_sectional_source_capture"),
        ("trials", "no_accepted_trial_inventory"),
        ("jockey_rankings", "no_accepted_ranking_inventory"),
        ("trainer_rankings", "no_accepted_ranking_inventory"),
        ("jackpots", "no_accepted_jackpot_observations"),
        ("odds_combinations", "no_accepted_market_combination_inventory"),
        ("pool_investments", "no_accepted_pool_observations"),
        ("racing_changes", "no_accepted_change_series"),
        (
            "intraday_observations",
            "prospective_series_not_started_past_ticks_not_inferred",
        ),
        ("narrative_comments", "source_and_output_modes_not_qualified"),
    ):
        from .curated.racing.families import DEPENDENCIES

        enabled.append(
            {
                "id": name,
                "enabled": False,
                "reasonCode": reason,
                "sourceDependencies": DEPENDENCIES[name],
                "providerParserQualified": False,
            }
        )
    return enabled
