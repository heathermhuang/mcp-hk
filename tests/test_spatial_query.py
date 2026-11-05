"""Reviewed source identities, independent point bindings and honest row counts."""

import copy
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.review_config import SOURCE_REVIEW
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.spatial_profiles import profiles, fingerprint, profile_for
from mcp_open_data_hk.storage import Store


@pytest.fixture(params=["school", "clinic"])
def point_service(request, tmp_path, monkeypatch):
    profile = next(p for p in profiles() if p["entityKind"] == request.param)
    resource = {
        "id": profile["resourceId"],
        "datasetId": profile["datasetId"],
        "format": profile["format"],
        "url": "https://"
        + profile["host"]
        + profile["path"]
        + (
            "?" + "&".join(k + "=" + v[0] for k, v in profile["query"].items())
            if profile["query"]
            else ""
        ),
        "sourceUrl": profile["evidence"][0],
        "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
        "catalogue": "DATA.GOV.HK",
    }
    service = Service(Store(str(tmp_path / "points.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": profile["datasetId"],
                "title": "Reviewed source",
                "provider": "Example",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        [resource],
        {},
    )
    rows = []
    for i, (lat, lon) in enumerate(
        [
            (22.28, 114.15),
            (22.5, 114.3),
            (22.28, 114.15),
            ("bad", 114.15),
            (22.281, 114.15),
        ]
    ):
        if request.param == "school":
            row = {
                "SCHOOL NO.": (
                    "000000000001" if i in {0, 2} else "000000000002" if i < 4 else ""
                ),
                "ENGLISH NAME": "School A" if i in {0, 2} else "School B",
                "中文名稱": "學校A" if i in {0, 2} else "學校B",
                "SESSION": "WHOLE DAY",
                "SCHOOL LEVEL": "PRIMARY",
                "LATITUDE": str(lat),
                "LONGITUDE": str(lon),
                "緯度": str(lat),
                "經度": str(lon),
            }
        else:
            row = {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "OBJECTID": 1 if i in {0, 2} else 2 if i < 4 else None,
                    "NameEN": "Clinic A" if i in {0, 2} else "Clinic B",
                    "NameTC": "診所A" if i in {0, 2} else "診所B",
                    "CategoryEN": "SYNTHETIC TEST SERVICE",
                    "DatasetEN": "Clinics / Health Centres under the Department of Health",
                },
            }
        rows.append(row)
    state = {"rows": rows, "crs": None, "name": "CLINIC_HEALTH"}

    async def fetch(url, headers=None, **kwargs):
        if request.param == "school":
            output = io.StringIO()
            writer = csv.DictWriter(output, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(state["rows"])
            body = output.getvalue().encode()
        else:
            body = json.dumps(
                {
                    "type": "FeatureCollection",
                    "name": state["name"],
                    "features": state["rows"],
                    **({"crs": state["crs"]} if state["crs"] else {}),
                }
            ).encode()
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    return service, profile, resource, state


@pytest.mark.asyncio
async def test_shared_engine_preserves_raw_rows_duplicates_totals_and_versions(
    point_service,
):
    service, profile, resource, state = point_service
    key = resource["id"]
    nearby = {"lat": 22.28, "lon": 114.15, "radiusM": 2000}
    first = await service.resources.query(key, nearby=nearby, limit=1)
    assert first["meta"]["total"] == 3
    assert first["meta"]["nearby"]["matches"] == [{"sourceOrdinal": 0, "distanceM": 0}]
    assert first["schema"]["semanticBinding"]["coverage"]["sourceRows"] == 5
    coverage = first["meta"]["nearby"]["coverage"]
    assert coverage["invalidCoordinates"] == 1
    assert (
        coverage["duplicateSourceIdentifierRows"] == 2
    )  # Both nonunique source IDs remain source evidence.
    assert coverage["missingSourceIdentifiers"] == 1
    assert first["meta"]["nearby"]["uniqueFacilityCount"] is None
    second = await service.resources.query(
        key, nearby=nearby, limit=1, offset=1, version=first["meta"]["version"]
    )
    assert second["data"]["items"] == first["data"]["items"]
    assert second["meta"]["nearby"]["matches"][0]["sourceOrdinal"] == 2
    chinese = "中文名稱" if profile["entityKind"] == "school" else "properties.NameTC"
    term = "學校A" if profile["entityKind"] == "school" else "診所A"
    assert (
        await service.resources.query(key, nearby=nearby, contains={chinese: term})
    )["meta"]["total"] == 2
    assert (
        await service.resources.query(
            key, nearby={"lat": 22.28, "lon": 114.15, "radiusM": 1}
        )
    )["meta"]["total"] == 2
    assert (
        service.resources.catalogue.capability(key)["operations"]["nearby"]["state"]
        == "available"
    )
    result = service.resources.catalogue.search(
        capability="nearby", entity_kind=profile["entityKind"]
    )
    assert result["total"] == 1
    assert (
        service.resources.catalogue.search(
            "學校" if profile["entityKind"] == "school" else "診所", capability="nearby"
        )["total"]
        == 1
    )
    assert result["items"][0]["capabilities"]["entityKind"] == profile["entityKind"]
    assert result["items"][0]["capabilities"]["nearby"]["state"] == "available"
    assert service.resources.catalogue.search(entity_kind="unqualified")["total"] == 0
    with pytest.raises(DomainError, match="RESOURCE_VERSION_REQUIRED"):
        await service.resources.query(key, nearby=nearby, offset=1)
    with pytest.raises(DomainError, match="INVALID_QUERY"):
        await service.resources.query(
            key, nearby=nearby, order_by=[{"field": chinese, "kind": "string"}]
        )


@pytest.mark.asyncio
async def test_http_mcp_point_contracts_and_projection_preserve_source_values(
    point_service,
):
    service, profile, resource, state = point_service
    field = "SCHOOL NO." if profile["entityKind"] == "school" else "properties.OBJECTID"
    query = {
        "nearby": {"lat": 22.28, "lon": 114.15, "radiusM": 2000},
        "fields": [field],
        "limit": 1,
    }
    with TestClient(create_app(service)) as client:
        response = client.post(
            "/api/v1/resources/" + resource["id"] + "/query", json=query
        )
        assert response.status_code == 200
        expected = response.json()
        discovery = client.get(
            "/api/v1/catalogue/datasets",
            params={"capability": "nearby", "entityKind": profile["entityKind"]},
        )
        assert discovery.status_code == 200
        discovery = discovery.json()
    async with Client(create_app(service).state.mcp) as client:
        result = await client.call_tool(
            "hk_resource_query", {"resourceId": resource["id"], **query}
        )
        payload = json.loads(result.content[0].text)
        found = await client.call_tool(
            "hk_catalogue_search",
            {"capability": "nearby", "entityKind": profile["entityKind"]},
        )
        assert json.loads(found.content[0].text) == discovery
    assert payload["data"] == expected["data"]
    assert payload["meta"]["nearby"] == expected["meta"]["nearby"]
    assert payload["data"]["items"][0][field] == (
        "000000000001" if profile["entityKind"] == "school" else 1
    )


@pytest.mark.asyncio
async def test_context_or_coordinate_contract_drift_holds_nearby_without_erasing_records(
    point_service,
):
    service, profile, resource, state = point_service
    await service.resources.schema(resource["id"])
    if profile["entityKind"] == "school":
        state["rows"][0]["緯度"] = "22.3"
        reason = "bilingual_coordinate_conflict"
    else:
        state["name"] = "ANOTHER_COLLECTION"
        reason = "binding_source_context_changed"
    token = SOURCE_REVIEW.set(True)
    try:
        response = await service.resources.schema(resource["id"])
    finally:
        SOURCE_REVIEW.reset(token)
    assert response["schema"]["semanticBinding"]["state"] == "held"
    assert response["schema"]["semanticBinding"]["reason"] == reason
    assert service.resources.catalogue.check(resource["id"])["status"] == "queryable"
    assert (
        service.resources.catalogue.capability(resource["id"])["operations"]["nearby"][
            "state"
        ]
        == "held"
    )
    with pytest.raises(DomainError, match="NEARBY_BINDING_REQUIRED"):
        await service.resources.query(
            resource["id"], nearby={"lat": 22.28, "lon": 114.15, "radiusM": 2000}
        )


def test_source_identity_is_exact_and_profile_revision_invalidates_receipts(
    point_service,
):
    _, profile, resource, _ = point_service
    assert profile_for(resource) == profile
    for key, value in [
        ("url", "https://other.gov.hk/data"),
        ("datasetId", "other"),
        ("id", "other"),
    ]:
        changed = {**resource, key: value}
        assert profile_for(changed) is None
    changed = copy.deepcopy(profile)
    changed["qualifiedDate"] = "later"
    assert fingerprint(changed) != fingerprint(profile)


@pytest.mark.asyncio
async def test_incompatible_selectors_fail_before_network_and_leave_receipts(
    point_service, monkeypatch
):
    service, _, resource, _ = point_service
    calls = []

    async def fail(*args, **kwargs):
        calls.append(True)
        raise AssertionError("no provider request")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fail)
    with pytest.raises(DomainError, match="INVALID_QUERY"):
        await service.resources.query(resource["id"], sheet="invented-default")
    assert not calls
    assert service.resources.catalogue.check(resource["id"]) == {}


@pytest.mark.asyncio
async def test_explicit_wrong_crs_and_new_profile_revision_cannot_inherit_acceptance(
    point_service, monkeypatch
):
    from mcp_open_data_hk.spatial_query import qualify
    from mcp_open_data_hk import spatial_profiles

    service, profile, resource, state = point_service
    response = await service.resources.schema(resource["id"])
    changed = copy.deepcopy(response["schema"])
    changed["sourceCrs"] = {"type": "name", "properties": {"name": "EPSG:2326"}}
    qualify(resource, state["rows"], changed)
    assert changed["semanticBinding"]["state"] == "held"
    assert changed["semanticBinding"]["reason"] == "binding_crs_changed"
    revised = copy.deepcopy(profile)
    revised["qualifiedDate"] = "new-review"
    monkeypatch.setattr(spatial_profiles, "profiles", lambda: (revised,))
    assert (
        service.resources.catalogue.capability(resource["id"])["operations"]["nearby"][
            "state"
        ]
        == "requires_binding"
    )


@pytest.mark.asyncio
async def test_nearby_source_failure_retains_records_but_cannot_be_an_empty_spatial_success(
    point_service, monkeypatch
):
    service, profile, resource, state = point_service
    await service.resources.schema(resource["id"])

    async def failing(*args, **kwargs):
        raise DomainError("SOURCE_UNAVAILABLE", "Provider offline", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", failing)
    token = SOURCE_REVIEW.set(True)
    try:
        prior = await service.resources.schema(resource["id"])
    finally:
        SOURCE_REVIEW.reset(token)
    assert prior["warnings"][0]["code"] == "STALE_ACCEPTED_RESOURCE"
    with pytest.raises(DomainError, match="SOURCE_UNAVAILABLE"):
        await service.resources.query(
            resource["id"], nearby={"lat": 22.28, "lon": 114.15, "radiusM": 2000}
        )
    assert (await service.resources.query(resource["id"]))["meta"]["total"] == 5


@pytest.mark.asyncio
async def test_checkpoint_restore_preserves_bindings_options_generations_and_legacy_reads(
    point_service, tmp_path
):
    from mcp_open_data_hk.operations import checkpoint, restore
    from mcp_open_data_hk.sources import DISTRICTS

    service, profile, resource, state = point_service
    await service.resources.schema(resource["id"])
    catalogue = service.resources.catalogue
    first_generation = catalogue.head()
    dataset = catalogue.dataset(profile["datasetId"])
    dataset["title"] = "Updated metadata"
    catalogue.publish([dataset], [resource], {})
    assert catalogue.head() != first_generation
    catalogue.record_options(
        resource["id"], [{"kind": "record_path", "options": [], "totalOptions": 0}]
    )
    service.store.publish(
        "restaurants", [{"id": "test", "latitude": 22.3, "longitude": 114.1}], None
    )
    service.store.publish(
        "population",
        [{"id": d["id"] + ":2024", "districtId": d["id"]} for d in DISTRICTS],
        None,
    )
    packed, digest = checkpoint(service.store.path)
    target = tmp_path / "isolated-restored" / "db.sqlite3"
    restore(packed.read_bytes(), digest, str(target))
    restored = Service(Store(str(target)))
    assert restored.status()["ready"]
    with restored.store.connect() as db:
        assert db.execute("SELECT count(*) FROM inventories").fetchone()[0] == 2
    assert restored.resources.catalogue.selection_options(resource["id"])
    assert (
        restored.resources.catalogue.capability(resource["id"])["operations"]["nearby"][
            "state"
        ]
        == "available"
    )
    legacy = await restored.resources.query(resource["id"], limit=1)
    assert legacy["meta"]["total"] == 5
    nearby = await restored.resources.query(
        resource["id"], nearby={"lat": 22.28, "lon": 114.15, "radiusM": 2000}, limit=1
    )
    assert nearby["meta"]["total"] == 3
