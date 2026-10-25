"""Strict offline normalization. Synthetic row contracts are not qualified HTML parsers."""

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from .policy import RacingRejected, checksum


def exact(value, pattern=r"[A-Za-z0-9_.-]{1,100}"):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise RacingRejected("INVALID_RACING_ID")
    return value


def participant(kind, source_id):
    if kind not in {"horse", "jockey", "trainer"}:
        raise RacingRejected("INVALID_PARTICIPANT_KIND")
    return f"hkjc:{kind}:" + exact(source_id)


def meeting(day, venue):
    date.fromisoformat(day)
    if venue not in {"ST", "HV"}:
        raise RacingRejected("UNQUALIFIED_VENUE")
    return f"hkjc:meeting:v1:{day}:{venue}"


def race(day, venue, number):
    if type(number) is not int or not 1 <= number <= 20:
        raise RacingRejected("INVALID_RACE_NUMBER")
    return meeting(day, venue) + f":{number:02d}"


def decimal_text(raw, *, nullable=False):
    if nullable and raw in {None, "", "--"}:
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"\d+(?:\.\d+)?", raw):
        raise RacingRejected("INVALID_DECIMAL_UNIT")
    try:
        number = Decimal(raw)
        if not number.is_finite():
            raise ValueError()
        return format(number, "f")
    except (ValueError, InvalidOperation) as exc:
        raise RacingRejected("INVALID_DECIMAL_UNIT") from exc


def elapsed(raw):
    if raw in {None, "", "--"}:
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"\d{1,2}:[0-5]\d\.\d{2}", raw):
        raise RacingRejected("UNKNOWN_TIME_FORMAT")
    minute, seconds = raw.split(":")
    return format(Decimal(minute) * 60 + Decimal(seconds), ".2f")


# Deliberately finite. New source codes require dictionary/fixture review.
STATUS = {
    "WV": "withdrawn",
    "WD": "withdrawn",
    "UR": "unseated",
    "DNF": "did_not_finish",
    "DISQ": "disqualified",
    "PU": "pulled_up",
    "FE": "fell",
    "WX": "withdrawn",
}


def placing(raw):
    if raw in STATUS:
        return {
            "placingRaw": raw,
            "placing": None,
            "status": STATUS[raw],
            "deadHeat": False,
        }
    match = re.fullmatch(r"([1-9]\d?)(\s+DH)?", raw) if isinstance(raw, str) else None
    if not match:
        raise RacingRejected("UNKNOWN_RESULT_CODE")
    return {
        "placingRaw": raw,
        "placing": int(match[1]),
        "status": "finished",
        "deadHeat": bool(match[2]),
    }


def result_row(row, race_id):
    required = {
        "horseId",
        "horseNumber",
        "draw",
        "placing",
        "time",
        "weightLb",
        "claimLb",
        "marginRaw",
    }
    if set(row) != required:
        raise RacingRejected("RESULT_LAYOUT_DRIFT")
    for field in ("horseNumber", "draw"):
        if row[field] is not None:
            exact(row[field], r"[0-9]{1,2}")
    horse_id = participant("horse", row["horseId"])
    outcome = placing(row["placing"])
    seconds = elapsed(row["time"])
    if outcome["status"] != "finished" and seconds is not None:
        raise RacingRejected("NON_FINISHER_TIME")
    if (
        not isinstance(row["marginRaw"], (str, type(None)))
        or len(row["marginRaw"] or "") > 40
    ):
        raise RacingRejected("INVALID_MARGIN")
    result = dict(
        outcome,
        raceId=race_id,
        participantId=horse_id,
        horseNumber=row["horseNumber"],
        draw=row["draw"],
        timeRaw=row["time"],
        timeSeconds=seconds,
        timePrecision="centisecond" if seconds else None,
        weightLb=decimal_text(row["weightLb"], nullable=True),
        claimLb=decimal_text(row["claimLb"], nullable=True),
        marginRaw=row["marginRaw"],
    )
    result["factId"] = race_id + ":" + horse_id
    result["revision"] = checksum(result)
    return result


def reconcile(expected_races, declarations, results):
    """Compare independent inventories, preserving withdrawals and explicit empty groups."""
    if len(set(expected_races)) != len(expected_races) or not expected_races:
        raise RacingRejected("INVALID_MEETING_INVENTORY")
    if set(expected_races) != set(declarations) or set(expected_races) != set(results):
        raise RacingRejected("INCOMPLETE_MEETING")
    output = []
    for race_id in sorted(expected_races):
        declared = declarations[race_id]
        rows = results[race_id]
        ids = [row["participantId"] for row in rows]
        if (
            not declared
            or len(set(declared)) != len(declared)
            or len(set(ids)) != len(ids)
        ):
            raise RacingRejected("DUPLICATE_OR_EMPTY_RUNNERS")
        if set(declared) != set(ids):
            raise RacingRejected("DECLARED_RUNNER_GAP")
        ties = {}
        for row in rows:
            if row["placing"] is not None:
                ties.setdefault(row["placing"], []).append(row)
        for group in ties.values():
            if (len(group) > 1) != all(row["deadHeat"] for row in group) or (
                len(group) == 1 and group[0]["deadHeat"]
            ):
                raise RacingRejected("UNRECONCILED_DEAD_HEAT")
        output.append(
            {
                "raceId": race_id,
                "declared": len(declared),
                "results": len(rows),
                "runnerSetSha256": checksum(sorted(ids)),
                "complete": True,
            }
        )
    return output


def sectional(row):
    if row["kind"] not in {"race", "runner"} or row["unit"] != "seconds":
        raise RacingRejected("SECTIONAL_KIND_OR_UNIT")
    if type(row["segment"]) is not int or row["segment"] < 1:
        raise RacingRejected("SECTIONAL_SEGMENT")
    if type(row["distanceM"]) is not int or row["distanceM"] <= 0:
        raise RacingRejected("SECTIONAL_DISTANCE")
    return dict(row, seconds=decimal_text(row["seconds"]))


def dividend(row):
    if row["semantics"] not in {"ordered", "unordered"} or row["currency"] != "HKD":
        raise RacingRejected("DIVIDEND_SEMANTICS_OR_UNIT")
    if row["status"] not in {"payout", "refund", "carryover", "jackpot"}:
        raise RacingRejected("DIVIDEND_STATUS")
    combination = row["combination"]
    if not isinstance(combination, list) or not combination:
        raise RacingRejected("DIVIDEND_COMBINATION")
    for number in combination:
        exact(number, r"[0-9]{1,2}")
    # F/M notation requires an independently documented dictionary; never guess.
    if row["semantics"] == "unordered":
        combination = sorted(combination, key=int)
    return dict(
        row,
        combination=combination,
        amount=decimal_text(row["amount"], nullable=True),
        stakeHkd=decimal_text(row["stakeHkd"]),
    )
