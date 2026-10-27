"""Accepted observation history with real PG/restore; fabricated source only."""

from datetime import datetime, timezone

import httpx
import pytest

from test_sfc import fake_policy
from test_sfc_postgres import model as base_model, pytestmark as base_marks
from test_sfc_job_postgres import recovery
from sfc_support import source_page
from mcp_open_data_hk.curated.read import ReadError
from mcp_open_data_hk.curated.sfc.public_register import Collector, ROUTE

model = base_model
pytestmark = base_marks


def test_history_pins_inventory_and_binds_cursor_to_ce_mode_and_retention(
    model, tmp_path
):
    state, original, reader, _ = model
    policy = fake_policy(route=ROUTE, modes={**original.modes, "history": "allowed"})
    state.activate(policy, policy.sha256)
    reader.policy = policy
    collector = Collector(
        state,
        policy,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, content=source_page(), headers={"Content-Type": "text/html"}
            )
        ),
    )
    previous = None
    versions = []

    def publish():
        nonlocal previous
        result = collector.collect(datetime.now(timezone.utc), ["ZZZ001"])
        version = result["version"]
        with recovery(state, tmp_path)(version, "candidate") as (target, artifact, sha):
            state.qualify_restore(version, target, artifact, sha)
        state.publish(version, previous)
        versions.append(version)
        previous = version
        return version

    publish()
    anchor = publish()
    first = reader.history("zzz001", limit=1)
    assert first["version"] == anchor and first["data"][0]["version"] == anchor
    assert first["nextCursor"]
    assert first["provenance"]["completeRegulatoryHistory"] is False
    token = reader.reader.unseal(
        first["nextCursor"],
        "sfc_history",
        {"ce": "ZZZ001", "mode": "rest", "policy": policy.sha256, "limit": 1},
    )
    assert token["expires"] <= policy.recheckAt.timestamp()
    newest = publish()
    second = reader.history("ZZZ001", limit=1, cursor=first["nextCursor"])
    assert second["version"] == anchor
    assert [row["version"] for row in second["data"]] == versions[:1]
    assert second["nextCursor"] is None and newest not in {
        r["version"] for r in second["data"]
    }
    for changes in (
        {"ce": "ZZZ002"},
        {"mode": "mcp"},
        {"limit": 2},
        {"version": newest},
    ):
        with pytest.raises(ReadError, match="Cursor|cursor|version"):
            reader.history(
                **{"ce": "ZZZ001", "limit": 1, "cursor": first["nextCursor"], **changes}
            )
    with state.connection() as conn:
        conn.execute(
            "UPDATE curated_sfc.versions SET expires_at=now()-interval '1 second' WHERE version=%s",
            (anchor,),
        )
    with pytest.raises(ReadError, match="retention expired"):
        reader.history("ZZZ001", limit=1, cursor=first["nextCursor"])


def test_history_requires_its_own_policy_and_accepted_real_capture(model):
    _, _, reader, _ = model
    with pytest.raises(ReadError, match="not qualified"):
        reader.history("ZZZ001")
