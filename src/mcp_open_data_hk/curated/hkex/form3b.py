"""Bounded factual English Form 3B parser; no source/output permission grant.

Inspected layout: DB20261026E00008. Contacts, commercial-name codes,
signatures and supplementary narratives are never selected. Nonempty derivative,
joint or trust sections fail closed until their own typed transforms are qualified.
"""

import hashlib
import re
import time
from datetime import datetime
from urllib.parse import urlencode

from pydantic import Field
import httpx

from ..racing.public_results import Document, cells
from .contracts import Filing, SourceDate, Strict, exact

ORIGIN = "https://di.hkex.com.hk"
PATH = "/di/NSForm3B.aspx"
MAX_BODY = 400 * 1024


class ParsedForm3B(Strict):
    filing: Filing
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    code_labels: dict[str, dict[str, str]]
    sections: dict[str, int]
    raw_html_retained: bool = False


class Form3BContext(Strict):
    serial: str = Field(min_length=1, max_length=40)
    source_search_ref: str = Field(min_length=1, max_length=12)
    stock_code: str = Field(min_length=5, max_length=5)
    issuer_id: str = Field(min_length=1, max_length=80)
    issuer_name: str = Field(min_length=1, max_length=300)


class Form3BAdapter:
    """Document-only adapter for the durable collector; no listing/inventory claim.

    The collector reserves before calling fetch. This class never follows a
    redirect, accepts an arbitrary URL, reuses authentication, or retries a request.
    """

    def __init__(self, contexts, transport=None):
        self.contexts = {}
        self.transport = transport
        for raw in contexts:
            if len(self.contexts) >= 5000:
                raise ValueError("FORM3B_CONTEXT_LIMIT")
            context = Form3BContext.model_validate(raw)
            form3b_url(context.serial, context.source_search_ref, context.stock_code)
            exact(context.issuer_id)
            if context.serial in self.contexts:
                raise ValueError("FORM3B_DUPLICATE_CONTEXT")
            self.contexts[context.serial] = context

    def source_url(self, kind, route, key):
        if kind != "detail" or route != ORIGIN + PATH or key not in self.contexts:
            raise ValueError("FORM3B_QUALIFIED_DETAIL_ROUTE_REQUIRED")
        context = self.contexts[key]
        return form3b_url(key, context.source_search_ref, context.stock_code)

    def fetch(self, kind, route, key, *, max_bytes, timeout):
        url = self.source_url(kind, route, key)
        if type(max_bytes) is not int or max_bytes < 1 or not 0 < timeout <= 20:
            raise ValueError("FORM3B_REQUEST_BOUND_REQUIRED")
        limit = min(MAX_BODY, max_bytes)
        deadline = time.monotonic() + timeout
        body = bytearray()
        with httpx.Client(
            timeout=timeout,
            trust_env=False,
            follow_redirects=False,
            transport=self.transport,
        ) as client:
            with client.stream(
                "GET",
                url,
                headers={
                    "User-Agent": "mcp.hk disclosure collector (+https://mcp.hk)",
                    "Accept": "text/html",
                    "Accept-Encoding": "identity",
                },
                follow_redirects=False,
            ) as response:
                if (
                    response.status_code == 200
                    and "text/html"
                    not in response.headers.get("content-type", "").lower()
                ):
                    raise ValueError("FORM3B_CONTENT_TYPE")
                for chunk in response.iter_bytes(chunk_size=32768):
                    if time.monotonic() > deadline:
                        raise httpx.ReadTimeout("Form document deadline")
                    if len(body) + len(chunk) > limit:
                        raise ValueError("FORM3B_BODY_LIMIT")
                    body.extend(chunk)
                return (
                    response.status_code,
                    bytes(body),
                    response.headers.get("retry-after"),
                )

    def normalize(self, kind, route, key, body):
        self.source_url(kind, route, key)
        return parse_form3b(body, **self.contexts[key].model_dump()).filing.model_dump(
            mode="json"
        )


def form3b_url(serial, source_search_ref, stock_code):
    if (
        not re.fullmatch(r"DB[0-9]{8}E[0-9]{5}", serial)
        or not re.fullmatch(r"[1-9][0-9]{0,11}", source_search_ref)
        or not re.fullmatch(r"[0-9]{5}", stock_code)
    ):
        raise ValueError("FORM3B_EXACT_SOURCE_CONTEXT_REQUIRED")
    return (
        ORIGIN
        + PATH
        + "?"
        + urlencode(
            {"fn": serial, "sid": source_search_ref, "sc": stock_code, "lang": "EN"}
        )
    )


