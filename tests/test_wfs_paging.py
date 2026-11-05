"""Paged WFS retains its native identity, CRS, raw attributes and scan bounds."""

import json

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.wfs_paging import read_pages, MAX_BYTES


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken",
    [
        None,
        "alias",
        "alias_ambiguous",
        "adaptive",
        "provider_denied",
        "oid_type",
        "repeated",
        "metadata",
        "changed_count",
        "no_oid",
        "empty",
        "bytes",
    ],
)
async def test_sorted_native_identity_count_reconciliation_and_cleanup(
    tmp_path, monkeypatch, broken
):
    import mcp_open_data_hk.wfs_paging as paging

    monkeypatch.setattr(paging.tempfile, "tempdir", str(tmp_path))
    if broken == "bytes":
        monkeypatch.setattr(paging, "MAX_BYTES", 20)
    calls = []

    async def read(url, params):
        calls.append(params)
        offset = params["startIndex"]
        assert "sortBy" not in params
        if broken == "adaptive" and len(calls) == 2:
            raise DomainError("SOURCE_TOO_LARGE", "page too large", 422)
        if broken == "provider_denied" and len(calls) == 2:
            raise DomainError("ACCESS_RESTRICTED", "source denied", 502)
        ids = (
            [1]
            if len(calls) == 1
            else [1, 2] if offset == 0 else [3, 4] if offset == 2 else [5]
        )
        if broken == "repeated" and offset:
            ids = [1, 2]
        if broken == "empty" and offset:
            ids = []
        value = {
            "fields": [
                {
                    "name": "OID",
                    "type": (
                        "esriFieldTypeInteger"
                        if broken == "no_oid"
                        else "esriFieldTypeOID"
                    ),
                }
            ],
            "spatialReference": {
                "wkid": 4326 if broken == "metadata" and offset else 2326
            },
            "geometryType": "esriGeometryPoint",
            "features": [
                {
                    "attributes": {"OID": n, "sourceCode": "0001"},
                    "geometry": {"x": 800000 + n, "y": 800000},
                }
                for n in ids
            ],
        }
        if broken in {"alias", "alias_ambiguous"}:
            value["fields"][0]["alias"] = "FID"
            value["fieldAliases"] = {"OID": "FID"}
            for row in value["features"]:
                row["attributes"]["FID"] = row["attributes"].pop("OID")
            if broken == "alias_ambiguous":
                value["fields"].append(
                    {"name": "another", "alias": "FID", "type": "esriFieldTypeInteger"}
                )
        if broken == "oid_type" and len(calls) > 1:
            value["features"][0]["attributes"]["OID"] = True
        return value, json.dumps(value).encode(), {}, url

    async def hits():
        return 6 if broken == "changed_count" else 5

    if broken not in {None, "alias", "adaptive"}:
        with pytest.raises(DomainError):
            await read_pages(
                "https://example.gov.hk/wfs",
                "source:features",
                5,
                "ESRIGEOJSON",
                read,
                hits,
            )
        assert list(tmp_path.glob("mcp-hk-wfs-*.json")) == []
        if broken == "provider_denied":
            assert len(calls) == 2
    else:
        path, _, _, extra = await read_pages(
            "https://example.gov.hk/wfs",
            "source:features",
            5,
            "ESRIGEOJSON",
            read,
            hits,
        )
        try:
            rows = json.loads(path.read_bytes())
            key = "FID" if broken == "alias" else "OID"
            assert [r["attributes"][key] for r in rows] == [1, 2, 3, 4, 5]
            assert all(r["attributes"]["sourceCode"] == "0001" for r in rows)
            assert extra["coordinateReferenceSystem"] == {"wkid": 2326}
            assert extra["representationFormat"] == "JSON"
            assert extra["countEvidence"]["distinctObservedOids"] == 5
            assert len(calls) == (5 if broken == "adaptive" else 4)
            assert MAX_BYTES == 128_000_000
        finally:
            path.unlink()
