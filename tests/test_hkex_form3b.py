import hashlib

import httpx
import pytest

from hkex_form3b_support import CONTEXT, SERIAL, document
from mcp_open_data_hk.curated.hkex.form3b import (
    Form3BAdapter,
    MAX_BODY,
    ORIGIN,
    PATH,
    form3b_url,
    parse_form3b,
)
from mcp_open_data_hk.curated.hkex.contracts import parse_filing
from hkex_support import policy


def test_actual_layout_separates_associated_security_phases_price_kinds_and_explicit_control_links():
    raw = document()
    result = parse_form3b(raw, **CONTEXT)
    row = result.filing
    assert (
        result.raw_sha256 == hashlib.sha256(raw).hexdigest()
        and not result.raw_html_retained
    )
    assert (
        row.securities[0].stock_code == "02536"
        and row.securities[0].share_class is None
    )
    assert (
        row.securities[1].stock_code is None
        and row.securities[1].issued_shares == "10000"
    )
    assert row.securities[1].source_id != row.securities[0].source_id
    assert (
        row.filed_date.value.isoformat() == "2026-10-23"
        and row.event_date.value.isoformat() == "2026-10-20"
    )
    assert row.aware_date.value is None and row.published_date.value is None
    assert row.interests[0].phase == "before" and row.interests[1].phase == "after"
    assert (
        row.interests[0].capacity_code is None
        and row.interests[0].percentage == "10.00"
    )
    assert len(row.interests) == 9 and result.sections["grdCap_Dir_Sh"] == 3
    assert row.particulars[0].shares == "1" and row.particulars[0].price is None
    assert [(p.kind, p.value, p.currency) for p in row.particulars[0].prices] == [
        ("highest", "0.6550", "HKD"),
        ("average", "0.6391", "HKD"),
    ]
    assert (
        row.particulars[0].capacity_before is None
        and row.particulars[0].capacity_after == "2201"
    )
    assert row.controls[1].controlling_party_ref == row.controls[0].controlled_party_ref
    assert all(c.percentage_control == "100.00" for c in row.controls)
    assert all(p.source_global_id is None for p in row.parties)
    assert "SECRET_" not in result.model_dump_json()
    p = policy(codes=result.code_labels)
    assert parse_filing(row.model_dump(mode="json"), p) == row


@pytest.mark.parametrize(
    "change",
    [
        {"lblDStockCode": "00001"},
        {"lblDSerialNo": "DB20261026E99999"},
        {"lblViewCorpName": "Another company"},
        {"lblSignDate": "Date of filing this Form 3A"},
        {"lblDEvtHPrice": "0.123,45"},
        {"lblDSignDate": "2026-10-23"},
    ],
)
def test_identity_layout_and_lossy_values_fail_closed(change):
    with pytest.raises(ValueError):
        parse_form3b(document(**change), **CONTEXT)


def test_populated_unqualified_sections_and_duplicate_source_fields_fail_closed():
    raw = document().replace(
        b"<td></td><td></td><td></td><td></td></tr></table>",
        b"<td>Unqualified trust</td><td></td><td></td><td></td></tr></table>",
    )
    with pytest.raises(ValueError, match="SECTION_TRANSFORM_UNQUALIFIED"):
        parse_form3b(raw, **CONTEXT)
    with pytest.raises(ValueError, match="DUPLICATE_SOURCE_ID"):
        parse_form3b(document() + b'<span id="lblDStockCode">02536</span>', **CONTEXT)


