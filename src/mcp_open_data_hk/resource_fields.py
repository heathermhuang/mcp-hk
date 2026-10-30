"""Explicit selectors for nested source fields; preserve original records."""

from .contracts import DomainError

MISSING = object()


def selected(row, field):
    if field in row:
        return row[field]
    value = row
    for part in field.split("."):
        if not isinstance(value, dict) or part not in value:
            return MISSING
        value = value[part]
    return value


def nested_values(row, prefix="", depth=0):
    if depth >= 4:
        return
    for key, value in row.items():
        name = prefix + "." + key if prefix else key
        if prefix:
            yield name, value
        if isinstance(value, dict):
            yield from nested_values(value, name, depth + 1)


def value_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "string"


SCALAR_KINDS = {
    int: "integer",
    float: "float",
    bool: "boolean",
    str: "string",
    type(None): "null",
    dict: "object",
    list: "array",
}


def scalar_kind(value):
    return SCALAR_KINDS.get(type(value), "string")


def add_nested(stats, row):
    for name, value in nested_values(row):
        entry = stats.setdefault(
            name, {"types": set(), "kinds": set(), "present": 0, "seen": 0}
        )
        kind = scalar_kind(value)
        entry["types"].add("number" if kind in {"integer", "float"} else kind)
        entry["kinds"].add(kind)
        entry["present"] += value is not None
        entry["seen"] += 1
    if len(stats) > 1000:
        raise DomainError(
            "SOURCE_TOO_COMPLEX", "Nested selector field budget exceeded", 422
        )


def nested_schema(stats, count):
    return [
        {
            "name": k,
            "types": sorted(v["types"] | ({"null"} if v["present"] < count else set())),
            "scalarKinds": sorted(v["kinds"] - {"object", "array"}),
            "missingCount": count - v["present"],
            "absentCount": count - v["seen"],
            "nullCount": v["seen"] - v["present"],
            "unit": None,
        }
        for k, v in sorted(stats.items())
    ]


def inspect_nested(rows, check_budget=None):
    stats = {}
    count = 0
    for row in rows:
        if check_budget and count % 256 == 0:
            check_budget()
        count += 1
        add_nested(stats, row)
    return nested_schema(stats, count)
