"""Offline closure of an explicit filing-date page inventory. No source dispatch.

The caller must supply qualified source inventory captures. Event-date search,
daily summaries, names, serial prefixes and signature dates cannot fill omissions.
"""

from .contracts import FORMS, Window, Filing, digest, revision_closure


def qualify(window, pages, filings, *, identity, forms=FORMS):
    window = Window.model_validate(window)
    if window.basis != "filed" or (window.end - window.start).days != 7:
        raise ValueError("SEVEN_DAY_FILING_DATE_WINDOW_REQUIRED")
    if (
        identity.get("issuerId") != window.issuer_id
        or identity.get("permanentSourceIdentityQualified") is not True
        or len(identity.get("sourceEvidenceSha256", "")) != 64
    ):
        raise ValueError("PERMANENT_ISSUER_IDENTITY_REQUIRED")
    if not forms or set(forms) - set(FORMS) or len(set(forms)) != len(forms):
        raise ValueError("EXACT_RELEVANT_FORMS_REQUIRED")
    if not pages or len(pages) > 100:
        raise ValueError("BOUNDED_PAGE_INVENTORY_REQUIRED")
    all_serials = []
    captures = []
    for form in forms:
        group = [p for p in pages if p["form"] == form]
        if not group:
            raise ValueError("FORM_CHANNEL_COVERAGE_GAP")
        total = group[0]["pages"]
        if (
            type(total) is not int
            or not 1 <= total <= 100
            or sorted(p["page"] for p in group) != list(range(1, total + 1))
        ):
            raise ValueError("PAGE_INVENTORY_GAP")
        serials = []
        for page in group:
            if (
                page["pages"] != total
                or page["issuerId"] != window.issuer_id
                or page["channel"] != window.channel
                or page["dateBasis"] != "filed"
                or page["windowStart"] != window.start.isoformat()
                or page["windowEnd"] != window.end.isoformat()
                or page["snapshot"] != group[0]["snapshot"]
                or len(page["captureSha256"]) != 64
                or page["sourceTotal"] != group[0]["sourceTotal"]
            ):
                raise ValueError("FILING_PAGE_SCOPE_OR_SNAPSHOT_MISMATCH")
            if len(page["serials"]) > 100:
                raise ValueError("PAGE_SERIAL_BOUND")
            serials.extend(page["serials"])
            captures.append(page["captureSha256"])
        if len(set(serials)) != len(serials) or len(serials) != group[0]["sourceTotal"]:
            raise ValueError("FILING_SOURCE_TOTAL_OR_DUPLICATE")
        all_serials.extend(serials)
    if any(p["form"] not in forms for p in pages) or len(set(all_serials)) != len(
        all_serials
    ):
        raise ValueError("INVENTORY_FORM_OR_DUPLICATE")
    parsed = [Filing.model_validate(f) for f in filings]
    by_serial = {f.serial: f for f in parsed}
    if len(by_serial) != len(parsed) or not set(all_serials) <= set(by_serial):
        raise ValueError("FILING_DETAIL_INVENTORY_GAP")
    for serial in all_serials:
        f = by_serial[serial]
        if (
            f.issuer_id != window.issuer_id
            or f.channel != window.channel
            or f.form not in forms
            or f.filed_date.precision != "day"
            or f.filed_date.value is None
            or not window.start <= f.filed_date.value < window.end
        ):
            raise ValueError("EXPLICIT_FILING_DATE_OR_IDENTITY_REQUIRED")
    closure = revision_closure(parsed)
    if closure["missing"]:
        raise ValueError("REVISION_CLOSURE_TARGET_MISSING")
    # Revision targets can fall outside the window, but must remain explicit
    # source statements of the same issuer/channel. Never invent absent parents.
    if any(
        f.issuer_id != window.issuer_id or f.channel != window.channel for f in parsed
    ):
        raise ValueError("REVISION_TARGET_IDENTITY_MISMATCH")
    return {
        "window": window.model_dump(mode="json"),
        "forms": list(forms),
        "pages": len(pages),
        "filingSerials": sorted(all_serials),
        "closureTargetSerials": sorted(set(by_serial) - set(all_serials)),
        "pageCapturesSha256": digest(sorted(captures)),
        "revisionClosure": closure,
        "completeWithinQualifiedInventory": True,
        "widerIssuerOrHistoryCoverageQualified": False,
    }
