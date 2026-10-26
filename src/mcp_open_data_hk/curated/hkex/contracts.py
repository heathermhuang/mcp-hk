"""Strict normalized intake contract; provider formats are qualified separately.

Extra fields fail closed so personal contacts, signatures and arbitrary source
documents cannot enter public facts.
"""

import hashlib
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODES = (
    "collect",
    "normalize",
    "retain",
    "raw",
    "history",
    "backup",
    "rest",
    "mcp",
    "browser",
    "links",
    "export",
    "schedule",
)
FORMS = ("1", "2", "3A", "3B", "3C", "3D")
NOTICE = (
    "Disclosure notices are dated source statements, not executed trades or "
    "a current aggregate beneficial-ownership register. Deemed interests may overlap."
)


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def canonical(value):
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def exact(value, prefix=""):
    if not isinstance(value, str) or not re.fullmatch(
        re.escape(prefix) + r"[A-Za-z0-9_-]{1,80}", value
    ):
        raise ValueError("INVALID_EXACT_ID")
    return value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDate(Strict):
    value: date | None = None
    precision: Literal["day", "unknown"] = "unknown"
    timezone: Literal["Asia/Hong_Kong", "unspecified"] = "unspecified"

    @model_validator(mode="after")
    def coherent(self):
        if (self.value is None) != (self.precision == "unknown"):
            raise ValueError("DATE_PRECISION_MISMATCH")
        return self


class Security(Strict):
    source_id: str = Field(min_length=1, max_length=80)
    stock_code: str | None = Field(None, pattern=r"^[0-9]{5}$")
    share_class: str | None = Field(None, min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=300)
    name_date: SourceDate = SourceDate()
    issued_shares: str | None = None

    @field_validator("issued_shares")
    @classmethod
    def quantity(cls, v):
        return Interest.numeric(v)

    @field_validator("source_id")
    @classmethod
    def identifier(cls, v):
        return exact(v)


class Interest(Strict):
    line: str = Field(min_length=1, max_length=80)
    section: str = Field(min_length=1, max_length=80)
    security_id: str
    capacity_code: str | None = Field(None, min_length=1, max_length=40)
    nature: Literal["direct", "deemed", "indirect", "unknown"]
    position: Literal["long", "short", "lending_pool", "unknown"]
    phase: Literal["before", "after", "declared", "unknown"]
    instrument: Literal["issuer_shares", "associated_shares", "debenture"]
    shares: str | None = None
    percentage: str | None = None
    unit: str = Field(min_length=1, max_length=80)
    party_ref: str | None = Field(None, max_length=80)

    @field_validator("security_id")
    @classmethod
    def identifier(cls, v):
        return exact(v)

    @field_validator("shares", "percentage")
    @classmethod
    def numeric(cls, v):
        if v is not None:
            if not re.fullmatch(r"[0-9]{1,40}(?:\.[0-9]{1,30})?", v):
                raise ValueError("LOSSLESS_DECIMAL_REQUIRED")
            if not Decimal(v).is_finite():
                raise ValueError("NONFINITE_DECIMAL")
        return v


class Price(Strict):
    kind: Literal["highest", "average", "average_consideration"]
    value: str
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    unit: Literal["per_share"] = "per_share"

    @field_validator("value")
    @classmethod
    def numeric(cls, v):
        return Interest.numeric(v)


class Particular(Strict):
    line: str = Field(min_length=1, max_length=80)
    reason_code: str = Field(min_length=1, max_length=40)
    shares: str | None = None
    price: str | None = None
    currency: str | None = Field(None, pattern=r"^[A-Z]{3}$")
    unit: str = Field(min_length=1, max_length=80)
    security_id: str | None = None
    capacity_before: str | None = Field(None, min_length=1, max_length=40)
    capacity_after: str | None = Field(None, min_length=1, max_length=40)
    prices: tuple[Price, ...] = Field(default=(), max_length=3)
    position: Literal["long", "short", "unknown"] = "unknown"

    @model_validator(mode="after")
    def distinct_prices(self):
        if len({p.kind for p in self.prices}) != len(self.prices):
            raise ValueError("DUPLICATE_PRICE_KIND")
        return self

    @field_validator("shares", "price")
    @classmethod
    def numeric(cls, v):
        return Interest.numeric(v)


class Party(Strict):
    ref: str = Field(min_length=1, max_length=80)
    disclosed_name: str = Field(min_length=1, max_length=300)
    source_global_id: str | None = Field(None, max_length=80)
    association: str | None = Field(None, max_length=200)


class Control(Strict):
    line: str = Field(min_length=1, max_length=80)
    controlled_party_ref: str
    controlling_party_ref: str
    percentage_control: str | None = None
    direct_interest: Literal["yes", "no", "unknown"] = "unknown"

    @field_validator("percentage_control")
    @classmethod
    def percentage(cls, v):
        value = Interest.numeric(v)
        if value is not None and Decimal(value) > 100:
            raise ValueError("CONTROL_PERCENTAGE_RANGE")
        return value


