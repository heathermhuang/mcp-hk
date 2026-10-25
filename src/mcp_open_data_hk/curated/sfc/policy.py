"""Pinned operator policy; request parameters and environment flags grant nothing."""

from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from .contracts import (
    MODES,
    CORPORATE_FIELDS,
    Strict,
    Rejected,
    ce_reference,
    digest,
    encoded,
)


class Policy(Strict):
    source: Literal["sfc_register"] = "sfc_register"
    purpose: Literal["intended_dealing_corporate_verification", "connector_development"]
    route: str = Field(max_length=500)
    evidenceRef: str = Field(min_length=1, max_length=200)
    evidenceSha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    qualifiedAt: datetime
    recheckAt: datetime
    modes: dict[str, Literal["unknown", "denied", "allowed"]]
    allowedFields: tuple[str, ...] = ()
    trackedCorporateReferences: tuple[str, ...] = Field(default=(), max_length=25)
    cacheSeconds: int = Field(0, ge=0, le=86400)
    retentionSeconds: int = Field(0, ge=0)
    backupSeconds: int = Field(0, ge=0)
    readsPerRun: int = Field(25, ge=1, le=25)
    readsPerDay: int = Field(100, ge=1, le=100)
    bytesPerRun: int = Field(8388608, ge=1, le=8388608)
    bytesPerDay: int = Field(16777216, ge=1, le=16777216)

    @model_validator(mode="after")
    def reviewed_contract(self):
        if len(set(self.allowedFields)) != len(self.allowedFields) or not set(
            self.allowedFields
        ) <= set(CORPORATE_FIELDS):
            raise ValueError("Unsupported or duplicate allowed field")
        cohort = tuple(ce_reference(ce) for ce in self.trackedCorporateReferences)
        if cohort != self.trackedCorporateReferences or len(set(cohort)) != len(cohort):
            raise ValueError(
                "Tracked cohort must use unique canonical corporate CE references"
            )
        if self.modes.get("automation") == "allowed" and not cohort:
            raise ValueError("Automation requires the exact qualified tracked cohort")
        if self.modes.get("retention") == "allowed" and set(self.allowedFields) != set(
            CORPORATE_FIELDS
        ):
            raise ValueError(
                "This transform requires explicit permission for every contract field"
            )
        if self.purpose == "connector_development" and any(
            self.modes.get(mode) == "allowed"
            for mode in ("rest", "mcp", "browser", "search", "history", "export")
        ):
            raise ValueError(
                "Development configuration cannot enable public outputs or history"
            )
        if set(self.modes) != set(MODES):
            raise ValueError("Each mode requires an independent decision")
        url = urlsplit(self.route)
        if self.route and (
            url.scheme != "https"
            or url.netloc != "apps.sfc.hk"
            or url.query
            or url.fragment
            or not url.path.startswith("/publicregWeb/")
        ):
            raise ValueError("Unqualified SFC route")
        if (
            any(
                t.tzinfo is None or t.utcoffset() is None
                for t in (self.qualifiedAt, self.recheckAt)
            )
            or self.recheckAt <= self.qualifiedAt
        ):
            raise ValueError("Policy needs a bounded aware recheck interval")
        for mode, seconds in (
            ("cache", self.cacheSeconds),
            ("retention", self.retentionSeconds),
            ("backup", self.backupSeconds),
        ):
            if (self.modes[mode] == "allowed") != (seconds > 0):
                raise ValueError("Retention duration and mode decision differ")
        if (
            self.cacheSeconds > self.retentionSeconds
            or self.backupSeconds > self.retentionSeconds
        ):
            raise ValueError("Cache/backups cannot outlive allowed retention")
        return self

    @property
    def sha256(self):
        return digest(encoded(self))

    def require(self, *modes, now=None):
        now = now or datetime.now(timezone.utc)
        if not self.qualifiedAt <= now < self.recheckAt or not self.route:
            raise Rejected("SFC_POLICY_UNQUALIFIED")
        if any(self.modes.get(mode) != "allowed" for mode in modes):
            raise Rejected("SFC_MODE_UNQUALIFIED")


# This reviewed record honestly records uncertainty. It grants no source access.
POLICY = Policy(
    purpose="intended_dealing_corporate_verification",
    route="",
    evidenceRef="docs/verification/sfc-20261025/RIGHTS.md",
    evidenceSha256="5b82c868b88214be6af4bd4699c3b5c5af05d6c3388d6e0c5f0fd07a6a44e96c",
    qualifiedAt="2026-10-25T00:00:00Z",
    recheckAt="2026-11-25T00:00:00Z",
    modes={mode: "unknown" for mode in MODES},
)
