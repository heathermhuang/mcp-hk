"""Deterministic projections of inventoried representations and accepted receipts.

No source requests, semantic inference, status writes or second receipt cache.
"""

import json
import zlib
from urllib.parse import urlsplit

REVISION = "resource-capabilities-1"
OPERATIONS = ("records", "text_search", "typed_comparison", "nearby")
READERS = {
    "CSV": "table",
    "TXT": "table",
    "GTFS": "table_archive",
    "JSON": "json",
    "GEOJSON": "features",
    "XML": "xml",
    "GML": "xml_features",
    "KML": "xml_features",
    "XLSM": "workbook",
    "API": "api_unqualified",
    "XLSX": "workbook",
    "XLS": "workbook",
    "ARCGIS": "arcgis",
    "WFS": "wfs",
    "RSS": "feed",
    "ZIP": "archive",
    "KMZ": "archive",
    "PDF": "document_text",
    "WMS": "map_imagery",
}


def unpack(value):
    return json.loads(zlib.decompress(value) if isinstance(value, bytes) else value)


def family(resource):
    # An access family is a routing hint, never evidence that the URL returns it.
    path = urlsplit(resource.get("url", "")).path.lower()
    if "featureserver" in path or "mapserver" in path:
        return "arcgis"
    return READERS.get(resource.get("format", "").upper(), "unknown")


def operation(state, reason):
    return {"state": state, "reason": reason}


def project(resource, check=None, receipts=(), schema=None):
    check = check or {}
    status = check.get("status") or "pending"
    access = family(resource)
    accepted = []
    for receipt in receipts:
        if not receipt.get("schema_json") or not receipt.get("schema_hash"):
            continue
        observed = unpack(receipt["schema_json"])
        accepted.append(
            {
                "receiptKey": receipt.get("key"),
                "schemaFingerprint": receipt["schema_hash"],
                "selection": observed.get("sourceSelection")
                or {
                    "recordPath": observed.get("recordPath"),
                    "sheet": observed.get("sheet"),
                    "scope": "legacy_receipt_selection_not_fully_recorded",
                },
                "status": receipt.get("status"),
                "lastCheckedAt": receipt.get("checked"),
                "lastValidatedAt": receipt.get("validated"),
                "retrievedAt": receipt.get("retrieved"),
                "readerRevision": observed.get("readerContract"),
                "sourceContract": observed.get("sourceContract"),
                "sourceResponseComplete": observed.get("sourceResponseComplete"),
            }
        )
    if status in {"restricted", "unavailable", "schema_drift", "stale"}:
        state, reason = "held", check.get("reason") or status
    elif status == "needs_selection":
        state, reason = "requires_selection", check.get("reason") or status
    elif status == "queryable" and any(r["status"] == "queryable" for r in accepted):
        state, reason = "available", "accepted_receipt_selections_only"
    elif status in {"unsupported", "document", "needs_adapter"} or access in {
        "document_text",
        "map_imagery",
    }:
        state, reason = (
            "unsupported",
            check.get("reason") or "not_an_accepted_record_collection",
        )
    else:
        state, reason = "held", (
            "reader_support_unverified" if access != "unknown" else "reader_unknown"
        )
    operations = {
        "records": operation(state, reason),
        "text_search": operation(state, reason),
        "typed_comparison": operation(
            "requires_binding", "inspect_native_types_before_comparison"
        ),
        "nearby": operation("requires_binding", "no_qualified_point_binding"),
    }
    fields = []
    if schema is not None:
        for field in schema.get("fields", []) + schema.get("queryFields", []):
            if field.get("name") in {f["name"] for f in fields}:
                continue
            fields.append(
                {
                    **field,
                    "operators": (
                        ["eq", "contains"]
                        if "string" in field.get("types", [])
                        else ["eq"]
                    ),
                }
            )
    return {
        "revision": REVISION,
        "resourceId": resource["id"],
        "datasetId": resource["datasetId"],
        "representation": resource.get("format"),
        "readerFamily": access,
        "readerSupport": "unverified" if not accepted else "accepted_selections_only",
        "operations": operations,
        "acceptedSelections": accepted,
        "fields": fields,
        "semanticBinding": None,
        "entityKind": None,
        "access": {
            "status": status,
            "reason": check.get("reason"),
            "lastCheckedAt": check.get("checked"),
        },
        "observationTime": None,
        "completeness": "per_receipt_selection_only" if accepted else "unknown",
        "nextAction": {
            "tool": "hk_resource_schema",
            "arguments": {"resourceId": resource["id"]},
        },
    }


def summary(counts):
    return {
        "revision": REVISION,
        "records": operation(
            "available" if counts.get("queryable") else "held",
            (
                "inspect_representation_and_selection_receipts"
                if counts.get("queryable")
                else "no_accepted_record_capability"
            ),
        ),
        "semanticBinding": None,
        "entityKind": None,
    }
