"""Narrow, byte-complete readers for observed publisher serializations."""

import hashlib
import json
import re
from pathlib import Path

from .contracts import DomainError
from .resource_formats import MAX_ROWS, invalid, no_duplicates, parse, text

FSD_PREFIX = "http://www.hkfsd.gov.hk/datagovhk/datasets/"
FSD_FILES = {
    "Fire_Protection_Prevention_Targets_eng.xlsx",
    "Fire_Protection_Prevention_Targets_chi.xlsx",
    "Fire_Service_Indicators_FP_eng.xlsx",
    "Fire_Service_Indicators_FP_chi.xlsx",
    "Ambulance_Service_Indicators_eng.xlsx",
    "Ambulance_Service_Indicators_chi.xlsx",
    "Ambulance_Service_Indicators_sc.xlsx",
    "Fire_Protection_Prevention_Indicators_eng.xlsx",
    "Fire_Protection_Prevention_Indicators_chi.xlsx",
    "Fire_Service_Indicator_eng.xlsx",
    "Fire_Service_Indicator_chi.xlsx",
    "Fire_Service_Indicators_sc.xlsx",
}
FSD_URLS = {
    prefix + name
    for prefix in [FSD_PREFIX, FSD_PREFIX.replace("http:", "https:")]
    for name in FSD_FILES
}
AUD_URLS = {
    "https://www.aud.gov.hk/datagovhk/" + name
    for name in [
        "vfm-by-subjects.json",
        "accounts-certified.json",
        "performance-indicators.json",
        "vfm-by-auditees.json",
    ]
}
NOTIFICATIONS = "https://ogcmn.one.gov.hk/ogcmn/service/list/catwc/OGCMN*"
HKSTP_RECRUITMENT = "https://opendata.hkstp.org/corporate/recruitment/v1/"
TID_URLS = {
    "https://www.tid.gov.hk/service/utf/messageFromUs" + language + ".do"
    for language in ["En", "Tc", "Sc"]
}


def object_sequence(body, comma_separated=False):
    decoded, _ = text(body)
    decoder = json.JSONDecoder(
        object_pairs_hook=no_duplicates,
        parse_constant=lambda _: invalid("Nonfinite JSON number"),
    )
    values = []
    position = 0
    while position < len(decoded):
        while position < len(decoded) and decoded[position] in " \t\r\n":
            position += 1
        if position == len(decoded):
            break
        value, position = decoder.raw_decode(decoded, position)
        if not isinstance(value, dict):
            # Valid standard JSON still uses the ordinary reader. Never repair arrays.
            return None
        values.append(value)
        if len(values) > MAX_ROWS:
            invalid("Object sequence exceeds row budget", "SOURCE_TOO_LARGE")
        if comma_separated:
            while position < len(decoded) and decoded[position] in " \t\r\n":
                position += 1
            if position == len(decoded):
                break
            if decoded[position] != ",":
                invalid("Expected comma between complete source objects")
            position += 1
            while position < len(decoded) and decoded[position] in " \t\r\n":
                position += 1
            if position == len(decoded):
                invalid("Source object sequence ends with an incomplete separator")
    if len(values) < 2:
        return None
    return json.dumps(values, ensure_ascii=False).encode()


def read(resource, body, record_path="", sheet="", layer=None):
    if isinstance(body, Path):
        return None
    url, fmt = resource["url"], resource["format"]
    kind = None
    decoded = body
    actual_format = fmt
    if url in FSD_URLS and fmt == "XLSX" and not body.startswith(b"PK"):
        if sheet or record_path or layer is not None:
            raise DomainError(
                "INVALID_QUERY",
                "This source is a flat CSV response, without workbook/map selectors",
                400,
            )
        kind, actual_format = "flat_csv_advertised_as_xlsx", "CSV"
    elif url in AUD_URLS and fmt == "JSON":
        comma_separated = url.endswith("/accounts-certified.json")
        decoded = object_sequence(body, comma_separated)
        if decoded is None:
            return None
        kind = (
            "complete_top_level_comma_separated_json_object_sequence"
            if comma_separated
            else "complete_top_level_json_object_sequence"
        )
    elif url == NOTIFICATIONS and fmt == "JSON":
        value, _ = text(body)
        match = re.fullmatch(r"\s*NotiList\((.*)\)\s*;\s*", value, re.DOTALL)
        if not match:
            invalid("Expected the complete published NotiList JSONP wrapper")
        decoded = match[1].encode()
        kind = "fixed_NotiList_jsonp_wrapper"
    elif url == HKSTP_RECRUITMENT and fmt == "JSON":
        value, _ = text(body)
        outer = json.loads(value)
        if not isinstance(outer, str):
            return None
        inner = json.loads(
            outer,
            object_pairs_hook=no_duplicates,
            parse_constant=lambda _: invalid("Nonfinite JSON number"),
        )
        if not isinstance(inner, list) or not all(
            isinstance(row, dict) for row in inner
        ):
            invalid("Expected the complete HKSTP recruitment array in a JSON string")
        if sheet or layer is not None:
            invalid("This JSON response has no workbook/map selectors", "INVALID_QUERY")
        decoded = outer.encode()
        kind = "hkstp_recruitment_array_in_json_string"
    elif url in TID_URLS and fmt == "XML":
        trimmed = body.lstrip(b" \t\r\n")
        kind = "tid_xml_DATA_document"
        if trimmed != body and trimmed.startswith(b"<?xml"):
            decoded = trimmed
            kind = "xml_declaration_after_whitespace_prefix"
        if sheet or layer is not None:
            invalid("This XML response has no workbook/map selectors", "INVALID_QUERY")
    if kind is None:
        return None
    rows, schema = parse(decoded, actual_format, record_path, sheet)
    if url in TID_URLS and schema.get("rootTag") != "DATA":
        invalid("Expected the published TID DATA XML root")
    if url == NOTIFICATIONS:
        container = schema.get("sourceContext", {}).get("notifications")
        if not isinstance(container, dict) or "sourceArrayLength" not in container:
            invalid("Expected the published notifications array")
    if actual_format == "CSV" and (not rows or len(rows[0]) < 2):
        invalid("Expected a complete multi-column flat CSV response")
    schema.update(
        advertisedFormat=fmt,
        observedSerialization=kind,
        serializationRevision="provider-serialization-1",
        sourceContentHash=hashlib.sha256(body).hexdigest(),
        sourceResponseBytes=len(body),
        sourceFramingFullyConsumed=True,
    )
    if url == NOTIFICATIONS:
        schema["rowMeaning"] = (
            "Original published notice; schedule and expiry values are retained, "
            "without an active-notice claim."
        )
    return rows, schema
