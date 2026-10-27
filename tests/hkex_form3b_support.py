"""Invented facts rendered in the inspected Form 3B field/table structure."""

from html import escape

SERIAL = "DB20261026E00001"
CONTEXT = dict(
    serial=SERIAL,
    source_search_ref="12345",
    stock_code="02536",
    issuer_id="TEST_SEARCH_12345",
    issuer_name="Invented Listed Ltd",
)


def span(key, value):
    return f'<span id="{key}">{escape(value)}</span>'


def table(key, rows):
    return (
        f'<table id="{key}">'
        + "".join(
            "<tr>" + "".join("<td>" + value + "</td>" for value in row) + "</tr>"
            for row in rows
        )
        + "</table>"
    )


def document(**updates):
    values = dict(
        lblDSerialNo=SERIAL,
        lblDStockCode="02536",
        lblViewCorpName="Invented Listed Ltd",
        lblDAssoCorpName="Invented Associated Ltd",
        lblDClass="Ordinary",
        lblDIssued="10,000",
        lblDSurname="Example",
        lblDFirstname="Person",
        lblDMidname="",
        lblDChiName="測試姓名",
        lblDCharCode="SECRET_COMMERCIAL_CODE",
        lblDRegOffice="SECRET_ADDRESS",
        lblDSuppInfo="SECRET_NARRATIVE",
        lblSignDate="Date of filing this Form 3B",
        lblDEventDate="20/10/2026 (dd/mm/yyyy)",
        lblDSignDate="23/10/2026 (dd/mm/yyyy)",
        lblDAwareDate="(dd/mm/yyyy)",
        lblDRevisePrevSN="",
        lblSh_BEvt="Total shares immediately before the relevant event",
        lblSh_AEvt="Total shares immediately after the relevant event",
        lblDEvtPosition="Long position",
        lblDEvtReason="1101 Invented source event description",
        lblDEvtCapBefore="",
        lblDEvtCapAfter="2201 Declared controlled-corporation capacity",
        lblDEvtShare="1",
        lblDEvtCurrency="HKD",
        lblDEvtHPrice="0.6550",
        lblDEvtAPrice="0.6391",
        lblDEvtAConsider="",
        lblDEvtPosition2="Short position",
        lblDEvtReason2="",
        lblDEvtShare2="",
    )
    values.update(updates)
    result = "".join(span(k, v) for k, v in values.items())
    for key, quantity, percent in (
        ("grdSh_BEvt", "1,000", "10.00"),
        ("grdSh_AEvt", "1,001", "10.01"),
    ):
        result += table(
            key,
            [
                ["", "Total number of shares", "Percentage figure (%)"],
                ["Long position", quantity, percent],
            ],
        )

    def nested(a, b):
        return "<table><tr><td>" + a + "</td><td>" + b + "</td></tr></table>"

    result += table(
        "grdCap_Dir_Sh",
        [
            ["Capacity code", "Number of shares"],
            [nested("2101", "Invented direct capacity"), nested("Long position", "10")],
            [
                nested("2201", "Declared controlled-corporation capacity"),
                nested("Long position", "976"),
            ],
            [nested("2202", "Invented spouse capacity"), nested("Long position", "15")],
        ],
    )
    result += table(
        "grdFI_Sh",
        [
            ["Child/Spouse", "Name of child/spouse", "Number of shares"],
            ["Spouse", "Invented Spouse", "Long position 15"],
        ],
    )
    result += table(
        "grdCtrlCorp",
        [
            [
                "Name of controlled corporation",
                "Address and place of incorporation",
                "Name of controlling person",
                "% control",
                "Direct interest (Y/N)",
                "Number of shares",
            ],
            [
                "Invented Alpha",
                "SECRET_CONTROL_ADDRESS_A",
                "Invented Controller",
                "100.00",
                "N",
                "Long position 970",
            ],
            [
                "Invented Beta",
                "SECRET_CONTROL_ADDRESS_B",
                "Invented Alpha",
                "100.00",
                "Y",
                "Long position 970",
            ],
            [
                "Invented Gamma",
                "SECRET_CONTROL_ADDRESS_C",
                "Invented Controller",
                "100.00",
                "Y",
                "Long position 6",
            ],
        ],
    )
    result += table(
        "grdDer_Dir",
        [
            [
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
            [""] * 11,
        ],
    )
    result += table(
        "grdJI_Sh",
        [["Name of joint shareholder", "Address", "Number of shares"], ["", "", ""]],
    )
    result += table(
        "grdTrust_Sh",
        [
            ["Names of Trust", "Address", "Status code", "Number of shares"],
            ["", "", "", ""],
        ],
    )
    return result.encode()