class Filing(Strict):
    serial: str
    issuer_id: str
    issuer_name: str = Field(min_length=1, max_length=300)
    channel: Literal["dion", "pre_dion"]
    form: Literal["1", "2", "3A", "3B", "3C", "3D"]
    subject: str = Field(min_length=1, max_length=300)
    subject_name_zh_hant: str | None = Field(None, max_length=300)
    event_date: SourceDate = SourceDate()
    aware_date: SourceDate = SourceDate()
    filed_date: SourceDate = SourceDate()
    published_date: SourceDate = SourceDate()
    withdrawn_date: SourceDate = SourceDate()
    state: Literal["original", "amendment", "superseded", "withdrawn"]
    replaces: str | None = None
    superseded_by: str | None = None
    securities: tuple[Security, ...] = Field(min_length=1, max_length=30)
    interests: tuple[Interest, ...] = Field(max_length=500)
    particulars: tuple[Particular, ...] = Field(default=(), max_length=500)
    parties: tuple[Party, ...] = Field(default=(), max_length=500)
    controls: tuple[Control, ...] = Field(default=(), max_length=500)

    @field_validator("serial", "issuer_id", "replaces", "superseded_by")
    @classmethod
    def identifier(cls, v):
        return exact(v) if v is not None else v

    @model_validator(mode="after")
    def relations(self):
        if self.serial in {self.replaces, self.superseded_by}:
            raise ValueError("SELF_REPLACING_FILING")
        if (self.state == "amendment" and not self.replaces) or (
            self.state == "superseded" and not self.superseded_by
        ):
            raise ValueError("MISSING_REVISION_RELATION")
        if self.withdrawn_date.value and self.state != "withdrawn":
            raise ValueError("WITHDRAWAL_STATE_MISMATCH")
        if self.filed_date.value:
            if self.channel == "dion" and self.filed_date.value < date(2017, 7, 3):
                raise ValueError("DION_DATE_RANGE_MISMATCH")
            if self.channel == "pre_dion" and not date(
                2003, 4, 1
            ) <= self.filed_date.value <= date(2017, 10, 2):
                raise ValueError("PRE_DION_DATE_RANGE_MISMATCH")
        ids = [s.source_id for s in self.securities]
        refs = [p.ref for p in self.parties]
        if len(set(ids)) != len(ids) or len(set(refs)) != len(refs):
            raise ValueError("DUPLICATE_SCOPED_ID")
        for values, key in (
            (self.interests, lambda x: (x.section, x.line)),
            (self.particulars, lambda x: x.line),
            (self.controls, lambda x: x.line),
        ):
            if len({key(x) for x in values}) != len(values):
                raise ValueError("DUPLICATE_SOURCE_LINE")
        for line in self.interests:
            if line.security_id not in ids or (
                line.party_ref and line.party_ref not in refs
            ):
                raise ValueError("UNRESOLVED_SCOPED_REFERENCE")
        for line in self.particulars:
            if line.security_id is not None and line.security_id not in ids:
                raise ValueError("UNRESOLVED_SCOPED_REFERENCE")
        for relation in self.controls:
            if (
                relation.controlled_party_ref not in refs
                or relation.controlling_party_ref not in refs
                or relation.controlled_party_ref == relation.controlling_party_ref
            ):
                raise ValueError("UNRESOLVED_CONTROL_REFERENCE")
        return self


class Window(Strict):
    issuer_id: str
    start: date
    end: date  # exclusive, local calendar dates
    basis: Literal["filed", "published", "event"]
    timezone: Literal["Asia/Hong_Kong"] = "Asia/Hong_Kong"
    channel: Literal["dion", "pre_dion"] = "dion"

    @field_validator("issuer_id")
    @classmethod
    def identifier(cls, v):
        return exact(v)

    @model_validator(mode="after")
    def bounded(self):
        if not 1 <= (self.end - self.start).days <= 31:
            raise ValueError("WINDOW_MUST_BE_1_TO_31_CALENDAR_DAYS")
        return self


