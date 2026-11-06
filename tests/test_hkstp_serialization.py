"""The exact recruitment endpoint sometimes JSON-encodes its record array twice."""

import hashlib
import json

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_serializations import HKSTP_RECRUITMENT, read
from mcp_open_data_hk.resources import SOURCE_REVIEW
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "jobs", "title": "Recruitment", "provider": "HKSTP"}],
        [
            {
                "id": "jobs",
                "datasetId": "jobs",
                "format": "JSON",
                "url": HKSTP_RECRUITMENT,
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_encoded_array_revalidates_accepted_fields_without_normalizing_values(
    service, monkeypatch
):
    rows = [
        {
            "Job_Position": "原文",
            "Job_Ref_No": "007",
            "Post_End_Date": "Original date",
            "Salary": "Negotiable",
        }
    ]
    body = json.dumps(rows, ensure_ascii=False).encode()

    async def fetch(url, *args, **kwargs):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    first = await service.resources.query("jobs")
    body = json.dumps(body.decode(), ensure_ascii=False).encode()
    token = SOURCE_REVIEW.set(True)
    try:
        result = await service.resources.query("jobs", require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert result["data"]["items"] == first["data"]["items"] == rows
    assert result["meta"]["version"] == hashlib.sha256(body).hexdigest()
    assert result["schema"]["sourceContentHash"] == hashlib.sha256(body).hexdigest()
    assert result["schema"]["sourceResponseBytes"] == len(body)
    assert result["schema"]["sourceFramingFullyConsumed"] is True
    assert result["schema"]["observedSerialization"] == (
        "hkstp_recruitment_array_in_json_string"
    )


@pytest.mark.parametrize(
    "inner",
    [
        '"not an array"',
        '{"error":"Unavailable"}',
        "[1]",
        '[{"id":1,"id":2}]',
        '[{"id":NaN}]',
        '[{"id":1}] trailing',
        '[{"id":1}',
    ],
)
@pytest.mark.asyncio
async def test_malformed_or_nonrecord_string_is_never_accepted(
    service, monkeypatch, inner
):
    async def fetch(url, *args, **kwargs):
        return json.dumps(inner).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query("jobs")
    assert service.resources.catalogue.check("jobs")["status"] != "queryable"


def test_unrelated_url_and_ordinary_array_keep_the_ordinary_reader():
    assert (
        read(
            {"url": HKSTP_RECRUITMENT + "?other=1", "format": "JSON"},
            b'"[{\\"id\\":1}]"',
        )
        is None
    )
    assert read({"url": HKSTP_RECRUITMENT, "format": "JSON"}, b'[{"id":1}]') is None


def test_explicit_empty_array_and_existing_row_limit(monkeypatch):
    resource = {"url": HKSTP_RECRUITMENT, "format": "JSON"}
    assert read(resource, b'"[]"')[0] == []
    monkeypatch.setattr("mcp_open_data_hk.resource_formats.MAX_ROWS", 1)
    with pytest.raises(DomainError, match="SOURCE_TOO_LARGE"):
        read(resource, json.dumps('[{"id":1},{"id":2}]').encode())


def test_workbook_selectors_cannot_be_applied_to_the_encoded_array():
    with pytest.raises(DomainError, match="INVALID_QUERY"):
        read({"url": HKSTP_RECRUITMENT, "format": "JSON"}, b'"[]"', sheet="Sheet1")
