"""Source-validation freshness and semantic qualifications, not data-age guesses."""

import re
import time

REVISION = "source-review-1"
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
    if any(
        x in cadence
        for x in ("annua", "yearly", "every year", "per year", "every 1 year")
    ):
        return 90 * DAY
    if any(
        x in cadence
        for x in ("quarter", "every six months", "every 6 months", "half-year")
    ):
        return 21 * DAY
    if "month" in cadence:
        return 7 * DAY
    if "week" in cadence:
        return DAY
    if any(x in cadence for x in ("daily", "every day", "day")):
        return 6 * 3600
    if any(x in cadence for x in ("minute", "hour", "real-time", "realtime")):
        return 300
    if any(
        x in cadence
        for x in ("necessary", "needed", "asneeded", "as and when", "asneeded")
    ):
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
