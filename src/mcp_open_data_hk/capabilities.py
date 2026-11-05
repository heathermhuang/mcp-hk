"""Deterministic projections of inventoried representations and accepted receipts.

No source requests, semantic inference, status writes or second receipt cache.
"""

import json
import zlib
from urllib.parse import urlsplit
from .resource_fields import field_catalogue
from .source_contracts import typed_bindings
from .spatial_profiles import accepted_binding, profile_for, dataset_kind
from .resource_protocols import protocol, HKMA_PAGING_CONTRACT

REVISION = "resource-capabilities-3"
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
    if protocol(resource):
        return READERS[protocol(resource)]
    path = urlsplit(resource.get("url", "")).path.lower()
    if "featureserver" in path or "mapserver" in path:
        return "arcgis"
    return READERS.get(resource.get("format", "").upper(), "unknown")


def operation(state, reason):
    return {"state": state, "reason": reason}


def public_selection(schema):
    raw = schema.get("sourceSelection")
    if raw:
        result = {
            key: raw[key]
            for key in ("recordPath", "sheet", "layer", "scope")
            if key in raw
        }
        names = raw.get("parameterNames") or sorted(
            (raw.get("parameters") or {}).keys()
        )
        if names:
            result["parameterNames"] = names
            result["parameterValues"] = "not_disclosed"
        return result
    return {
        "recordPath": schema.get("recordPath"),
        "sheet": schema.get("sheet"),
        "scope": "legacy_receipt_selection_not_fully_recorded",
    }


def project(resource, check=None, receipts=(), schema=None):
    check = check or {}
    status = check.get("status") or "pending"
    access = family(resource)
    accepted = []
    hkma = urlsplit(resource.get("url", "")).hostname == "api.hkma.gov.hk"
    has_typed_fields = False
    spatial_binding = accepted_binding(resource, schema) if schema else None
    for receipt in receipts:
        if not receipt.get("schema_json") or not receipt.get("schema_hash"):
            continue
        observed = unpack(receipt["schema_json"])
        revalidate = (
            hkma and observed.get("hkmaPaginationContract") != HKMA_PAGING_CONTRACT
        )
        eligible = receipt.get("status") == "queryable" and not revalidate
        bindings = typed_bindings(observed)
        typed_count = sum(
            set(field.get("types", [])) - {"null"} == {"number"}
            or name in observed.get("nativeTemporalFields", {})
            or name in bindings
            for name, field in field_catalogue(observed).items()
        )
        has_typed_fields = has_typed_fields or bool(typed_count and eligible)
        scoped_binding = accepted_binding(resource, observed)
        if spatial_binding is None and scoped_binding and eligible:
            spatial_binding = scoped_binding
        accepted.append(
            {
                "receiptKey": None,  # Internal cache hashes can encode caller parameters.
                "representation": observed.get("format"),
                "readScope": observed.get("scope"),
                "datasetCompleteness": observed.get("datasetCompleteness"),
                "unreadMemberCount": len(observed.get("unreadMembers", [])),
                "schemaFingerprint": receipt["schema_hash"],
                "selection": public_selection(observed),
                "status": receipt.get("status"),
                "lastCheckedAt": receipt.get("checked"),
                "lastValidatedAt": receipt.get("validated"),
                "retrievedAt": receipt.get("retrieved"),
                "readerRevision": observed.get("readerRevision")
                or observed.get("readerContract"),
                "sourceContract": observed.get("sourceContract"),
                "sourceResponseComplete": observed.get("sourceResponseComplete"),
                "semanticBinding": scoped_binding,
                "typedComparisonFieldCount": typed_count,
                **({"requiresRevalidation": revalidate} if hkma else {}),
            }
        )
    if access == "map_imagery":
        state, reason = "unsupported", "map_imagery_is_not_a_record_collection"
    elif status in {
        "restricted",
        "unavailable",
        "schema_drift",
        "stale",
        "capacity_limited",
    }:
        state, reason = "held", check.get("reason") or status
    elif status == "needs_selection":
        state, reason = "requires_selection", check.get("reason") or status
    elif (
        hkma
        and status == "queryable"
        and not any(
            r["status"] == "queryable" and not r.get("requiresRevalidation")
            for r in accepted
        )
    ):
        state, reason = "held", "hkma_pagination_revalidation_required"
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
        state, reason = "held", check.get("reason") or (
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
    if has_typed_fields:
        operations["typed_comparison"] = operation(state, reason)
    if spatial_binding:
        operations["nearby"] = operation(
            state if spatial_binding.get("state") == "available" else "held",
            spatial_binding.get("reason") or "accepted_reviewed_point_binding",
        )
    fields = []
    if schema is not None:
        for field in schema.get("fields", []) + schema.get("queryFields", []):
            if field.get("name") in {f["name"] for f in fields}:
                continue
            operators = ["eq"]
            types = set(field.get("types", [])) - {"null"}
            if "string" in types:
                operators.append("contains")
            if (
                types == {"number"}
                or field["name"] in schema.get("nativeTemporalFields", {})
                or field["name"] in typed_bindings(schema)
            ):
                operators += ["lt", "lte", "gt", "gte", "between", "order"]
                operations["typed_comparison"] = operation(state, reason)
            fields.append({**field, "operators": operators})
    return {
        "revision": REVISION,
        "resourceId": resource["id"],
        "datasetId": resource["datasetId"],
        "representation": resource.get("format"),
        "readerFamily": access,
        "readerSupport": (
            "accepted_selections_only"
            if any(not r.get("requiresRevalidation") for r in accepted)
            else "unverified"
        ),
        "operations": operations,
        "acceptedSelections": accepted,
        "fields": fields,
        "semanticBinding": spatial_binding,
        "entityKind": (profile_for(resource) or {}).get("entityKind"),
        "access": {
            "status": status,
            "reason": check.get("reason"),
            "lastCheckedAt": check.get("checked"),
        },
        "observationTime": None,
        "completeness": (
            "per_receipt_selection_only"
            if any(not r.get("requiresRevalidation") for r in accepted)
            else "unknown"
        ),
        "nextAction": {
            "tool": "hk_resource_schema",
            "arguments": {"resourceId": resource["id"]},
        },
    }


def summary(counts, dataset_id=None):
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
        "entityKind": dataset_kind(dataset_id),
    }
