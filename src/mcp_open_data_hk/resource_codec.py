"""Additive exact scalar wire codec shared by HTTP, MCP and browser evidence."""

import json
import math
import re

from .contracts import DomainError
from .resource_fields import MISSING, selected

KINDS = {"integer", "float", "string", "boolean", "null"}
MAX_RESPONSE_BYTES = 1_536_000


def scalar_kind(value):
    if value is MISSING:
        return "missing"
    if type(value) is int:
        return "integer"
    if type(value) is float:
        return "float"
    if type(value) is bool:
        return "boolean"
    if value is None:
        return "null"
    return "string" if isinstance(value, str) else "json"


def typed_filters(predicates, legacy=None):
    if (
        not isinstance(predicates, list)
        or len(predicates) > 10
        or legacy
        and predicates
    ):
        raise DomainError(
            "INVALID_FILTER",
            "Use at most ten typed filters, without legacy filters",
            400,
        )
    result = {}
    for predicate in predicates:
        if not isinstance(predicate, dict) or set(predicate) != {
            "field",
            "kind",
            "value",
        }:
            raise DomainError(
                "INVALID_FILTER",
                "Typed equality requires field, kind and textual value",
                400,
            )
        field, kind, text = (predicate[k] for k in ("field", "kind", "value"))
        if (
            not isinstance(field, str)
            or not 1 <= len(field) <= 300
            or field in result
            or kind not in KINDS
            or not isinstance(text, str)
            or len(text) > 1000
        ):
            raise DomainError(
                "INVALID_FILTER", "Invalid or duplicate typed equality field", 400
            )
        try:
            if kind == "integer":
                if not re.fullmatch(r"-?(?:0|[1-9][0-9]{0,199})", text):
                    raise ValueError()
                value = int(text)
            elif kind == "float":
                if len(text) > 200 or not re.fullmatch(
                    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?", text
                ):
                    raise ValueError()
                value = float(text)
                if not math.isfinite(value):
                    raise ValueError()
            elif kind == "boolean":
                if text not in {"true", "false"}:
                    raise ValueError()
                value = text == "true"
            elif kind == "null":
                if text != "null":
                    raise ValueError()
                value = None
            else:
                value = text
        except (ValueError, OverflowError):
            raise DomainError(
                "INVALID_FILTER", "Invalid finite scalar value for " + kind, 400
            ) from None
        result[field] = value
    return result if predicates else legacy or {}


def presentation(items, fields):
    columns = fields or list(dict.fromkeys(k for row in items for k in row))
    rows = []
    for row in items:
        cells = []
        for name in columns:
            value = selected(row, name)
            kind = scalar_kind(value)
            raw = (
                None
                if value is MISSING
                else json.dumps(
                    value, ensure_ascii=False, allow_nan=False, separators=(",", ":")
                )
            )
            cells.append(
                {"kind": kind, "text": value if kind == "string" else raw, "json": raw}
            )
        rows.append(cells)
    return {
        "codec": 1,
        "columns": columns,
        "rows": rows,
        "recordsJson": json.dumps(
            items, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        ),
        "precision": "Exact parsed source values. Cannot restore precision already lost by a source reader.",
    }
