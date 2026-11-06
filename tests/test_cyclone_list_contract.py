"""A documented empty issuer list must not become a false source failure."""

import hashlib
import json

import pytest

from mcp_open_data_hk import cyclone_list
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.review_config import SOURCE_REVIEW
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

EMPTY = b'<?xml version="1.0"?><TropicalCycloneList> </TropicalCycloneList>'
ITEM = (
    "<TropicalCyclone><TropicalCycloneID>0001</TropicalCycloneID>"
    "<TropicalCycloneChineseName>原文</TropicalCycloneChineseName>"
    "<TropicalCycloneEnglishName>Original</TropicalCycloneEnglishName>"
    "<TropicalCycloneURL>https://www.weather.gov.hk/wxinfo/currwx/hko_tctrack_0001.xml</TropicalCycloneURL>"
    "</TropicalCyclone>"
)
POPULATED = ("<TropicalCycloneList>" + ITEM + "</TropicalCycloneList>").encode()


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": cyclone_list.DATASET,
                "title": "HKO forecast track list",
                "provider": "HKO",
            }
        ],
        [
            {
                "id": "list",
                "datasetId": cyclone_list.DATASET,
                "url": cyclone_list.URL,
                "format": "XML",
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_empty_and_populated_lists_revalidate_without_inventing_records(
    service, monkeypatch
):
    body = POPULATED

    async def fetch(url, *args, **kwargs):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    one = await service.resources.query("list")
    assert one["data"]["items"][0]["TropicalCycloneID"] == "0001"
    body = EMPTY
    token = SOURCE_REVIEW.set(True)
    try:
        zero = await service.resources.query("list", require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert zero["meta"]["total"] == 0 and zero["data"]["items"] == []
    assert zero["schema"]["sourceEmptyCollection"] is True
    assert zero["schema"]["profileRowCount"] == 0
    assert zero["schema"]["schemaTypeBasis"] == "publisher_declared_xml_text"
    assert {x["name"] for x in zero["schema"]["fields"]} == set(cyclone_list.FIELDS)
    assert all(x["observedValueCount"] == 0 for x in zero["schema"]["fields"])
    assert zero["schema"]["cacheTTLSeconds"] == 300
    assert zero["meta"]["version"] == hashlib.sha256(EMPTY).hexdigest()
    assert zero["capabilities"]["operations"]["nearby"]["state"] != "available"
    body = POPULATED
    token = SOURCE_REVIEW.set(True)
    try:
        again = await service.resources.query("list", require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert again["data"] == one["data"]


@pytest.mark.parametrize(
    "bad",
    [
        b"<error>Unavailable</error>",
        b"<TropicalCycloneList>Unavailable</TropicalCycloneList>",
        b'<TropicalCycloneList error="true"/>',
        b"<TropicalCycloneList><Error/></TropicalCycloneList>",
        b"<TropicalCycloneList><TropicalCyclone/></TropicalCycloneList>",
        POPULATED.replace(b"<TropicalCycloneID>0001", b"<TropicalCycloneID>1"),
        POPULATED.replace(
            b"</TropicalCyclone>", b"<Extra>changed</Extra></TropicalCyclone>"
        ),
        POPULATED.replace(b"https://www.weather.gov.hk", b"javascript:bad"),
        b"<TropicalCycloneList",
    ],
)
@pytest.mark.asyncio
async def test_errors_unknown_shapes_and_partial_xml_never_become_empty(
    service, monkeypatch, bad
):
    async def fetch(url, *args, **kwargs):
        return bad, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query("list", require_fresh=True)
    assert service.resources.catalogue.check("list")["status"] != "queryable"


@pytest.mark.asyncio
async def test_unpublished_selectors_fail_before_source_access(service, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No request for invalid selectors")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    for args in [{"record_path": "missing"}, {"sheet": "Sheet1"}, {"layer": 0}]:
        with pytest.raises(DomainError, match="INVALID_QUERY"):
            await service.resources.query("list", **args)


@pytest.mark.asyncio
async def test_current_dictionary_fields_compare_to_retained_legacy_fields(
    service, monkeypatch
):
    fields = [{"name": x, "types": ["string"]} for x in cyclone_list.FIELDS]
    legacy = hashlib.sha256(
        json.dumps(
            ["structured-reader-3", "list", "", "", None], sort_keys=True
        ).encode()
    ).hexdigest()
    service.resources.catalogue.accept(
        "list",
        legacy,
        [{x: "old" for x in cyclone_list.FIELDS}],
        {"format": "XML", "fields": fields, "rootTag": "TropicalCycloneList"},
        "legacy-version",
        {},
    )
    old = service.resources.catalogue.check("list", legacy)

    async def fetch(url, *args, **kwargs):
        return EMPTY, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("list", require_fresh=True)
    assert (
        result["meta"]["total"] == 0
        and service.resources.catalogue.check("list", legacy) == old
    )


def test_gml_placeholder_and_other_urls_do_not_inherit_the_empty_list_rule():
    assert not cyclone_list.profile(
        {
            "datasetId": cyclone_list.DATASET,
            "url": cyclone_list.URL + "?other=1",
            "format": "XML",
        }
    )
    assert not cyclone_list.profile(
        {
            "datasetId": "other",
            "url": "https://data.weather.gov.hk/weatherAPI/hko_data/csdi/dataset/tc.zip",
            "format": "GML",
        }
    )