def test_document_transport_uses_exact_context_no_auth_no_redirect_and_raw_response_bytes():
    seen = []
    raw = document()

    def handler(request):
        seen.append(str(request.url))
        assert (
            "authorization" not in request.headers and "cookie" not in request.headers
        )
        return httpx.Response(200, content=raw, headers={"content-type": "text/html"})

    adapter = Form3BAdapter([CONTEXT], transport=httpx.MockTransport(handler))
    status, body, retry = adapter.fetch(
        "detail", ORIGIN + PATH, SERIAL, max_bytes=MAX_BODY, timeout=20
    )
    assert (
        status == 200
        and body == raw
        and retry is None
        and seen == [form3b_url(SERIAL, "12345", "02536")]
    )
    assert (
        adapter.normalize("detail", ORIGIN + PATH, SERIAL, body)["particulars"][0][
            "prices"
        ][1]["value"]
        == "0.6391"
    )
    with pytest.raises(ValueError, match="QUALIFIED_DETAIL_ROUTE"):
        adapter.fetch(
            "detail", "https://other.example", SERIAL, max_bytes=MAX_BODY, timeout=20
        )
    assert len(seen) == 1


def test_transport_does_not_follow_and_cannot_overflow_or_accept_json_as_html():
    seen = []

    def redirect(request):
        seen.append(str(request.url))
        return httpx.Response(
            302,
            content=b"moved",
            headers={"location": "https://other.example", "retry-after": "86400"},
        )

    adapter = Form3BAdapter([CONTEXT], transport=httpx.MockTransport(redirect))
    assert adapter.fetch(
        "detail", ORIGIN + PATH, SERIAL, max_bytes=100, timeout=20
    ) == (302, b"moved", "86400")
    assert len(seen) == 1
    for response, code in [
        (
            httpx.Response(
                200, content=b"x" * 101, headers={"content-type": "text/html"}
            ),
            "BODY_LIMIT",
        ),
        (httpx.Response(200, json={"not": "html"}), "CONTENT_TYPE"),
    ]:
        adapter = Form3BAdapter(
            [CONTEXT], transport=httpx.MockTransport(lambda request: response)
        )
        with pytest.raises(ValueError, match=code):
            adapter.fetch("detail", ORIGIN + PATH, SERIAL, max_bytes=100, timeout=20)


def test_unknown_capacity_is_preserved_but_unqualified_nonempty_codes_are_rejected():
    parsed = parse_form3b(document(), **CONTEXT)
    row = parsed.filing
    with pytest.raises(ValueError, match="UNKNOWN_CAPACITY_CODE"):
        parse_filing(row.model_dump(mode="json"), policy())
    doc = row.model_dump(mode="json")
    doc["controls"][0]["percentage_control"] = "100.01"
    with pytest.raises(ValueError):
        type(row).model_validate(doc)
    doc = row.model_dump(mode="json")
    doc["particulars"][0]["prices"].append(doc["particulars"][0]["prices"][0])
    with pytest.raises(ValueError, match="DUPLICATE_PRICE_KIND"):
        type(row).model_validate(doc)


def test_ambiguous_control_names_never_merge_scoped_parties():
    raw = document().replace(b"Invented Beta", b"Invented Alpha")
    row = parse_form3b(raw, **CONTEXT).filing
    assert row.controls[1].controlling_party_ref == "controller-name-2"
    assert row.controls[1].controlling_party_ref not in {
        c.controlled_party_ref for c in row.controls
    }


def test_repeated_position_amount_in_one_source_cell_is_not_double_counted():
    raw = document().replace(
        b"Long position 970", b"Long position 970 Long position 970"
    )
    with pytest.raises(ValueError, match="POSITION_AMOUNT_LAYOUT"):
        parse_form3b(raw, **CONTEXT)


@pytest.mark.parametrize(
    "change,code",
    [
        (
            {"lblDEvtNatConsider": "Unqualified noncash value"},
            "NONCASH_CONSIDERATION_UNQUALIFIED",
        ),
        ({"lblDEvtReason3": "1101 Third event"}, "EXTRA_EVENT_LAYOUT"),
        ({"lblDEvtAConsider": "1.00"}, "CONSIDERATION_UNIT_UNQUALIFIED"),
    ],
)
def test_material_unqualified_event_fields_are_never_silently_omitted(change, code):
    with pytest.raises(ValueError, match=code):
        parse_form3b(document(**change), **CONTEXT)
