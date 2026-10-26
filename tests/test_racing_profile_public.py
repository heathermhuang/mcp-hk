"""Independent recovery, policy, source budget and shared public contracts."""

import hashlib
import io
import json
import zipfile

import httpx
import pytest
from fastmcp import Client

from test_racing_public import service as base_service
from test_racing_profiles import page
from test_racing_prototype import page as results_page
from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.curated.racing.policy import RacingRejected, checksum, MODES
from mcp_open_data_hk.curated.racing.profiles import parse_profile, profile_url
from mcp_open_data_hk.curated.racing.prototype_store import (
    PrototypeStore,
    PilotCollector,
)
from mcp_open_data_hk.operations import checkpoint, restore
from mcp_open_data_hk.racing_store import RacingStore

service = base_service


def policy():
    return {
        "schema": "racing-policy-v1",
        "source": "hkjc",
        "purpose": "read_only_racing_facts",
        "state": "active",
        "qualifiedAt": "2026-10-25T00:00:00Z",
        "recheckAt": "2026-11-25T00:00:00Z",
        "families": {
            "profiles": {
                "modes": {mode: "allowed" for mode in MODES},
                "evidenceRef": "invented test basis",
                "evidenceSha256": "a" * 64,
                "fields": ["professional_attributes", "displayed_form_history"],
                "routes": [
                    f"https://racing.hkjc.com/{lang}/local/information/horse"
                    for lang in ("en-us", "zh-hk")
                ],
                "retentionSeconds": 365 * 86400,
                "rawRetentionSeconds": 0,
                "minIntervalSeconds": 1,
            }
        },
    }


def html(zh=False, rating="60"):
    text = page(changed={"Current Rating": rating})
    # A second independently specified displayed form row permits real pagination.
    row = text[text.index("<tr><td><a href=") : text.index("</tr></table></html>") + 5]
    text = text.replace(
        "</tr></table></html>",
        "</tr>"
        + row.replace("raceno=1", "raceno=2").replace(">119<", ">120<")
        + "</table></html>",
    )
    if zh:
        for left, right in [
            ("Country of Origin / Age", "出生地 / 馬齡"),
            ("Colour / Sex", "毛色 / 性別"),
            ("No. of 1-2-3-Starts*", "冠-亞-季-總出賽次數*"),
            ("Current Rating", "現時評分"),
            ("Total Stakes*", "總獎金*"),
            ("Import Date", "進口日期"),
        ]:
            text = text.replace(left, right)
    return text


def observations(rating="60", observed="2026-10-26T00:00:00Z"):
    values = []
    captures = []
    for zh, lang in ((False, "en-us"), (True, "zh-hk")):
        body = html(zh, rating).encode()
        url = profile_url("horse", "HK_2026_K001", lang)
        values.append(parse_profile(body.decode(), url, observed))
        captures.append(
            {
                "url": url,
                "observed": values[-1]["observedAt"],
                "sha256": hashlib.sha256(body).hexdigest(),
                "bytes": len(body),
            }
        )
    return values, captures


def accept_profile(service, tmp_path, candidate):
    packed, digest = checkpoint(service.store.path)
    target = tmp_path / ("restore-" + candidate["version"][-8:] + ".sqlite3")
    restore(packed.read_bytes(), digest, str(target))
    return service.racing.store.accept_restored(
        RacingStore(target), candidate["version"], digest
    )


@pytest.fixture
def prepared(service, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mcp_open_data_hk.curated.racing.prototype_store.time.sleep", lambda _: None
    )

    def handler(request):
        from urllib.parse import parse_qs

        n = int(parse_qs(request.url.query.decode()).get("RaceNo", ["1"])[0])
        text = results_page(n, zh="/zh-hk/" in request.url.path).replace(
            "HK_2024_TEST1", "HK_2026_K001"
        )
        return httpx.Response(200, text=text, headers={"content-type": "text/html"})

    private = PrototypeStore(tmp_path / "pilot.sqlite3")
    snapshot = PilotCollector(
        private, httpx.Client(transport=httpx.MockTransport(handler))
    ).collect("2026-10-21", "HV")
    with private.connect() as db:
        bundle = {
            "snapshot": snapshot,
            "pages": [dict(r) for r in db.execute("SELECT * FROM racing_pages")],
            "attempts": [dict(r) for r in db.execute("SELECT * FROM racing_attempts")],
        }
    candidate = service.racing.store.import_bundle(bundle)
    accept_profile(service, tmp_path, candidate)
    record = policy()
    service.racing.store.profiles.install_policy(record, checksum(record))
    return service


def test_unknown_policy_and_unaccepted_cohort_never_stage(service):
    with pytest.raises(RacingRejected, match="MODE_UNQUALIFIED"):
        service.racing.store.profiles.stage(*observations())
    record = policy()
    service.racing.store.profiles.install_policy(record, checksum(record))
    with pytest.raises(RacingRejected, match="OUTSIDE_ACCEPTED_COHORT"):
        service.racing.store.profiles.stage(*observations())


