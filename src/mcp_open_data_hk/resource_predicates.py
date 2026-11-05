"""Allowlisted comparisons on native numbers or reader-declared temporal values.

No CSV casting, guessed dates/units, expression parser or arbitrary source query.
"""

import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from .contracts import DomainError
from .resource_fields import MISSING, selected, field_catalogue
from .source_contracts import typed_bindings

OPS = {"lt", "lte", "gt", "gte", "between"}
KINDS = {"number", "date", "datetime"}


def invalid(message):
    raise DomainError("INVALID_PREDICATE", message, 400)


def convert(value, kind):
    if kind == "number":
        if type(value) not in {int, float, str} or isinstance(value, bool):
            raise ValueError("not a number")
        if isinstance(value, str) and (
            len(value) > 100
            or not re.fullmatch(
                r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d{1,3})?", value
            )
        ):
            raise ValueError("invalid decimal")
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError("nonfinite number")
        return number
    if not isinstance(value, str):
        raise ValueError("not temporal text")
    if kind == "date":
        result = date.fromisoformat(value)
        if result.isoformat() != value:
            raise ValueError("use YYYY-MM-DD")
        return result
    if kind == "datetime":
        if not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})",
            value,
        ):
            raise ValueError("use timezone-aware ISO datetime")
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(timezone.utc)
    raise ValueError("unknown kind")


class Predicates:
    def __init__(self, predicates, ordering, schema, names, offset, limit):
        if (
            not isinstance(predicates, list)
            or len(predicates) > 10
            or not isinstance(ordering, list)
            or len(ordering) > 3
        ):
            invalid("At most ten comparisons and three order fields are allowed")
        if ordering and offset + limit > 1000:
            invalid("Ordered pages are bounded to the first 1000 matching records")
        fields = field_catalogue(schema)
        temporal = {
            **schema.get("nativeTemporalFields", {}),
            **{
                name: binding["kind"]
                for name, binding in typed_bindings(schema).items()
                if binding.get("conversion") == "iso8601_timezone_required"
            },
        }
        self.predicates, self.ordering = [], []
        self.excluded = {"missing": 0, "null": 0, "invalid": 0}
        for item, is_order in [(p, False) for p in predicates] + [
            (p, True) for p in ordering
        ]:
            allowed = (
                {"field", "kind", "direction"}
                if is_order
                else {"field", "kind", "op", "value", "upper"}
            )
            if not isinstance(item, dict) or set(item) - allowed:
                invalid("Unknown comparison or ordering member")
            field, kind = item.get("field"), item.get("kind")
            if not isinstance(field, str) or field not in names:
                raise DomainError(
                    "UNKNOWN_FIELD", "Inspect schema for exact source fields", 400
                )
            if kind not in KINDS | ({"string"} if is_order else set()):
                invalid("Unsupported comparison kind")
            types = set(fields.get(field, {}).get("types", [])) - {"null"}
            if kind == "number" and types != {"number"}:
                invalid(
                    "Numeric comparisons require native numeric fields; string conversion needs a reviewed binding"
                )
            if kind in {"date", "datetime"} and (
                temporal.get(field) != kind or not types <= {"string"}
            ):
                invalid(
                    "Temporal comparisons require a reader-declared native date/datetime field"
                )
            if kind == "string" and types != {"string"}:
                invalid("String ordering requires source strings")
            if is_order:
                direction = item.get("direction", "asc")
                if direction not in {"asc", "desc"}:
                    invalid("Ordering direction must be asc or desc")
                self.ordering.append((field, kind, direction))
            else:
                op = item.get("op")
                if op not in OPS or ("upper" in item) != (op == "between"):
                    invalid(
                        "Use lt/lte/gt/gte or between with an exclusive upper bound"
                    )
                try:
                    lower = convert(item.get("value"), kind)
                    upper = convert(item["upper"], kind) if op == "between" else None
                    if upper is not None and upper <= lower:
                        invalid("Interval must have start < end")
                except (ValueError, TypeError, InvalidOperation, OverflowError):
                    invalid("Invalid typed comparison value")
                self.predicates.append((field, kind, op, lower, upper))

    def matches(self, row):
        for field, kind, op, lower, upper in self.predicates:
            value = selected(row, field)
            if value is MISSING or value is None:
                self.excluded["missing" if value is MISSING else "null"] += 1
                return False
            try:
                if kind == "number" and type(value) not in {int, float}:
                    raise ValueError("not native numeric")
                actual = convert(value, kind)
            except (ValueError, TypeError, InvalidOperation, OverflowError):
                self.excluded["invalid"] += 1
                return False
            if not {
                "lt": lambda: actual < lower,
                "lte": lambda: actual <= lower,
                "gt": lambda: actual > lower,
                "gte": lambda: actual >= lower,
                "between": lambda: lower <= actual < upper,
            }[op]():
                return False
        return True

    def key(self, row, index):
        values = []
        for field, kind, direction in self.ordering:
            value = selected(row, field)
            missing = value is MISSING or value is None
            try:
                if missing:
                    value = None
                elif kind == "string":
                    if not isinstance(value, str) or len(value.encode()) > 1000:
                        invalid("Ordered strings must be at most 1000 UTF-8 bytes")
                else:
                    if kind == "number" and type(value) not in {int, float}:
                        raise ValueError("not native numeric")
                    value = convert(value, kind)
            except (ValueError, TypeError, InvalidOperation, OverflowError):
                missing, value = True, None
            values.append((missing, value, direction))
        return SortKey(values, index)


class SortKey:
    """Null/invalid values last in either direction; source ordinal breaks ties."""

    __slots__ = ("values", "index")

    def __init__(self, values, index):
        self.values, self.index = values, index

    def __lt__(self, other):
        for (missing, a, direction), (other_missing, b, _) in zip(
            self.values, other.values
        ):
            if missing != other_missing:
                return not missing
            if not missing and a != b:
                return a < b if direction == "asc" else a > b
        return self.index < other.index
