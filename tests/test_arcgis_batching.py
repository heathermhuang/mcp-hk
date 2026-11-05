"""Fewer bounded requests must never weaken complete-ID acceptance."""

import json

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resources import arcgis, params_url


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode",
    [
        "normal",
        "small_body",
        "transfer_limit",
        "denied",
        "wrong_ids",
        "boolean_id",
        "final_duplicate",
    ],
)
async def test_provider_bounded_batches_exact_identity_and_no_partial_acceptance(
    monkeypatch, mode
):
    ids = list(range(1000000000, 1000000600))
    calls, id_reads = [], []

    async def read(url, params=None):
        if not url.endswith("query"):
            value = {"objectIdField": "OID", "maxRecordCount": 2000}
        elif params.get("returnIdsOnly"):
            id_reads.append(1)
            value = {
                "objectIds": (
                    ids + [ids[0]]
                    if mode == "final_duplicate" and len(id_reads) == 2
                    else ids
                )
            }
        else:
            selected = [int(x) for x in params["objectIds"].split(",")]
            calls.append(selected)
            assert len(params_url(url, params)) <= 2000
            assert len(selected) <= 2000
            if mode == "denied":
                raise DomainError("ACCESS_RESTRICTED", "provider denied", 502)
            if mode == "small_body" and len(selected) > 60:
                raise DomainError("SOURCE_TOO_LARGE", "oversized page", 422)
            value = {
                "features": [
                    {"attributes": {"OID": x, "code": "0001"}} for x in selected
                ]
            }
            if mode == "transfer_limit" and len(selected) > 60:
                value = {
                    "features": value["features"][:1],
                    "exceededTransferLimit": True,
                }
            if mode == "wrong_ids":
                value["features"][0]["attributes"]["OID"] = -1
            if mode == "boolean_id":
                value["features"][0]["attributes"]["OID"] = True
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    if mode in {"denied", "wrong_ids", "boolean_id", "final_duplicate"}:
        with pytest.raises(DomainError):
            await arcgis("https://example.gov.hk/FeatureServer/0", None)
        if mode == "denied":
            assert len(calls) == 1
    else:
        body, _, _, extra = await arcgis("https://example.gov.hk/FeatureServer/0", None)
        rows = json.loads(body)
        assert [r["attributes"]["OID"] for r in rows] == ids
        assert all(r["attributes"]["code"] == "0001" for r in rows)
        assert extra["sourceBatchRequests"] == len(calls)
        assert extra["sourceMatched"] == 600
        assert len(id_reads) == 2
        if mode == "normal":
            assert len(calls) < 6
            assert max(map(len, calls)) > 100
