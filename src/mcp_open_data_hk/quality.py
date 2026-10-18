"""Source-validation freshness and semantic qualifications, not data-age guesses."""

import re
import time
from datetime import datetime, timezone

REVISION = "source-review-9"
DAY = 86400
HELD = {
    "unsupported",
    "schema_drift",
    "capacity_limited",
    "needs_selection",
    "needs_adapter",
}


def review_interval(dataset, resource):
    cadence = re.sub(r"\s+", " ", str(dataset.get("updateCadence") or "").casefold())
    if any(
        x in cadence
        for x in (
            "one-off",
            "one off",
            "not be further updated",
            "not updated",
            "no further update",
        )
    ):
        return 365 * DAY
    years = [int(x) for x in re.findall(r"\b(?:19|20)\d{2}\b", cadence)]
    if (
        cadence.startswith("only ")
        and "period" in cadence
        and "available" in cadence
        and len(years) >= 2
        and max(years) < datetime.now(timezone.utc).year
    ):
        return 90 * DAY
    intervals = []
    if re.search(r"\b(minute|hourly|every hour|real-time|realtime)\b", cadence):
        intervals.append(300)
    if re.search(r"\b(daily|every day|per day)\b", cadence):
        intervals.append(6 * 3600)
    if re.search(r"\b(weekly|every week|per week)\b", cadence):
        intervals.append(DAY)
    if re.search(
        r"\b(monthly|once a month|once per month|twice a month|every one month|every 1 month)\b",
        cadence,
    ):
        intervals.append(7 * DAY)
    if any(
        x in cadence
        for x in (
            "quarter",
            "every six months",
            "every 6 months",
            "every three months",
            "every 3 months",
            "half-year",
        )
    ):
        intervals.append(21 * DAY)
    if any(
        x in cadence
        for x in ("annua", "yearly", "every year", "per year", "every 1 year")
    ):
        intervals.append(90 * DAY)
    if intervals:
        # Compound cadence descriptions use their fastest declared update, never
        # the slow exception (e.g. monthly tables with some annual columns).
        return min(intervals)
    if any(x in cadence for x in ("necessary", "needed", "asneeded", "as and when")):
        return 7 * DAY
    return 3600 if resource.get("isApi") else DAY


def freshness(dataset, resource, validated, ttl=None, now=None):
    now = time.time() if now is None else now
    cache_ttl = ttl or (300 if resource.get("isApi") else DAY)
    review = review_interval(dataset, resource)
    age = max(0, now - validated) if validated else None
    return {
        "lastValidatedAt": validated,
        "validationAgeSeconds": round(age) if age is not None else None,
        "cacheTtlSeconds": cache_ttl,
        "cacheExpired": age is None or age >= cache_ttl,
        "reviewIntervalSeconds": review,
        "nextReviewAt": validated + review if validated else None,
        "reviewOverdue": age is None or age >= review,
        "policyVersion": REVISION,
        "scope": "Source validation only; publication dates, reference periods and record observations are separate.",
    }


def semantic_quality(schema):
    fields = schema.get("fields", [])
    positional = any(re.match(r"^_column_\d+$", f.get("name", "")) for f in fields)
    return {
        "level": "raw_source",
        "semanticVerification": "not_performed",
        "headerVerified": (
            False if schema.get("headerVerification") or positional else None
        ),
        "hasPositionalColumns": positional,
        "fieldUnitsAnnotated": any(f.get("unit") is not None for f in fields),
        "sourceResponseScope": schema.get("scope"),
        "note": "A parsed source response is not a verified analytical table. Preserve source grain, units, dates and qualifications.",
    }
