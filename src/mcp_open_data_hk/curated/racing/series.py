"""Prospective series receipts: measured cadence and gaps; never invented history."""

from decimal import Decimal

from .policy import RacingRejected, utc
from .normalize import decimal_text, exact


def observation(row):
    if row["kind"] not in {"odds", "pool_investments", "changes"}:
        raise RacingRejected("UNKNOWN_OBSERVATION_KIND")
    if row["state"] not in {"open", "suspended", "closed", "corrected"}:
        raise RacingRejected("UNKNOWN_MARKET_STATE")
    exact(row["seriesId"])
    exact(row["selection"])
    if type(row["sequence"]) is not int or row["sequence"] < 0:
        raise RacingRejected("INVALID_OBSERVATION_SEQUENCE")
    observed = utc(row["observedAt"])
    source = utc(row["sourceAt"]) if row.get("sourceAt") else None
    if source and source > observed:
        raise RacingRejected("SOURCE_CLOCK_AHEAD")
    value = decimal_text(row.get("value"), nullable=True)
    if row["state"] == "open" and value is None:
        raise RacingRejected("OPEN_MARKET_VALUE_REQUIRED")
    if not row.get("rawUnit") or len(row["rawUnit"]) > 40:
        raise RacingRejected("OBSERVATION_UNIT_REQUIRED")
    return dict(
        row,
        value=value,
        delaySeconds=(
            str(Decimal(str((observed - source).total_seconds()))) if source else None
        ),
    )


def series_receipt(rows, cadence_seconds, *, end):
    if type(cadence_seconds) is not int or cadence_seconds < 1:
        raise RacingRejected("INVALID_CADENCE")
    if not rows:
        return {
            "actualStart": None,
            "samples": 0,
            "measuredIntervals": [],
            "gaps": [],
            "state": "not_started",
        }
    parsed = [observation(row) for row in rows]
    keys = [(row["seriesId"], row["sequence"], row["selection"]) for row in parsed]
    if len(set(keys)) != len(keys):
        raise RacingRejected("DUPLICATE_OBSERVATION")
    if len({row["seriesId"] for row in parsed}) != 1:
        raise RacingRejected("MIXED_SERIES")
    # Selections at one request timestamp represent a single sample, not extra cadence.
    times = sorted({utc(row["observedAt"]) for row in parsed})
    finish = utc(end)
    if finish < times[-1]:
        raise RacingRejected("SERIES_WINDOW_REJECTED")
    gaps, intervals = [], []
    for index, (left, right) in enumerate(zip(times, times[1:] + [finish])):
        elapsed = (right - left).total_seconds()
        if index < len(times) - 1:
            intervals.append(elapsed)
        if elapsed > cadence_seconds * 1.5:
            gaps.append(
                {
                    "after": left.isoformat(),
                    "before": right.isoformat(),
                    "missingSamplesAtLeast": max(
                        1, int(elapsed // cadence_seconds) - 1
                    ),
                }
            )
    return {
        "actualStart": times[0].isoformat(),
        "observedThrough": times[-1].isoformat(),
        "samples": len(times),
        "measuredIntervals": intervals,
        "targetCadenceSeconds": cadence_seconds,
        "gaps": gaps,
        "state": "observed",
        "historicalOddsInferred": False,
    }


def capacity(*, samples_per_day, markets, selections, bytes_per_row, retention_days):
    values = (samples_per_day, markets, selections, bytes_per_row, retention_days)
    if any(type(value) is not int or value <= 0 for value in values):
        raise RacingRejected("CAPACITY_INPUT_REJECTED")
    raw = samples_per_day * markets * selections * bytes_per_row * retention_days
    # Explicit conservative engineering allocation, not measured provider capacity.
    total = raw * 8  # rows + indexes + WAL + dump + staging + offsite restore.
    return {
        "rawBytes": raw,
        "reservedPeakBytes": total,
        "withinInitialOneGiB": total <= 1024**3,
        "measured": False,
    }
