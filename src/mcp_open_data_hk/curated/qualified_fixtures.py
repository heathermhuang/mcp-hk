"""Synthetic contract validators only; no source access or public integration.

These contracts let identifiers and event semantics be tested while exact provider
access, storage and output modes remain unresolved. They do not parse provider
PDFs/HTML or enable collection.
"""

import re
from datetime import date

from .official import SourceRejected


def exact(value, pattern):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise SourceRejected("INVALID_EXACT_SOURCE_ID")
    return value


def dated(value):
    if value is not None:
        date.fromisoformat(value)
    return value


def dissolution_notice(row):
    namespace = row["identifier"]["namespace"]
    if namespace not in {"cr:brn", "cr:crn"}:
        raise SourceRejected("NOTICE_IDENTIFIER_NAMESPACE_UNQUALIFIED")
    value = exact(row["identifier"]["value"], r"[0-9]{1,12}")
    kind = row["noticeType"]
    if kind not in {
        "proposed_striking_off",
        "dissolution",
        "withdrawal",
        "restoration",
        "correction",
    }:
        raise SourceRejected("NOTICE_TYPE_UNQUALIFIED")
    event_date = dated(row.get("eventDate"))
    # Only an explicit qualified actual dissolution notice/date can assert that event.
    return dict(
        row,
        entity_id=namespace + ":" + value,
        issueDate=dated(row["issueDate"]),
        eventDate=event_date,
        effectiveDissolution=kind == "dissolution" and event_date is not None,
        supersedes=row.get("supersedes"),
        syntheticContract=True,
    )


def sfc_corporate(row):
    ce = exact(row["ceReference"], r"[A-Z]{3}[0-9]{3}")
    if (
        row.get("purpose") != "licence_verification"
        or row.get("entityType") != "corporate"
    ):
        raise SourceRejected("SFC_PURPOSE_OR_CORPORATE_SCOPE")
    if any(
        k in row
        for k in ("email", "telephone", "formerExecutiveOfficers", "inferredBrn")
    ):
        raise SourceRejected("SFC_FIELD_OUTSIDE_PILOT")
    return dict(
        row,
        entity_id="sfc:ce:" + ce,
        coveredThrough=dated(row.get("coveredThrough")),
        syntheticContract=True,
    )


def hkex_disclosure(row):
    filing = exact(row["filingId"], r"[A-Za-z0-9_-]{1,80}")
    issuer = exact(row["issuerId"], r"[A-Za-z0-9_-]{1,80}")
    if row.get("replaces") == filing:
        raise SourceRejected("SELF_REPLACING_FILING")
    return dict(
        row,
        filing_id="hkex:di:" + filing,
        issuer_id="hkex:issuer:" + issuer,
        eventDate=dated(row.get("eventDate")),
        filedDate=dated(row.get("filedDate")),
        publishedDate=dated(row.get("publishedDate")),
        syntheticContract=True,
    )
