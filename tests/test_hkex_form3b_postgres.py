"""Actual PostgreSQL storage/physical restore; invented form values only."""

import hashlib
import time
from datetime import datetime, timezone

import httpx
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from hkex_form3b_support import CONTEXT, SERIAL, document
from hkex_support import SyntheticAdapter, policy, window
from test_hkex_postgres import (
    model as base_model,
    qualify,
    pytestmark as inherited_marks,
)
from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.hkex.collect import Collector
from mcp_open_data_hk.curated.hkex.contracts import digest
from mcp_open_data_hk.curated.hkex.form3b import (
    Form3BAdapter,
    ORIGIN,
    PATH,
    parse_form3b,
)
from mcp_open_data_hk.curated.hkex.store import Store, activate_policy, migrate

model = base_model
pytestmark = inherited_marks


def install_policy(model, **updates):
    parsed = parse_form3b(document(), **CONTEXT)
    p = policy(codes=parsed.code_labels, **updates)
    activate_policy(model["owner"], p.model_dump(mode="json"), digest(p))
    model["store"] = Store(model["owner"], digest(p))
    return parsed


def test_all_form_facts_survive_independent_physical_restore_and_select_only_serving(
    model, tmp_path
):
    parsed = install_policy(model)
    row = parsed.filing
    scope = window(issuer_id=CONTEXT["issuer_id"], start="2026-10-20", end="2026-10-27")

    def inventory(kind, key, doc):
        if kind == "inventory":
            return dict(
                doc,
                issuer_name=row.issuer_name,
                securities=[row.securities[0].model_dump(mode="json")],
            )
        return doc

    adapter = SyntheticAdapter([row], scope, mutate=inventory, after=model["paced"])
    result = Collector(model["store"], adapter).run(scope, datetime.now(timezone.utc))
    assert result["state"] == "validated", result
    migrate(model["owner"])
    qualify(model, result["version"], tmp_path)
    actual = model["reader"].query(
        "disclosure", {"filingId": SERIAL, "version": result["version"]}
    )["data"]
    expected = row.model_dump(mode="json")
    assert {key: actual[key] for key in expected} == expected
    with connect(model["admin"], row_factory=dict_row) as c:
        prices = c.execute(
            "SELECT prices,capacity_before,capacity_after,position FROM hkex.particulars WHERE version=%s",
            (result["version"],),
        ).fetchone()
        assert (
            prices["prices"][1]["value"] == "0.6391"
            and prices["capacity_before"] is None
        )
        assert prices["capacity_after"] == "2201" and prices["position"] == "long"
        controls = c.execute(
            "SELECT percentage_control_raw FROM hkex.controls WHERE version=%s",
            (result["version"],),
        ).fetchall()
        assert len(controls) == 3 and all(
            x["percentage_control_raw"] == "100.00" for x in controls
        )
        assert (
            c.execute(
                "SELECT count(*) FROM hkex.interests WHERE version=%s AND capacity_code IS NULL",
                (result["version"],),
            ).fetchone()["count"]
            == 6
        )


def detail_collector(model, handler):
    routes = policy().routes.copy()
    routes["detail"] = ORIGIN + PATH
    install_policy(model, routes=routes)
    scope = window(issuer_id=CONTEXT["issuer_id"], start="2026-10-20", end="2026-10-27")
    run = "form3b-document-intake"
    with connect(model["owner"]) as c:
        c.execute(
            "INSERT INTO hkex.runs(id,operation,policy_hash,scope_window,scheduled_for,state) VALUES(%s,'pilot',%s,%s,now(),'running')",
            (
                run,
                model["store"].policy_hash,
                Jsonb(scope.model_dump(mode="json")),
            ),
        )
    collector = Collector(
        model["store"], Form3BAdapter([CONTEXT], transport=httpx.MockTransport(handler))
    )
    collector.deadline = time.monotonic() + 60
    return collector, run


def test_real_document_adapter_preserves_html_hash_and_reserves_before_dispatch(model):
    raw = document()
    seen = []

    def handler(request):
        seen.append(str(request.url))
        with connect(model["admin"], row_factory=dict_row) as c:
            assert (
                c.execute(
                    "SELECT count(*) n FROM hkex.requests WHERE state='unknown'"
                ).fetchone()["n"]
                == 1
            )
        return httpx.Response(200, content=raw, headers={"content-type": "text/html"})

    collector, run = detail_collector(model, handler)
    value, capture = collector._fetch(run, "detail", SERIAL)
    assert value["securities"][1]["stock_code"] is None and len(seen) == 1
    with connect(model["admin"], row_factory=dict_row) as c:
        row = c.execute(
            "SELECT * FROM hkex.captures WHERE id=%s", (capture,)
        ).fetchone()
        assert (
            row["raw_sha256"] == hashlib.sha256(raw).hexdigest()
            and row["validation"] == "validated"
        )
        assert row["source_location"] == seen[0] and b"<span" in bytes(row["raw_bytes"])
        assert c.execute("SELECT count(*) n FROM hkex.accepted").fetchone()["n"] == 0


def test_unsupported_document_context_is_rejected_before_reservation(model):
    collector, run = detail_collector(
        model, lambda request: pytest.fail("No provider dispatch is permitted")
    )
    with pytest.raises(ValueError, match="QUALIFIED_DETAIL_ROUTE"):
        collector._fetch(run, "inventory", "not-a-detail")
    with connect(model["admin"], row_factory=dict_row) as c:
        assert c.execute("SELECT count(*) n FROM hkex.requests").fetchone()["n"] == 0


def test_document_layout_failure_is_retained_as_rejected_capture_and_never_published(
    model,
):
    collector, run = detail_collector(
        model,
        lambda request: httpx.Response(
            200,
            content=document(lblDStockCode="00001"),
            headers={"content-type": "text/html"},
        ),
    )
    with pytest.raises(ValueError, match="SOURCE_SCHEMA_CHANGED"):
        collector._fetch(run, "detail", SERIAL)
    with connect(model["admin"], row_factory=dict_row) as c:
        assert (
            c.execute("SELECT validation FROM hkex.captures").fetchone()["validation"]
            == "rejected"
        )
        assert c.execute("SELECT count(*) n FROM hkex.accepted").fetchone()["n"] == 0
