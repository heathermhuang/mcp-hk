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


def add_nested(stats, row):
    for name, value in nested_values(row):
        entry = stats.setdefault(name, {"types": set(), "present": 0})
        entry["types"].add(value_type(value))
        entry["present"] += value is not None
    if len(stats) > 1000:
        raise DomainError(
            "SOURCE_TOO_COMPLEX", "Nested selector field budget exceeded", 422
        )


def nested_schema(stats, count):
    return [
        {
            "name": k,
            "types": sorted(v["types"] | ({"null"} if v["present"] < count else set())),
            "missingCount": count - v["present"],
            "unit": None,
        }
        for k, v in sorted(stats.items())
    ]


def inspect_nested(rows):
    stats = {}
    count = 0
    for row in rows:
        count += 1
        add_nested(stats, row)
    return nested_schema(stats, count)
