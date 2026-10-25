"""Strict, purpose-limited normalised contract; not a live register parser."""

import hashlib
import json
import re
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

REGISTER_URL = "https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing/Register-of-licensed-persons-and-registered-institutions"
LEGAL_URL = (
    REGISTER_URL + "/Public-register-of-licensed-persons-and-registered-institutions"
)
MODES = (
    "automation",
    "cache",
    "retention",
    "backup",
    "rest",
    "mcp",
    "browser",
    "search",
    "history",
    "export",
    "raw",
)


class Rejected(ValueError):
    """Codes only: never include source bytes, private terms or credentials."""


def ce_reference(value):
    # ASCII case conversion only. NFKC must not turn a lookalike into identity.
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{3}[0-9]{3}", value):
        raise Rejected("SFC_INVALID_CE")
    return value.upper()


def encoded(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDate(Strict):
    raw: str | None = Field(None, max_length=100)
    value: str | None = Field(None, max_length=10)
    precision: Literal["day", "month", "year", "unknown"] = "unknown"

    @model_validator(mode="after")
    def exact_precision(self):
        if self.precision == "unknown":
            if self.value is not None:
                raise ValueError("Unknown source date has no parsed value")
            return self
        pattern = {
            "day": r"\d{4}-\d{2}-\d{2}",
            "month": r"\d{4}-\d{2}",
            "year": r"\d{4}",
        }[self.precision]
        if self.raw != self.value or not re.fullmatch(
            pattern, self.value or "", re.ASCII
        ):
            raise ValueError(
                "Normalised date must retain the exact source value and precision"
            )
        date.fromisoformat(
            self.value + {"day": "", "month": "-01", "year": "-01-01"}[self.precision]
        )
        return self


class Activity(Strict):
    code: str = Field(pattern=r"^[0-9]{1,2}$")
    label: str = Field(min_length=1, max_length=500)
    statusCode: str = Field(min_length=1, max_length=100)
    statusLabel: str = Field(min_length=1, max_length=500)
    start: SourceDate = Field(default_factory=SourceDate)
    end: SourceDate = Field(default_factory=SourceDate)
    conditions: tuple[str, ...] = Field(default=(), max_length=30)


class Corporation(Strict):
    ce: str
    entityType: Literal["corporation"]
    regime: Literal["SFO"]
    licenceType: Literal["licensed_corporation"]
    nameEn: str | None = Field(None, min_length=1, max_length=500)
    nameZhHant: str | None = Field(None, min_length=1, max_length=500)
    statusCode: str = Field(min_length=1, max_length=100)
    statusLabel: str = Field(min_length=1, max_length=500)
    activities: tuple[Activity, ...] = Field(max_length=50)
    observedAt: datetime
    sourceCutoff: SourceDate = Field(default_factory=SourceDate)
    sourceTimezone: Literal["Asia/Hong_Kong"] = "Asia/Hong_Kong"

    @field_validator("ce")
    @classmethod
    def identity(cls, value):
        return ce_reference(value)

    @field_validator("observedAt")
    @classmethod
    def timezone_known(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Observation requires a timezone")
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def complete(self):
        if not self.nameEn and not self.nameZhHant:
            raise ValueError("A corporate source name is required")
        # Multiple intervals per activity are permitted; exact duplicates are drift.
        keys = [encoded(activity) for activity in self.activities]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate activity interval")
        if any(len(c) > 2000 for a in self.activities for c in a.conditions):
            raise ValueError("Condition exceeds its bound")
        return self

    @property
    def subject_id(self):
        return "sfc:ce:" + self.ce


# Full contract field paths. A narrower grant requires a separately reviewed
# transform, rather than silently claiming omitted fields were qualified.
CORPORATE_FIELDS = tuple(
    sorted(
        list(Corporation.model_fields)
        + ["activities." + field for field in Activity.model_fields]
    )
)


def parse_normalized(payload, expected_ce):
    """Offline, explicitly normalised JSON only. No HTML/API shape is guessed."""
    if not isinstance(payload, bytes) or len(payload) > 256 * 1024:
        raise Rejected("SFC_PAYLOAD_LIMIT")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    try:
        record = Corporation.model_validate(
            json.loads(payload, object_pairs_hook=unique)
        )
        if record.ce != ce_reference(expected_ce):
            raise ValueError("Corporate identity mismatch")
        return record
    except (ValueError, TypeError, RecursionError) as exc:
        raise Rejected("SFC_SCHEMA_CHANGED") from exc
