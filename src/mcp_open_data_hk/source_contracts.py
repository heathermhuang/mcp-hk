"""Narrow provider-declared type variations; source values are never rewritten."""

from urllib.parse import parse_qs, urlsplit
from datetime import date

from .contracts import DomainError

HKO_WARNING = "hko-rhrread-warning-1"
CSV_DATE_PREAMBLE = "csv-date-preamble-1"


def date_only_header(values):
    values = [str(v).strip() for v in values if v is not None and str(v).strip()]
    if len(values) != 1:
        return False
    try:
        return date.fromisoformat(values[0]).isoformat() == values[0]
    except ValueError:
        return False


HKO_DICTIONARY = (
    "https://www.hko.gov.hk/tc/weatherAPI/doc/files/HKO_Open_Data_API_Documentation.pdf"
)


def annotate(resource, rows, schema):
    url = urlsplit(resource["url"])
    if (
        resource.get("datasetId") != "hk-hko-rss-current-weather-report"
        or url.hostname != "data.weather.gov.hk"
        or url.path != "/weatherAPI/opendata/weather.php"
        or parse_qs(url.query).get("dataType") != ["rhrread"]
        or not any(f["name"] == "warningMessage" for f in schema.get("fields", []))
    ):
        return
    for row in rows:
        value = row.get("warningMessage")
        if value != "" and not (
            isinstance(value, list) and all(isinstance(x, str) for x in value)
        ):
            raise DomainError(
                "SOURCE_SCHEMA_CHANGED",
                "HKO warningMessage violates its declared array-or-empty-string contract",
                409,
            )
    schema["sourceContract"] = {
        "id": HKO_WARNING,
        "dictionaryUrl": HKO_DICTIONARY,
        "scope": "Only warningMessage array/empty-string variation. Other inferred field changes remain subject to drift checks. Raw source values are retained.",
    }


def comparable_fields(schema, contract=None):
    fields = []
    columns = schema.get("sourceColumns", [])
    aliases = (
        {c["name"]: "_column_" + str(c["columnIndex"]) for c in columns}
        if contract == CSV_DATE_PREAMBLE
        and date_only_header(c.get("sourceHeader") for c in columns)
        else {}
    )
    for field in schema.get("fields", []):
        types = [t for t in field["types"] if t != "null"]
        if (
            contract == HKO_WARNING
            and field["name"] == "warningMessage"
            and types
            and set(types) <= {"array", "string"}
        ):
            types = ["array", "string"]
        fields.append(
            {"name": aliases.get(field["name"], field["name"]), "types": types}
        )
    return sorted(fields, key=lambda field: field["name"])