def test_stage_hidden_exact_restore_publish_and_hash_corruption(prepared, tmp_path):
    p = prepared.racing.store.profiles
    candidate = p.stage(*observations())
    assert p.pending() == candidate["version"]
    with pytest.raises(RacingRejected, match="NOT_FOUND"):
        p.read("horse", "HK_2026_K001")
    with pytest.raises(RacingRejected, match="RESTORE_MISMATCH"):
        p.accept(p, candidate["version"], "a" * 64)
    proof = accept_profile(prepared, tmp_path, candidate)
    assert len(proof["sourceTables"]) == 15
    data = p.read("horse", "HK_2026_K001")
    assert data["data"]["attributes"]["rating"]["en"]["value"] == "60"
    assert p.pending() is None
    assert p.stage(*observations())["state"] == "unchanged"
    with p.store.connect() as db:
        db.execute(
            "UPDATE racing_profile_versions SET payload=replace(payload,'Fixture Horse','Tampered Horse')"
        )
    with pytest.raises(RacingRejected, match="CONTENT_MISMATCH"):
        p.read("horse", "HK_2026_K001")


def test_changed_control_restore_and_failed_refresh_preserve_last_good(
    prepared, tmp_path
):
    p = prepared.racing.store.profiles
    old = p.stage(*observations())
    accept_profile(prepared, tmp_path, old)
    newer = p.stage(*observations("61", "2026-10-26T01:00:00Z"))
    packed, digest = checkpoint(prepared.store.path)
    target = tmp_path / "changed.sqlite3"
    restore(packed.read_bytes(), digest, str(target))
    other = RacingStore(target)
    with other.connect() as db:
        db.execute("UPDATE racing_profile_queue SET next_due=next_due+1")
    with pytest.raises(RacingRejected, match="RESTORE_MISMATCH"):
        p.accept(other.profiles, newer["version"], digest)
    assert p.read("horse", "HK_2026_K001")["meta"]["version"] == old["version"]
    with pytest.raises(RacingRejected, match="OBSERVATION_REGRESSION"):
        p.stage(*observations("59", "2026-10-25T00:00:00Z"))


def test_policy_revoked_after_stage_blocks_publication_and_read(prepared, tmp_path):
    p = prepared.racing.store.profiles
    candidate = p.stage(*observations())
    accept_profile(prepared, tmp_path, candidate)
    record = policy()
    record["state"] = "revoked"
    p.install_policy(record, checksum(record))
    with pytest.raises(RacingRejected, match="POLICY_INACTIVE"):
        p.read("horse", "HK_2026_K001")
    assert not p.scheduled()
    assert not p.status()["available"]
    with p.store.connect() as db:
        assert (
            db.execute("SELECT count(*) FROM racing_profile_current").fetchone()[0] == 1
        )


def test_signed_cursor_binds_identity_language_version_and_zip_page(prepared, tmp_path):
    p = prepared.racing.store.profiles
    candidate = p.stage(*observations())
    accept_profile(prepared, tmp_path, candidate)
    first = p.history("horse", "HK_2026_K001", limit=1)
    cursor = first["meta"]["nextCursor"]
    assert cursor
    second = p.history("horse", "HK_2026_K001", cursor=cursor, limit=1)
    assert first["data"]["items"][0]["race"]["raceNumber"] == 1
    assert second["data"]["items"][0]["race"]["raceNumber"] == 2
    for params in (
        {"cursor": cursor + "x"},
        {"cursor": cursor, "language": "zhHant"},
        {"cursor": "x" * 2049},
        {"cursor": "%"},
    ):
        with pytest.raises(RacingRejected, match="INVALID_PROFILE_CURSOR"):
            p.history("horse", "HK_2026_K001", **params)
    archive = zipfile.ZipFile(
        io.BytesIO(p.archive("horse", "HK_2026_K001", limit=1, cursor=cursor))
    )
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["historyRows"] == 1
    assert json.loads(archive.read("history.json")) == second
    for name, entry in manifest["files"].items():
        assert hashlib.sha256(archive.read(name)).hexdigest() == entry["sha256"]
        assert len(archive.read(name)) == entry["bytes"]
    assert b"private@example.invalid" not in archive.read("profile.json")


@pytest.mark.asyncio
async def test_rest_mcp_parity_and_disabled_discovery(prepared, tmp_path):
    p = prepared.racing.store.profiles
    app = create_app(prepared)
    async with Client(app.state.mcp) as mcp:
        assert "hk_racing_profile_observation" not in {
            t.name for t in await mcp.list_tools()
        }
        candidate = p.stage(*observations())
        accept_profile(prepared, tmp_path, candidate)
        assert "hk_racing_profile_observation" in {
            t.name for t in await mcp.list_tools()
        }
        tool = await mcp.call_tool(
            "hk_racing_profile_observation",
            {
                "kind": "horse",
                "sourceId": "HK_2026_K001",
                "version": candidate["version"],
            },
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="https://mcp.hk"
        ) as browser:
            response = await browser.get(
                "/api/v1/racing/profiles/horse/HK_2026_K001",
                params={"version": candidate["version"]},
            )
            assert response.status_code == 200
            assert response.json() == tool.data
            export = await browser.get(
                "/api/v1/racing/profiles/horse/HK_2026_K001/export",
                params={"version": candidate["version"]},
            )
            assert export.status_code == 200 and zipfile.is_zipfile(
                io.BytesIO(export.content)
            )


