"""Entirely invented normalized fixtures. No captured HKEX notices or code meanings."""

import hashlib
import json
from datetime import datetime, timedelta, timezone

from mcp_open_data_hk.curated.hkex.contracts import Filing, MODES, Policy, Window


def policy(**updates):
    now = datetime.now(timezone.utc)
    doc = dict(
        reference="synthetic-test-only",
        evidence_sha256="a" * 64,
        qualified_at=now - timedelta(days=1),
        expires_at=now + timedelta(days=1),
        modes={mode: "allowed" for mode in MODES},
        allowed_fields=tuple(Filing.model_fields),
        routes={
            kind: "https://di.hkex.com.hk/__synthetic_test_only/" + kind
            for kind in ("listing", "detail", "inventory")
        },
        forms=("1", "2", "3A", "3B", "3C", "3D"),
        codes={
            "capacity": {"TEST_CAP": "Invented capacity"},
            "reason": {"TEST_REASON": "Invented reason"},
        },
        retention_seconds=7 * 86400,
        cursor_seconds=3600,
        min_interval_seconds=1,
        inventory_basis="filed",
        inventory_method="synthetic independent filing inventory",
        recheck_rule="Every route/field/purpose/terms change",
    )
    doc.update(updates)
    return Policy.model_validate(doc)


def window(**updates):
    doc = dict(
        issuer_id="TEST_ISSUER", start="2026-10-12", end="2026-10-19", basis="filed"
    )
    doc.update(updates)
    return Window.model_validate(doc)


def day(value=None):
    return dict(
        value=value, precision="day" if value else "unknown", timezone="Asia/Hong_Kong"
    )


def filing(serial="TEST_001", **updates):
    doc = dict(
        serial=serial,
        issuer_id="TEST_ISSUER",
        issuer_name="Synthetic Example 香港測試",
        channel="dion",
        form="1",
        subject="Invented subject",
        event_date=day("2020-01-01"),
        filed_date=day("2026-10-14"),
        published_date=day(),
        state="original",
        securities=[
            dict(
                source_id="TEST_SEC_A",
                stock_code="00001",
                share_class="ordinary A",
                name="Invented A",
            )
        ],
        interests=[
            dict(
                line="001",
                section="TEST",
                security_id="TEST_SEC_A",
                capacity_code="TEST_CAP",
                nature="deemed",
                position="long",
                phase="after",
                instrument="issuer_shares",
                shares="9007199254740993.000000000000000001",
                percentage="5.12345678901234567890",
                unit="shares",
            )
        ],
        particulars=[
            dict(
                line="001",
                reason_code="TEST_REASON",
                shares=None,
                price="1.00000000000000001",
                currency="HKD",
                unit="per share",
            )
        ],
    )
    doc.update(updates)
    return Filing.model_validate(doc)


class SyntheticAdapter:
    """Local byte responses only. Does not construct or issue any HTTP requests."""

    def __init__(self, rows, w=None, mutate=None, after=None):
        self.rows = {row.serial: row for row in rows}
        self.window = w or window()
        self.mutate, self.after = mutate, after
        self.calls = []
        self.expected = [
            r.serial
            for r in rows
            if r.filed_date.value
            and self.window.start <= r.filed_date.value < self.window.end
        ]

    def fetch(self, kind, route, key, **bounds):
        self.calls.append((kind, key))
        if kind == "inventory":
            doc = dict(
                contract="mcp-hk-hkex-normalized-v1",
                window=self.window.model_dump(mode="json"),
                snapshot="synthetic-snapshot",
                serials=self.expected,
                detail_hashes={
                    key: hashlib.sha256(
                        json.dumps(row.model_dump(mode="json")).encode()
                    ).hexdigest()
                    for key, row in self.rows.items()
                },
                pages=max(1, len(self.expected)),
                method="synthetic independent filing inventory",
                issuer_name="Synthetic Example 香港測試",
                securities=[s.model_dump(mode="json") for s in filing().securities],
            )
        elif kind == "listing":
            page = int(key)
            doc = dict(
                contract="mcp-hk-hkex-normalized-v1",
                snapshot="synthetic-snapshot",
                page=page,
                pages=max(1, len(self.expected)),
                serials=self.expected[page - 1 : page],
            )
        else:
            doc = self.rows[key].model_dump(mode="json")
        if self.mutate:
            doc = self.mutate(kind, key, doc)
        if self.after:
            self.after(kind, key)
        if isinstance(doc, tuple):
            return doc
        return 200, json.dumps(doc).encode(), None
