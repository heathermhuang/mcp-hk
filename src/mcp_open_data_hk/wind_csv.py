"""Exact HKO provisional wind CSV layout, with native values retained."""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation

from .contracts import DomainError

REVISION = "hko-wind-five-columns-1"
DATASET = "hk-hko-rss-latest-ten-minute-wind-info"
BASE = "https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/"
DICTIONARY = BASE + "HKO_open_data_10min_wind_Documentation.pdf"
HEADERS = {
    BASE
    + "latest_10min_wind.csv": [
        "Date time",
        "Automatic Weather Station",
        "10-Minute Mean Wind Direction(Compass points)",
        "10-Minute Mean Speed(km/hour)",
        "10-Minute Maximum Gust(km/hour)",
    ],
    BASE
    + "latest_10min_wind_uc.csv": [
        "日期時間",
        "自動氣象站",
        "十分鐘平均風向（方位點）",
        "十分鐘平均風速（公里/小時）",
        "十分鐘最高陣風風速（公里/小時）",
    ],
    BASE
    + "latest_10min_wind_sc.csv": [
        "日期时间",
        "自动气象站",
        "十分钟平均风向（方位点）",
        "十分钟平均风速（公里/小时）",
        "十分钟最高阵风风速（公里/小时）",
    ],
}


def profile(resource):
    return (
        resource.get("datasetId") == DATASET
        and resource.get("format") == "CSV"
        and resource.get("url") in HEADERS
    )


def reject(message):
    raise DomainError("SOURCE_SCHEMA_CHANGED", message, 409)


def numeric(value, *, calm=False):
    if value == "N/A" or (calm and value == " "):
        return True
    try:
        return bool(value.strip()) and Decimal(value).is_finite()
    except (InvalidOperation, AttributeError, ValueError):
        return False


def annotate(resource, rows, schema):
    if not profile(resource):
        return
    headers = HEADERS[resource["url"]]
    columns = schema.get("sourceColumns", [])
    if (
        len(columns) != 5
        or [c.get("sourceHeader") for c in columns] != headers
        or {f["name"] for f in schema.get("fields", [])} != set(headers)
        or not rows
    ):
        reject("HKO wind CSV must retain its five published columns and data rows")
    for row in rows:
        if set(row) != set(headers) or not all(
            isinstance(row[k], str) for k in headers
        ):
            reject("HKO wind CSV row width or native field types changed")
        stamp = row[headers[0]]
        try:
            if not re.fullmatch(r"[0-9]{12}", stamp):
                raise ValueError()
            datetime.strptime(stamp, "%Y%m%d%H%M")
        except ValueError:
            reject("HKO wind timestamp violates its published calendar format")
        if not row[headers[1]].strip() or not row[headers[2]].strip():
            reject("HKO wind row lacks its native station/direction fields")
        if not numeric(row[headers[3]], calm=True) or not numeric(row[headers[4]]):
            reject("HKO wind values violate numeric/N/A/calm-space framing")
    schema["sourceContract"] = {
        "id": REVISION,
        "dictionaryUrl": DICTIONARY,
        "provisional": True,
        "declaredUpdateIntervalSeconds": 600,
        "scope": "Five published columns only; native strings, N/A and calm-space markers retained. A generated historical overflow field is not a source-declared column or a semantic binding.",
    }
    schema["timestampTimezoneQualification"] = "unreviewed_native_timestamp"
    schema["sourceRowMeaning"] = (
        "Original provisional wind CSV row; no unique station inventory, "
        "geographic binding or current-observation guarantee."
    )


def legacy_overflow(schema, field):
    """Compare a reviewed current five-column shape to retained legacy overflow.

    Current extra fields are rejected above. This does not discard old rows/schema
    or approve any additional source-declared field.
    """
    columns = schema.get("sourceColumns", [])
    return (
        schema.get("format") == "CSV"
        and len(columns) == 6
        and [c.get("sourceHeader") for c in columns[:5]] in list(HEADERS.values())
        and columns[5].get("name") == field["name"] == "_column_6"
        and columns[5].get("sourceHeader") is None
        and columns[5].get("columnIndex") == 6
        and set(field["types"]) <= {"null", "string"}
    )
