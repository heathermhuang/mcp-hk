"""Native archive/group selection, scoped discovery and bounded ZIP safety."""

import hashlib
import asyncio
import io
import stat
import threading
import zipfile

import pytest

from mcp_open_data_hk import census_xml_archives as census
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.resource_serializations import read
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


def zipped(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in entries:
            archive.writestr(name, value)
    return output.getvalue()


def document(value="0012"):
    return (
        "<root><Table_Information><Title>Native</Title></Table_Information>"
        "<Observation><SV>007</SV><Obs_val>" + value + "</Obs_val></Observation>"
        "<Class_code><Code>01</Code><Name>原文</Name></Class_code></root>"
    ).encode()


def nested():
    return zipped(
        [
            (
                name,
                zipped([("table.xml", document(value)), ("table.xsd", b"<schema/>")]),
            )
            for name, value in [("F101s.zip", "0012"), ("F102s.zip", "..")]
        ]
    )


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    did, url = next(iter(census.SOURCES.items()))
    service.resources.catalogue.publish(
        [{"id": did, "title": "Census16", "provider": "C&SD"}],
        [
            {
                "id": "xml",
                "datasetId": did,
                "url": url,
                "format": "XML",
                "catalogue": "DATA.GOV.HK",
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
            }
        ],
        {},
    )
    service.resources.catalogue.failure("xml", "UNSUPPORTED_FORMAT", "unsupported")
    return service


@pytest.mark.asyncio
async def test_choices_are_not_acceptance_and_scoped_choices_do_not_replace_root(
    service, monkeypatch
):
    body = nested()

    async def fetch(url, *args, **kwargs):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    root = await service.resources.schema("xml")
    assert root["recordCount"] is None and not root["structuredQueryable"]
    assert [x["value"] for x in root["selections"][0]["options"]] == [
        "file:F101s.zip",
        "file:F102s.zip",
    ]
    saved = service.resources.catalogue.selection_options("xml")
    child = await service.resources.schema("xml", record_path="file:F101s.zip")
    group = child["selections"][0]
    assert group["scopedToRecordPath"] == "file:F101s.zip"
    assert all(
        x["nextAction"]["arguments"]["recordPath"].startswith("file:F101s.zip/")
        for x in group["options"]
    )
    result = await service.resources.query(
        "xml", record_path="file:F101s.zip/Observation"
    )
    assert result["data"]["items"] == [{"SV": "007", "Obs_val": "0012"}]
    assert result["meta"]["version"] == hashlib.sha256(body).hexdigest()
    assert (
        result["schema"]["sourceDictionarySha256"]
        == hashlib.sha256(b"<schema/>").hexdigest()
    )
    assert result["schema"]["sourceArchiveMember"] == "F101s.zip"
    assert result["schema"]["scope"] == "selected_native_xml_group"
    other = await service.resources.query(
        "xml", record_path="file:F102s.zip/Observation"
    )
    assert other["data"]["items"][0]["Obs_val"] == ".."
    assert service.resources.catalogue.selection_options("xml") == saved


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"record_path": "file:F101s.zip"},
        {"record_path": "../table"},
        {"record_path": "file:F101s.zip/Observation", "sheet": "Sheet1"},
        {"record_path": "file:F101s.zip/Observation", "layer": 0},
    ],
)
@pytest.mark.asyncio
async def test_invalid_or_incomplete_query_fails_before_fetch(
    service, monkeypatch, query
):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Invalid selector attempted provider access")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    with pytest.raises(DomainError):
        await service.resources.query("xml", **query)


def test_only_exact_profile_supports_nested_archives():
    did, url = next(iter(census.SOURCES.items()))
    resource = {"datasetId": did, "url": url, "format": "XML"}
    assert census.profile(resource)
    assert not census.profile({"format": "XML"})
    for other in [
        {**resource, "url": url + "?other=1"},
        {**resource, "datasetId": "other"},
    ]:
        assert not census.profile(other)
        assert read(other, nested(), "file:F101s.zip/Observation") is None
    with pytest.raises(DomainError) as exc:
        parse(nested(), "XML", "Observation")
    assert exc.value.code == "UNSUPPORTED_FORMAT"