def test_bounded_source_steps_resume_second_language_without_duplicate_read(prepared):
    p = prepared.racing.store.profiles
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(
            200,
            text=html("/zh-hk/" in request.url.path),
            headers={"content-type": "text/html"},
        )

    with prepared.racing.store.connect() as db:
        db.execute(
            "UPDATE racing_profile_queue SET next_due=9999999999 WHERE kind!='horse'"
        )
    assert (
        p.collect(1, httpx.Client(transport=httpx.MockTransport(handler)))["state"]
        == "partial"
    )
    assert (
        p.collect(1, httpx.Client(transport=httpx.MockTransport(handler)))["state"]
        == "staged"
    )
    assert len(calls) == 2 and len(set(calls)) == 2


def test_no_extra_import_fields_even_with_recalculated_checksum(prepared):
    observed, captures = observations()
    observed[0]["biography"] = "not an allowed field"
    with pytest.raises(RacingRejected, match="FIELDS_UNQUALIFIED"):
        prepared.racing.store.profiles.stage(observed, captures)


def test_low_disk_retains_the_previous_profile_pointer(prepared, tmp_path, monkeypatch):
    p = prepared.racing.store.profiles
    old = p.stage(*observations())
    accept_profile(prepared, tmp_path, old)
    import shutil

    current = shutil.disk_usage(p.store.path.parent)
    monkeypatch.setattr(
        "mcp_open_data_hk.racing_profiles.shutil.disk_usage",
        lambda _: current._replace(free=0),
    )
    with pytest.raises(RacingRejected, match="GROWTH_CAPACITY_HOLD"):
        p.stage(*observations("61", "2026-10-26T01:00:00Z"))
    assert p.read("horse", "HK_2026_K001")["meta"]["version"] == old["version"]


@pytest.mark.parametrize(
    "free,allowed",
    [(1_399_999_999, False), (1_400_000_000, True), (8_000_000_000, True)],
)
def test_gateway_scratch_guard_fits_its_eight_gb_disk(
    prepared, monkeypatch, free, allowed
):
    import shutil
    from mcp_open_data_hk.racing_profiles import required_scratch_bytes

    current = shutil.disk_usage(prepared.racing.store.path.parent)
    monkeypatch.setattr(
        "mcp_open_data_hk.racing_profiles.shutil.disk_usage",
        lambda _: current._replace(free=free),
    )
    # 500 MB backup copy + 150 MB packed transfer + 750 MB isolated restore.
    assert required_scratch_bytes() == 1_400_000_000
    profiles = prepared.racing.store.profiles
    if allowed:
        assert profiles.stage(*observations())["state"] == "staged"
        assert profiles.status()["accepted"] == 0
    else:
        with pytest.raises(RacingRejected, match="GROWTH_CAPACITY_HOLD"):
            profiles.stage(*observations())
    assert profiles.status()["scratchCapacity"]["sufficient"] is allowed


def test_expired_policy_blocks_acceptance_and_export(prepared, tmp_path):
    p = prepared.racing.store.profiles
    candidate = p.stage(*observations())
    record = policy()
    record["recheckAt"] = "2026-10-26T00:00:00Z"
    p.install_policy(record, checksum(record))
    with pytest.raises(RacingRejected, match="POLICY_INACTIVE"):
        accept_profile(prepared, tmp_path, candidate)
    with pytest.raises(RacingRejected, match="POLICY_INACTIVE"):
        p.archive("horse", "HK_2026_K001")
    assert p.pending() == candidate["version"]


def test_earlier_replay_column_is_removed_without_new_observation_time(
    prepared, tmp_path
):
    observed, captures = observations()
    original = observed[1]
    original["formHistory"][0]["fields"]["賽事 重播"] = "replay excluded"
    original["factsSha256"] = checksum(
        {
            k: v
            for k, v in original.items()
            if k
            not in {"observedAt", "effectiveAt", "sourceUrl", "factsSha256", "coverage"}
        }
    )
    before = original["factsSha256"]
    p = prepared.racing.store.profiles
    candidate = p.stage(observed, captures)
    accept_profile(prepared, tmp_path, candidate)
    detail = p.read("horse", "HK_2026_K001")["data"]
    assert detail["inputFactsSha256"]["zh-hk"] == before
    assert detail["observations"]["zhHant"] == original["observedAt"]
    assert detail["rawParseTransformSha256"] is None
    assert "replay excluded" not in str(
        p.history("horse", "HK_2026_K001", language="zhHant")
    )


@pytest.mark.parametrize("raw", ["萬", "一萬萬", "十十", "二三百"])
def test_invalid_chinese_numerals_never_become_zero(raw):
    from mcp_open_data_hk.curated.racing.profiles import chinese_number

    with pytest.raises(RacingRejected):
        chinese_number(raw)
