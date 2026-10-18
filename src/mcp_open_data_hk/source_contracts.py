"""Narrow provider-declared type variations; source values are never rewritten."""

from urllib.parse import parse_qs, urlsplit

from .contracts import DomainError

HKO_WARNING = "hko-rhrread-warning-1"
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
    for field in schema.get("fields", []):
        types = [t for t in field["types"] if t != "null"]
        if (
            contract == HKO_WARNING
            and field["name"] == "warningMessage"
            and types
            and set(types) <= {"array", "string"}
        ):
            types = ["array", "string"]
        fields.append({"name": field["name"], "types": types})
    return fields
