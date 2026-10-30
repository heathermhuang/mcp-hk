"""Source-scoped observation checks; never infer freshness from a download."""

import math
import time
from datetime import datetime
from urllib.parse import parse_qs, urlsplit

from .contracts import DomainError

REVISION = "hko-station-observations-1"
DICTIONARY = (
    "https://www.hko.gov.hk/en/weatherAPI/doc/files/HKO_Open_Data_API_Documentation.pdf"
)


def hko_current(resource):
    url = urlsplit(resource.get("url", ""))
    return (
        resource.get("datasetId") == "hk-hko-rss-current-weather-report"
        and url.hostname == "data.weather.gov.hk"
        and url.path == "/weatherAPI/opendata/weather.php"
        and parse_qs(url.query).get("dataType") == ["rhrread"]
    )


def timestamp(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if date.tzinfo is not None:
            return date.timestamp()
    except (AttributeError, TypeError, ValueError, OverflowError):
        pass
    raise DomainError(
        "SOURCE_SCHEMA_CHANGED",
        "Observation time must include its source timezone",
        422,
    )


def qualify(resource, rows, schema):
    series = {
        "temperature/data": ("temperature", "C"),
        "humidity/data": ("humidity", "percent"),
    }
    choice = series.get(schema.get("recordPath"))
    if not hko_current(resource) or choice is None:
        return
    family, unit = choice
    context = schema.get("sourceContext", {}).get(family, {})
    observed = context.get("recordTime")
    observed_at = timestamp(observed)
    if observed_at > time.time() + 300:
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Observation time is in the future", 422
        )
    if not rows:
        raise DomainError("INCOMPLETE_SOURCE", "No station observations supplied", 422)
    identities = set()
    for row in rows:
        place, value = row.get("place"), row.get("value")
        if (
            not isinstance(place, str)
            or not place.strip()
            or place in identities
            or row.get("unit") != unit
            or type(value) not in {int, float}
            or not math.isfinite(value)
            or (family == "humidity" and not 0 <= value <= 100)
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED",
                "Station observation violates its identity, numeric value or unit contract",
                422,
            )
        identities.add(place)
    for field in schema.get("fields", []):
        if field["name"] == "value":
            field["unit"] = unit
    schema["observationQuality"] = {
        "contract": REVISION,
        "dictionaryUrl": DICTIONARY,
        "series": family,
        "observedAt": observed,
        "rowCount": len(rows),
        "uniqueStationCount": len(identities),
        "unit": unit,
        "checks": [
            "required_fields",
            "unique_station",
            "finite_numeric_value",
            "source_unit",
            "timezone_timestamp",
        ]
        + (["humidity_range"] if family == "humidity" else []),
        "scope": "All observations in this selected source response; not a fixed station inventory or complete weather coverage.",
        "maxAgeSeconds": 7200,
        "freshnessPolicy": "Operational two-hour observation target, not a provider availability guarantee.",
    }


def observation_freshness(schema, now=None):
    quality = schema.get("observationQuality")
    if not quality:
        return None
    now = time.time() if now is None else now
    observed = timestamp(quality["observedAt"])
    age = max(0, now - observed)
    return {
        "observedAt": quality["observedAt"],
        "ageSeconds": round(age),
        "maxAgeSeconds": quality["maxAgeSeconds"],
        "freshUntil": observed + quality["maxAgeSeconds"],
        "stale": now >= observed + quality["maxAgeSeconds"] or observed > now + 300,
        "basis": "source_record_time",
    }