@pytest.mark.parametrize(
    "member", ["../F101s.zip", "folder/F101s.zip", "folder\\F101s.zip", "F101s.txt"]
)
def test_unexpected_paths_or_members_are_held(member):
    with pytest.raises(DomainError):
        census.choices(
            zipped([(member, zipped([("table.xml", document()), ("table.xsd", b"x")]))])
        )


@pytest.mark.parametrize(
    "children",
    [
        [("next.zip", zipped([("table.xml", document())]))],
        [("table.xml", document())],
        [("one.xml", document()), ("two.xml", document()), ("table.xsd", b"x")],
        [("table.xml", document()), ("table.xml", document())],
    ],
)
def test_depth_dictionary_and_duplicate_layouts_are_held(children):
    with pytest.raises(DomainError):
        census.choices(zipped([("F101s.zip", zipped(children))]))


def test_cumulative_member_and_expansion_limits(monkeypatch):
    monkeypatch.setattr(census, "MAX_MEMBERS", 3)
    with pytest.raises(DomainError) as exc:
        census.choices(nested())
    assert exc.value.code == "SOURCE_TOO_LARGE"
    monkeypatch.setattr(census, "MAX_MEMBERS", 1000)
    monkeypatch.setattr(census, "MAX_EXPANDED", 1000)
    with pytest.raises(DomainError) as exc:
        census.choices(
            zipped(
                [
                    (
                        "F101s.zip",
                        zipped(
                            [("table.xml", document("x" * 2000)), ("table.xsd", b"x")]
                        ),
                    )
                ]
            )
        )
    assert exc.value.code == "SOURCE_TOO_LARGE"


def test_nonregular_malformed_and_unknown_selections_are_held():
    link = zipfile.ZipInfo("F101s.zip")
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(DomainError):
        census.choices(zipped([(link, b"target")]))
    with pytest.raises(DomainError):
        census.choices(b"not a zip")
    for value in ["file:missing.zip/Observation", "file:F101s.zip/missing"]:
        with pytest.raises(DomainError) as exc:
            census.read(nested(), value)
        assert exc.value.code == "INVALID_RECORD_PATH"


@pytest.mark.parametrize("body", [b"prefix" + nested(), nested() + b"trailing"])
def test_unconsumed_outer_framing_is_held(body):
    with pytest.raises(DomainError):
        census.choices(body)


def test_unconsumed_inner_framing_is_held():
    inner = zipped([("table.xml", document()), ("table.xsd", b"x")])
    with pytest.raises(DomainError):
        census.choices(zipped([("F101s.zip", inner + b"trailing")]))


@pytest.mark.asyncio
async def test_metadata_parsing_keeps_both_existing_scan_slots_owned(
    service, monkeypatch
):
    body = nested()
    entered = []
    fetched = []
    ready = threading.Event()
    release = threading.Event()
    original = census.choices

    def blocked_choices(*args):
        entered.append(1)
        if len(entered) >= 2:
            ready.set()
        assert release.wait(5)
        return original(*args)

    async def fetch(url, *args, **kwargs):
        fetched.append(url)
        return body, {}, url, 200

    monkeypatch.setattr(census, "choices", blocked_choices)
    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    tasks = [asyncio.create_task(service.resources.schema("xml")) for _ in range(2)]
    try:
        assert await asyncio.to_thread(ready.wait, 2)
        tasks.append(asyncio.create_task(service.resources.schema("xml")))
        await asyncio.sleep(0.02)
        assert len(fetched) == 2
    finally:
        release.set()
        await asyncio.gather(*tasks)
    assert len(fetched) == 3
