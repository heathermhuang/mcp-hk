"""Bounded typed selector options: metadata evidence, never read acceptance."""

MAX_BYTES = 1_000_000
SELECTION_ERRORS = frozenset(
    {
        "SHEET_REQUIRED",
        "LAYER_REQUIRED",
        "INVALID_SHEET",
        "INVALID_RECORD_PATH",
        "TYPE_NAME_REQUIRED",
        "PARAMETERS_REQUIRED",
        "RECORD_PATH_REQUIRED",
        "INVALID_QUERY",
    }
)


def describe(resource_id, result):
    schema = result.get("schema", result)
    groups = []
    for kind, source, field in (
        ("sheet", schema.get("availableSheets") or result.get("sheets"), "sheet"),
        ("layer", result.get("layers"), "layer"),
        ("feature_type", result.get("featureTypes"), "recordPath"),
        ("record_path", schema.get("availableRecordPaths"), "recordPath"),
    ):
        if source is None:
            continue
        options = []
        for raw in source[:100]:
            value = raw.get("id") if isinstance(raw, dict) else raw
            valid = (
                type(value) is int and 0 <= value <= 10000
                if field == "layer"
                else isinstance(value, str)
                and len(value) <= (100 if field == "sheet" else 300)
            )
            if not valid:
                continue
            options.append(
                {
                    "value": value,
                    "label": (
                        raw.get("name", str(value)) if isinstance(raw, dict) else value
                    ),
                    "state": "unverified",
                    "nextAction": {
                        "tool": "hk_resource_schema",
                        "arguments": {"resourceId": resource_id, field: value},
                    },
                }
            )
        count = result.get("sheetCount") if kind == "sheet" else None
        count = count if count is not None else len(source)
        groups.append(
            {
                "kind": kind,
                "argument": field,
                "options": options,
                "totalOptions": count,
                "truncated": len(options) < count,
                "scope": "discovered_options_not_accepted_record_reads",
            }
        )
    return groups
