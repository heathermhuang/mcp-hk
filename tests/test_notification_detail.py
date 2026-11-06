"""A native ID selects one complete, unexecuted notification-detail object."""

import hashlib
import json

import pytest

from mcp_open_data_hk import notification_detail as detail
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.published_requests import request_requirements
from mcp_open_data_hk.resource_serializations import read
from mcp_open_data_hk.resources import source_parameters, template_url
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


def native(ident=7):
    return {
        "id": ident,
        "subject_en": "Original",
        "subject_tc": "原文",
        "subject_sc": "原文",
        "msg_en": '{"body":[{"type":"A","val":"https://example.invalid/"}]}',
        "msg_tc": "<b>Original text</b>",
        "msg_sc": "007",
        "schedule_ts": 1793920945000,
        "exp_ts": 1793942545000,
        "source_id": "TD0001",
    }


def wrapped(value):
    return ("\nNotiDetail(" + json.dumps(value, ensure_ascii=False) + ");\n").encode()


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": detail.DATASET, "title": "Notifications", "provider": "DPO"}],
        [
            {
                "id": "detail",
                "datasetId": detail.DATASET,
                "url": detail.URL,
                "format": "JSON",
                "catalogue": "DATA.GOV.HK",
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
            }
        ],
        {},
    )
    service.resources.catalogue.failure(
        "detail", "PARAMETER_ADAPTER_REQUIRED", "unsupported"
    )
    return service


@pytest.mark.parametrize("ident", [7, "0007"])
@pytest.mark.asyncio
async def test_native_id_binding_keeps_message_strings_timestamps_and_source_hash(
    service, monkeypatch, ident
):
    expected = native(ident)
    body = wrapped(expected)
    calls = []

    async def fetch(url, *args, **kwargs):
        calls.append(url)
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query(
        "detail", parameters={"notification-id": str(ident)}
    )
    assert calls == [detail.URL.replace("{notification-id}", str(ident))]
    assert result["data"]["items"] == [expected]
    assert result["meta"]["total"] == 1
    assert result["meta"]["version"] == hashlib.sha256(body).hexdigest()
    schema = result["schema"]
    assert schema["sourceContentHash"] == hashlib.sha256(body).hexdigest()
    assert schema["sourceFramingFullyConsumed"] is True
    assert schema["sourceResponseComplete"] is True
    assert schema["sourceNotificationId"] == ident
    assert schema["timestampUnitQualification"].startswith("unreviewed")
    assert (
        schema["messageContentQualification"]
        == "native_strings_not_rendered_or_followed"
    )


@pytest.mark.asyncio
async def test_mismatched_response_id_is_not_accepted(service, monkeypatch):
    async def fetch(url, *args, **kwargs):
        return wrapped(native(8)), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError, match="differs from the requested"):
        await service.resources.query("detail", parameters={"notification-id": "7"})


@pytest.mark.parametrize("parameters", [None, {}, {"notification-id": ""}, {"id": "7"}])
@pytest.mark.asyncio
async def test_missing_or_wrong_parameter_never_fetches(
    service, monkeypatch, parameters
):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Invalid parameters must fail before source access")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    with pytest.raises(DomainError):
        await service.resources.query("detail", parameters=parameters)


@pytest.mark.parametrize(
    "body",
    [
        b"Other({});",
        b"NotiDetail({});alert(1);",
        b"NotiDetail([]);",
        b'NotiDetail({"error":"unavailable"});',
        b'NotiDetail({"id":1,"id":2});',
        b'NotiDetail({"id":NaN});',
        b'NotiDetail({"id":1,});',
    ],
)
def test_malformed_or_executable_framing_is_held(body):
    with pytest.raises((DomainError, ValueError)):
        detail.read(body)


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "unreviewed"},
        {"id": True},
        {"msg_en": {}},
        {"schedule_ts": "1793920945000"},
        {"exp_ts": None},
    ],
)
def test_shape_and_native_types_are_not_coerced(change):
    with pytest.raises(DomainError):
        detail.read(wrapped({**native(), **change}))


@pytest.mark.parametrize(
    "selectors", [{"record_path": "msg_en"}, {"sheet": "1"}, {"layer": 0}]
)
def test_other_selectors_do_not_reinterpret_message_content(selectors):
    with pytest.raises(DomainError) as exc:
        detail.read(wrapped(native()), **selectors)
    assert exc.value.code == "INVALID_QUERY"


def test_exact_profile_parameter_name_and_encoded_path():
    assert source_parameters(detail.URL) == ["notification-id"]
    url = template_url(detail.URL, {"notification-id": "a/b?x=1#fragment"})
    assert url.endswith("a%2Fb%3Fx%3D1%23fragment")
    assert (
        request_requirements(detail.URL)["sourceSpecificationUrl"] == detail.DICTIONARY
    )
    resource = {"datasetId": detail.DATASET, "url": detail.URL, "format": "JSON"}
    assert read(resource, wrapped(native()))[0] == [native()]
    assert read({**resource, "datasetId": "other"}, wrapped(native())) is None
    assert read({**resource, "url": detail.URL + "/other"}, wrapped(native())) is None
