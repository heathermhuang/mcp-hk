"""Checksum-pinned, mode-specific source rights; flags never confer permission."""

import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit

FAMILIES = (
    "races",
    "declared_runners",
    "results",
    "profiles",
    "sectionals",
    "dividends",
    "barrier_trials",
    "comments",
    "jockey_rankings",
    "trainer_rankings",
    "track_conditions",
    "jackpots",
    "odds",
    "pool_investments",
    "changes",
)
MODES = (
    "collect",
    "cache",
    "history",
    "rest",
    "mcp",
    "browser",
    "links",
    "export",
    "schedule",
)
ORIGINS = {"https://racing.hkjc.com", "https://bet.hkjc.com"}


class RacingRejected(ValueError):
    """Stable safe error code; provider payloads never enter public errors."""


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()


def checksum(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def utc(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (AttributeError, TypeError, ValueError) as exc:
        raise RacingRejected("INVALID_UTC_TIME") from exc


def location(value):
    """Only exact approved public origins; route permission is checked separately."""
    try:
        url = urlsplit(value)
        origin = f"{url.scheme}://{url.netloc}"
        if (
            origin not in ORIGINS
            or url.username
            or url.password
            or url.fragment
            or not url.path.startswith("/")
            or len(value) > 1000
        ):
            raise ValueError()
        return value
    except (TypeError, ValueError) as exc:
        raise RacingRejected("SOURCE_LOCATION_REJECTED") from exc


def validate_policy(record):
    if (
        record.get("source") != "hkjc"
        or record.get("purpose") != "read_only_racing_facts"
        or record.get("schema") != "racing-policy-v1"
    ):
        raise RacingRejected("POLICY_SCOPE_REJECTED")
    utc(record["qualifiedAt"])
    if utc(record["recheckAt"]) <= utc(record["qualifiedAt"]):
        raise RacingRejected("POLICY_RECHECK_REJECTED")
    if record.get("state") not in {"unknown", "active", "revoked"}:
        raise RacingRejected("POLICY_STATE_REJECTED")
    for family, grant in record.get("families", {}).items():
        if family not in FAMILIES or set(grant.get("modes", {})) != set(MODES):
            raise RacingRejected("POLICY_MODES_REJECTED")
        if any(
            value not in {"unknown", "denied", "allowed"}
            for value in grant["modes"].values()
        ):
            raise RacingRejected("POLICY_MODES_REJECTED")
        if any(value == "allowed" for value in grant["modes"].values()):
            if (
                not grant.get("evidenceRef")
                or len(grant.get("evidenceSha256", "")) != 64
                or not grant.get("fields")
                or not grant.get("routes")
                or type(grant.get("retentionSeconds")) is not int
                or grant["retentionSeconds"] <= 0
                or type(grant.get("minIntervalSeconds")) is not int
                or grant["minIntervalSeconds"] < 1
            ):
                raise RacingRejected("POLICY_EVIDENCE_REQUIRED")
        if "rawRetentionSeconds" in grant and (
            type(grant["rawRetentionSeconds"]) is not int
            or not 0 <= grant["rawRetentionSeconds"] <= grant.get("retentionSeconds", 0)
        ):
            raise RacingRejected("RAW_RETENTION_UNQUALIFIED")
        for route in grant.get("routes", []):
            location(route)
    return record


def require(record, pinned, family, mode, *, now=None, route=None, fields=()):
    validate_policy(record)
    now = now or datetime.now(timezone.utc)
    if (
        checksum(record) != pinned
        or record["state"] != "active"
        or utc(record["qualifiedAt"]) > now
        or utc(record["recheckAt"]) <= now
    ):
        raise RacingRejected("SOURCE_POLICY_INACTIVE")
    grant = record.get("families", {}).get(family, {})
    if (
        family not in FAMILIES
        or mode not in MODES
        or grant.get("modes", {}).get(mode) != "allowed"
    ):
        raise RacingRejected("SOURCE_MODE_UNQUALIFIED")
    if route is not None and location(route) not in grant.get("routes", []):
        raise RacingRejected("SOURCE_ROUTE_UNQUALIFIED")
    if not set(fields).issubset(grant.get("fields", [])):
        raise RacingRejected("SOURCE_FIELDS_UNQUALIFIED")
    return grant