class Policy(Strict):
    source: Literal["hkex_di"] = "hkex_di"
    reference: str = Field(min_length=1, max_length=200)
    evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    purpose: Literal["disclosure_chronology"] = "disclosure_chronology"
    qualified_at: datetime
    expires_at: datetime
    revoked: bool = False
    modes: dict[str, Literal["unknown", "denied", "allowed"]]
    allowed_fields: tuple[str, ...]
    # Intake routes are configured by audited operators, never by query parameters.
    routes: dict[Literal["listing", "detail", "inventory"], str]
    forms: tuple[Literal["1", "2", "3A", "3B", "3C", "3D"], ...]
    codes: dict[str, dict[str, str]]
    retention_seconds: int = Field(ge=1, le=366 * 86400)
    cursor_seconds: int = Field(ge=1, le=48 * 3600)
    reads_run: int = Field(default=40, ge=1, le=40)
    reads_day: int = Field(default=100, ge=1, le=100)
    bytes_run: int = Field(default=16 * 1024 * 1024, ge=1, le=16 * 1024 * 1024)
    bytes_day: int = Field(default=32 * 1024 * 1024, ge=1, le=32 * 1024 * 1024)
    min_interval_seconds: int = Field(ge=1, le=86400)
    inventory_basis: Literal["filed", "published", "event", "unknown"]
    inventory_method: str = Field(min_length=1, max_length=500)
    recheck_rule: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def bound(self):
        if set(self.modes) != set(MODES):
            raise ValueError("EXPLICIT_MODE_MATRIX_REQUIRED")
        if (
            any(t.tzinfo is None for t in (self.qualified_at, self.expires_at))
            or self.qualified_at >= self.expires_at
        ):
            raise ValueError("POLICY_DATES_INVALID")
        if self.cursor_seconds > self.retention_seconds:
            raise ValueError("CURSOR_EXCEEDS_RETENTION")
        if not set(self.allowed_fields) <= set(Filing.model_fields):
            raise ValueError("FIELD_OUTSIDE_NORMALIZED_CONTRACT")
        for route in self.routes.values():
            u = urlsplit(route)
            if (
                u.scheme != "https"
                or u.hostname not in {"di.hkex.com.hk", "www2.hkexnews.hk"}
                or u.port not in {None, 443}
                or u.username
                or u.password
                or u.query
                or u.fragment
                or not u.path.startswith("/")
            ):
                raise ValueError("UNQUALIFIED_ROUTE")
        return self

    def require(self, *modes, now=None):
        now = now or datetime.now(timezone.utc)
        if (
            self.revoked
            or not self.qualified_at <= now < self.expires_at
            or any(self.modes.get(m) != "allowed" for m in modes)
        ):
            raise ValueError("HKEX_SOURCE_UNQUALIFIED")


def parse_filing(raw, policy):
    policy.require("normalize", "retain")
    row = Filing.model_validate(raw)
    if set(raw) - set(policy.allowed_fields) or row.form not in policy.forms:
        raise ValueError("UNQUALIFIED_FIELDS_OR_FORM")
    for line in row.interests:
        if (
            line.capacity_code is not None
            and line.capacity_code not in policy.codes.get("capacity", {})
        ):
            raise ValueError("UNKNOWN_CAPACITY_CODE")
    for line in row.particulars:
        if line.reason_code not in policy.codes.get("reason", {}):
            raise ValueError("UNKNOWN_REASON_CODE")
        for code in (line.capacity_before, line.capacity_after):
            if code is not None and code not in policy.codes.get("capacity", {}):
                raise ValueError("UNKNOWN_CAPACITY_CODE")
    return row


def revision_closure(filings):
    """Validate reciprocal assertions without inventing missing notices."""
    by_id = {x.serial: x for x in filings}
    if len(by_id) != len(filings):
        raise ValueError("DUPLICATE_SERIAL_IN_VERSION")
    edges, missing = {}, set()
    for row in filings:
        for old, new in ((row.replaces, row.serial), (row.serial, row.superseded_by)):
            if old and new:
                edges.setdefault(old, set()).add(new)
                for serial in (old, new):
                    if serial not in by_id:
                        missing.add(serial)
                if old in by_id and new in by_id:
                    a, b = by_id[old], by_id[new]
                    if a.issuer_id != b.issuer_id or a.channel != b.channel:
                        raise ValueError("CROSS_IDENTITY_REVISION")
                    if a.superseded_by not in (None, new) or b.replaces not in (
                        None,
                        old,
                    ):
                        raise ValueError("CONTRADICTORY_REVISION")
    if any(len(values) != 1 for values in edges.values()):
        raise ValueError("BRANCHING_SUPERSESSION")
    if len({new for values in edges.values() for new in values}) != len(edges):
        raise ValueError("MULTIPLE_REVISION_PREDECESSORS")
    for start in edges:
        seen, current = set(), start
        while current in edges:
            if current in seen:
                raise ValueError("REVISION_CYCLE")
            seen.add(current)
            current = next(iter(edges[current]))
    return {
        "missing": sorted(missing),
        "edges": sorted((a, next(iter(b))) for a, b in edges.items()),
    }


def unavailable_status():
    return {
        "source": "hkex_di",
        "state": "source_unqualified",
        "acceptedVersion": None,
        "modes": {m: "unknown" for m in MODES},
        "coverage": None,
        "notice": NOTICE,
        "code": "HKEX_SOURCE_UNQUALIFIED",
    }


class CaptureMeta(Strict):
    id: str = Field(pattern=r"^[a-f0-9]{64}$")
    run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    policy_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: datetime
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    transform_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class Revision(Strict):
    older: str
    newer: str
    resolved: bool


class ServedFiling(Filing):
    filing_id: str
    issuer_source_id: str
    revision_links: tuple[Revision, ...]
    currently_effective_notice: bool
    interpretation: str
    capture: CaptureMeta


class ServedSecurity(Strict):
    id: str
    stock_code: str = Field(pattern=r"^[0-9]{5}$")
    share_class: str
    name: str
    name_date: SourceDate


class ServedIssuer(Strict):
    id: str
    issuer_id: str
    name: str
    securities: tuple[ServedSecurity, ...]
