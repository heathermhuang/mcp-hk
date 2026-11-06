"""Exact HKO forecast-track list, including its documented empty state."""

import hashlib
import re
from urllib.parse import urlsplit

from defusedxml import ElementTree

from .contracts import DomainError
from .resource_formats import parse

REVISION = "hko-cyclone-list-1"
DATASET = "hk-hko-rss-tc-track-info"
URL = "https://www.weather.gov.hk/wxinfo/currwx/tc_list.xml"
DICTIONARY = (
    "https://www.weather.gov.hk/wxinfo/currwx/HKO_TCTrackInfo_DataDictionary_en.pdf"
)
FIELDS = (
    "TropicalCycloneID",
    "TropicalCycloneChineseName",
    "TropicalCycloneEnglishName",
    "TropicalCycloneURL",
)


def profile(resource):
    return (
        resource.get("datasetId") == DATASET
        and resource.get("format") == "XML"
        and resource.get("url") == URL
    )


def validate_selectors(record_path, sheet, layer):
    if record_path not in {"", "TropicalCyclone"} or sheet or layer is not None:
        raise DomainError(
            "INVALID_QUERY", "Use the complete published TropicalCyclone list", 400
        )


def reject(message):
    raise DomainError("SOURCE_SCHEMA_CHANGED", message, 409)


def read(body, record_path="", sheet="", layer=None):
    validate_selectors(record_path, sheet, layer)
    root = ElementTree.fromstring(body)
    if root.tag != "TropicalCycloneList" or root.attrib or (root.text or "").strip():
        reject("Expected the complete published TropicalCycloneList XML container")
    for item in root:
        if (
            item.tag != "TropicalCyclone"
            or item.attrib
            or (item.text or "").strip()
            or (item.tail or "").strip()
            or len(item) != 4
            or {child.tag for child in item} != set(FIELDS)
        ):
            reject("Tropical cyclone list elements changed")
        values = {}
        for child in item:
            if child.attrib or len(child) or (child.tail or "").strip():
                reject("Expected simple native cyclone-list text fields")
            values[child.tag] = child.text or ""
        if not re.fullmatch(r"[0-9]{4}", values["TropicalCycloneID"]):
            reject("Expected the native four-digit HKO cyclone identifier")
        if not all(values[k].strip() for k in FIELDS):
            reject("Required tropical cyclone list text is missing")
        link = urlsplit(values["TropicalCycloneURL"])
        if (
            link.scheme not in {"http", "https"}
            or not link.hostname
            or link.username
            or link.password
        ):
            reject("Expected a public-format source-provided track URL")
    rows, schema = parse(body, "XML", record_path, sheet)
    if len(rows) != len(root):
        reject("Cyclone list extraction does not match its XML item count")
    empty = not rows
    if empty:
        schema["fields"] = [
            {
                "name": name,
                "types": ["string"],
                "scalarKinds": [],
                "unit": None,
                "missingCount": 0,
                "absentCount": 0,
                "nullCount": 0,
                "observedValueCount": 0,
                "typeBasis": "publisher_declared_xml_text",
            }
            for name in sorted(FIELDS)
        ]
    schema.update(
        sourceContract={
            "id": REVISION,
            "dictionaryUrl": DICTIONARY,
            "declaredFields": list(FIELDS),
            "emptyRule": "HKO defines absent TropicalCyclone items when it issues no forecast track.",
        },
        observedSerialization="hko_forecast_track_list_xml",
        sourceContentHash=hashlib.sha256(body).hexdigest(),
        sourceResponseBytes=len(body),
        sourceFramingFullyConsumed=True,
        sourceEmptyCollection=empty,
        schemaTypeBasis="publisher_declared_xml_text" if empty else "observed_xml_text",
        sourceRowMeaning="Original HKO-listed forecast-track entry; no global cyclone inventory or safety qualification.",
        sourceCachePolicy="Operational five-minute list-validation target, not an HKO update or availability guarantee.",
    )
    return rows, schema