def number(value):
    if value in {"", "-", "--", "---"}:
        return None
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]+)?", value):
        raise ValueError("FORM3B_DECIMAL_LAYOUT")
    return value.replace(",", "")


def source_date(value):
    if value in {"", "(dd/mm/yyyy)"}:
        return SourceDate()
    match = re.fullmatch(r"([0-9]{2}/[0-9]{2}/[0-9]{4})(?: \(dd/mm/yyyy\))?", value)
    if not match:
        raise ValueError("FORM3B_DATE_LAYOUT")
    return SourceDate(
        value=datetime.strptime(match[1], "%d/%m/%Y").date(), precision="day"
    )


def parse_form3b(raw, *, serial, source_search_ref, stock_code, issuer_id, issuer_name):
    """Parse an exact source-linked document without cross-filing identity joins.

    The search reference is source context, not a verified permanent issuer ID.
    All associated securities and related-party references remain filing-scoped.
    Unique exact names explicitly declared in the same control table link its
    rows only; ambiguous names never resolve to an existing corporation reference.
    """
    form3b_url(serial, source_search_ref, stock_code)
    exact(issuer_id)
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_BODY:
        raise ValueError("FORM3B_BODY_LIMIT")
    root = Document(raw.decode("utf-8-sig")).root
    nodes, duplicates = {}, set()
    for node in root.all():
        key = node.attrs.get("id")
        if key:
            if key in nodes:
                duplicates.add(key)
            nodes[key] = node

    def source_node(key):
        if key in duplicates:
            raise ValueError("FORM3B_DUPLICATE_SOURCE_ID")
        return nodes.get(key)

    def text(key, required=False):
        node = source_node(key)
        if node is None:
            if required:
                raise ValueError("FORM3B_LAYOUT_MISSING")
            return ""
        value = node.text()
        if len(value) > 500 or required and not value:
            raise ValueError("FORM3B_FIELD_LIMIT")
        return value

    def rows(key):
        table = source_node(key)
        if table is None or table.tag != "table":
            raise ValueError("FORM3B_TABLE_MISSING")
        values = []
        for row in table.all("tr"):
            parent = row.parent
            while parent and parent.tag != "table":
                parent = parent.parent
            if parent is table:
                values.append([cell.text() for cell in cells(row)])
        if not values or len(values) > 501 or any(len(v) > 20 for v in values):
            raise ValueError("FORM3B_TABLE_LIMIT")
        return values

    if (
        text("lblDSerialNo", True) != serial
        or text("lblDStockCode", True) != stock_code
        or text("lblViewCorpName", True) != issuer_name
        or text("lblSignDate", True) != "Date of filing this Form 3B"
    ):
        raise ValueError("FORM3B_SOURCE_IDENTITY_MISMATCH")
    associated_name = text("lblDAssoCorpName", True)
    primary, associated = serial + "_listed", serial + "_associated"
    interests, particulars, parties, controls = [], [], [], []
    codes = {"capacity": {}, "reason": {}}
    sections = {}

    def coded(value, family):
        if not value:
            return None
        match = re.fullmatch(r"([0-9]{4})\s+(.+)", value)
        if not match:
            raise ValueError("FORM3B_CODE_LAYOUT")
        prior = codes[family].setdefault(match[1], match[2])
        if prior != match[2]:
            raise ValueError("FORM3B_CODE_LABEL_CONFLICT")
        return match[1]

    def position(value):
        try:
            return {"Long position": "long", "Short position": "short"}[value]
        except KeyError:
            raise ValueError("FORM3B_POSITION_LAYOUT") from None

    def amounts(value):
        matches = list(
            re.finditer(r"(Long position|Short position)\s+([0-9,.]+)", value)
        )
        if (
            not matches
            or " ".join(m[0] for m in matches) != value
            or len({m[1] for m in matches}) != len(matches)
        ):
            raise ValueError("FORM3B_POSITION_AMOUNT_LAYOUT")
        return [(position(m[1]), number(m[2])) for m in matches]

    def interest(section, line, pos, shares, **extra):
        interests.append(
            dict(
                line=line,
                section=section,
                security_id=associated,
                capacity_code=None,
                nature="unknown",
                position=pos,
                phase="declared",
                instrument="associated_shares",
                shares=shares,
                unit="shares",
                **extra,
            )
        )

    if any(
        text(key)
        for key in nodes
        if re.fullmatch(
            r"lblDEvt(?:Reason|Share|Position|HPrice|APrice|AConsider|NatConsider|Currency|CapBefore|CapAfter)(?:[3-9]|[1-9][0-9]+)",
            key,
        )
    ):
        raise ValueError("FORM3B_EXTRA_EVENT_LAYOUT")

    for key, phase, label in (
        ("grdSh_BEvt", "before", "Total shares immediately before the relevant event"),
        ("grdSh_AEvt", "after", "Total shares immediately after the relevant event"),
    ):
        if text("lblSh_BEvt" if phase == "before" else "lblSh_AEvt", True) != label:
            raise ValueError("FORM3B_AGGREGATE_LABEL_DRIFT")
        table = rows(key)
        if table[0] != ["", "Total number of shares", "Percentage figure (%)"]:
            raise ValueError("FORM3B_AGGREGATE_LAYOUT")
        sections[key] = len(table) - 1
        for i, row in enumerate(table[1:], 1):
            if len(row) != 3:
                raise ValueError("FORM3B_AGGREGATE_LAYOUT")
            interests.append(
                dict(
                    line=str(i),
                    section=key,
                    security_id=associated,
                    capacity_code=None,
                    nature="unknown",
                    position=position(row[0]),
                    phase=phase,
                    instrument="associated_shares",
                    shares=number(row[1]),
                    percentage=number(row[2]),
                    unit="shares",
                )
            )

    table = rows("grdCap_Dir_Sh")
    if table[0] != ["Capacity code", "Number of shares"]:
        raise ValueError("FORM3B_CAPACITY_LAYOUT")
    sections["grdCap_Dir_Sh"] = len(table) - 1
    for i, row in enumerate(table[1:], 1):
        if len(row) != 2:
            raise ValueError("FORM3B_CAPACITY_LAYOUT")
        code = coded(row[0], "capacity")
        for j, (pos, quantity) in enumerate(amounts(row[1]), 1):
            interests.append(
                dict(
                    line=f"{i}-{j}",
                    section="grdCap_Dir_Sh",
                    security_id=associated,
                    capacity_code=code,
                    nature="unknown",
                    position=pos,
                    phase="declared",
                    instrument="associated_shares",
                    shares=quantity,
                    unit="shares",
                )
            )

    for suffix in ("", "2"):
        if text("lblDEvtNatConsider" + suffix):
            raise ValueError("FORM3B_NONCASH_CONSIDERATION_UNQUALIFIED")
        if text("lblDEvtAConsider" + suffix):
            raise ValueError("FORM3B_CONSIDERATION_UNIT_UNQUALIFIED")
        reason = text("lblDEvtReason" + suffix)
        quantity = text("lblDEvtShare" + suffix)
        before = text("lblDEvtCapBefore" + suffix)
        after = text("lblDEvtCapAfter" + suffix)
        price_values = [
            (kind, text(key + suffix))
            for kind, key in (
                ("highest", "lblDEvtHPrice"),
                ("average", "lblDEvtAPrice"),
            )
        ]
        if not any(
            [reason, quantity, before, after, *(value for _, value in price_values)]
        ):
            continue
        currency = text("lblDEvtCurrency" + suffix) or None
        particulars.append(
            dict(
                line="event-" + (suffix or "1"),
                reason_code=coded(reason, "reason"),
                shares=number(quantity),
                price=None,
                currency=None,
                unit="shares",
                security_id=associated,
                position=position(text("lblDEvtPosition" + suffix, True)),
                capacity_before=coded(before, "capacity"),
                capacity_after=coded(after, "capacity"),
                prices=[
                    dict(kind=kind, value=number(value), currency=currency)
                    for kind, value in price_values
                    if number(value) is not None
                ],
            )
        )

    family = rows("grdFI_Sh")
    if family[0] != ["Child/Spouse", "Name of child/spouse", "Number of shares"]:
        raise ValueError("FORM3B_FAMILY_LAYOUT")
    sections["grdFI_Sh"] = 0
    for i, row in enumerate(family[1:], 1):
        if not any(row):
            continue
        if len(row) != 3 or row[0] != "Spouse" or not row[1]:
            raise ValueError("FORM3B_FAMILY_FIELDS_UNQUALIFIED")
        ref = "spouse-" + str(i)
        parties.append(
            dict(ref=ref, disclosed_name=row[1], association="disclosed_spouse")
        )
        for j, (pos, quantity) in enumerate(amounts(row[2]), 1):
            interest("grdFI_Sh", f"{i}-{j}", pos, quantity, party_ref=ref)
        sections["grdFI_Sh"] += 1

    companies = rows("grdCtrlCorp")
    expected_header = [
        "Name of controlled corporation",
        "Address and place of incorporation",
        "Name of controlling person",
        "% control",
        "Direct interest (Y/N)",
        "Number of shares",
    ]
    if companies[0] != expected_header:
        raise ValueError("FORM3B_CONTROL_LAYOUT")
    company_rows = [row for row in companies[1:] if any(row)]
    if any(len(row) != 6 for row in company_rows):
        raise ValueError("FORM3B_CONTROL_LAYOUT")
    names = [row[0] for row in company_rows]
    for i, row in enumerate(company_rows, 1):
        # The address column is deliberately neither copied nor normalized.
        name, _, controller_name, percent, direct, quantities = row
        if not name or not controller_name or direct not in {"Y", "N", ""}:
            raise ValueError("FORM3B_CONTROL_LAYOUT")
        ref = "controlled-" + str(i)
        parties.append(
            dict(
                ref=ref,
                disclosed_name=name,
                association="disclosed_controlled_corporation",
            )
        )
        matches = [n + 1 for n, other in enumerate(names) if other == controller_name]
        if len(matches) == 1:
            controlling = "controlled-" + str(matches[0])
        else:
            controlling = "controller-name-" + str(i)
            parties.append(
                dict(
                    ref=controlling,
                    disclosed_name=controller_name,
                    association="disclosed_controlling_name",
                )
            )
        controls.append(
            dict(
                line=str(i),
                controlled_party_ref=ref,
                controlling_party_ref=controlling,
                percentage_control=number(percent),
                direct_interest={"Y": "yes", "N": "no", "": "unknown"}[direct],
            )
        )
        for j, (pos, quantity) in enumerate(amounts(quantities), 1):
            interest("grdCtrlCorp", f"{i}-{j}", pos, quantity, party_ref=ref)
    sections["grdCtrlCorp"] = len(company_rows)

    empty_headers = {
        "grdDer_Dir": [
            "",
            "",
            "Begins",
            "Ends",
            "Currency",
            "Price for grant",
            "Currency",
            "Exercise price",
            "Currency",
            "Price on assignment",
            "",
        ],
        "grdJI_Sh": ["Name of joint shareholder", "Address", "Number of shares"],
        "grdTrust_Sh": ["Names of Trust", "Address", "Status code", "Number of shares"],
    }
    for key, header in empty_headers.items():
        table = rows(key)
        if table[0] != header:
            raise ValueError("FORM3B_EMPTY_SECTION_LAYOUT")
        if any(any(row) for row in table[1:]):
            raise ValueError("FORM3B_SECTION_TRANSFORM_UNQUALIFIED")
        sections[key] = 0

    replaces = text("lblDRevisePrevSN") or None
    # This adapter qualifies incoming amendments only. A populated outgoing or
    # withdrawal state must not silently become an original filing. Full-window
    # closure needs a separately qualified listing and revision adapter.
    related = {
        match[1]
        for node in root.all("a")
        if (
            match := re.search(r"[?&]fn=([A-Z0-9]+)(?:&|$)", node.attrs.get("href", ""))
        )
    }
    if related - {serial, replaces} or re.search(
        r"(?:superseded\s+by\s*:?\s*D[A-Z][0-9]{8}[A-Z][0-9]{5}|(?:this\s+)?form\s+(?:has\s+been\s+)?withdrawn)",
        root.text(),
        re.I,
    ):
        raise ValueError("FORM3B_REVISION_STATE_UNQUALIFIED")
    subject = " ".join(
        filter(
            None,
            [text("lblDSurname", True), text("lblDFirstname"), text("lblDMidname")],
        )
    )
    filing = Filing.model_validate(
        dict(
            serial=serial,
            issuer_id=issuer_id,
            issuer_name=issuer_name,
            channel="dion",
            form="3B",
            subject=subject,
            subject_name_zh_hant=text("lblDChiName") or None,
            event_date=source_date(text("lblDEventDate", True)),
            aware_date=source_date(text("lblDAwareDate")),
            filed_date=source_date(text("lblDSignDate", True)),
            state="amendment" if replaces else "original",
            replaces=replaces,
            securities=[
                dict(
                    source_id=primary,
                    stock_code=stock_code,
                    share_class=None,
                    name=issuer_name,
                ),
                dict(
                    source_id=associated,
                    stock_code=None,
                    share_class=text("lblDClass") or None,
                    name=associated_name,
                    issued_shares=number(text("lblDIssued")),
                ),
            ],
            interests=interests,
            particulars=particulars,
            parties=parties,
            controls=controls,
        )
    )
    return ParsedForm3B(
        filing=filing,
        raw_sha256=hashlib.sha256(raw).hexdigest(),
        code_labels=codes,
        sections=sections,
    )
