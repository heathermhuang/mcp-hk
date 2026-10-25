"""Durable bounded collection engine with an injected qualified route adapter.

There is deliberately no production provider parser/transport until exact routes
and response formats are authorised and inspected. Tests inject synthetic bytes.
The adapter gets a fixed operator policy route + typed key; no public URL reaches it.
"""

import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from pydantic import Field
from psycopg.types.json import Jsonb

from .contracts import (
    Security,
    Strict,
    Window,
    canonical,
    digest,
    parse_filing,
    revision_closure,
)

MAX_BODY = 2 * 1024 * 1024
TRANSFORM = digest(
    {p.name: p.read_text() for p in sorted(Path(__file__).parent.glob("*.py"))}
)


def provider_hold(status, retry_after, observed):
    """A source denial is reviewed; a provider's longer delay is never shortened."""
    if status == 403:
        return None, "SOURCE_403_MANUAL_REVIEW"
    try:
        if retry_after is None:
            delay = 3600
        elif (
            isinstance(retry_after, str)
            and retry_after.isascii()
            and retry_after.isdigit()
        ):
            delay = int(retry_after)
        elif type(retry_after) is int and retry_after >= 0:
            delay = retry_after
        else:
            raise ValueError()
        return observed + timedelta(seconds=max(60, delay)), "SOURCE_" + str(status)
    except (ValueError, OverflowError):
        # An unparseable/unrepresentable header is not permission to retry sooner.
        return None, "SOURCE_RETRY_AFTER_UNQUALIFIED"


class Inventory(Strict):
    contract: Literal["mcp-hk-hkex-normalized-v1"]
    window: Window
    snapshot: str = Field(min_length=1, max_length=200)
    serials: tuple[str, ...] = Field(max_length=5000)
    pages: int = Field(ge=1, le=100)
    detail_hashes: dict[str, str]
    method: str = Field(min_length=1, max_length=500)
    issuer_name: str = Field(min_length=1, max_length=300)
    securities: tuple[Security, ...] = Field(min_length=1, max_length=30)


class Listing(Strict):
    contract: Literal["mcp-hk-hkex-normalized-v1"]
    snapshot: str = Field(min_length=1, max_length=200)
    page: int = Field(ge=1, le=100)
    pages: int = Field(ge=1, le=100)
    serials: tuple[str, ...] = Field(max_length=100)


class Collector:
    def __init__(self, store, adapter=None):
        self.store, self.adapter = store, adapter
        self.deadline = None

    def _checkpoint(self, run_id, state):
        if len(canonical(state)) > 16 * 1024 * 1024:
            raise ValueError("NORMALIZED_CHECKPOINT_LIMIT")
        with self.store.connection("collect", "retain") as (c, _):
            c.execute(
                "UPDATE hkex.runs SET checkpoint=%s WHERE id=%s AND state='running'",
                (Jsonb(state), run_id),
            )

    def _fetch(self, run_id, kind, key):
        # Reserve before dispatch; a crash leaves an unknown, charged reservation.
        self.store.check_capacity()
        with self.store.connection("collect", "retain") as (c, policy):
            c.execute("SELECT * FROM hkex.control WHERE singleton FOR UPDATE")
            from .store import current_policy

            current_policy(c, self.store.policy_hash, ("collect", "retain"))
            control = c.execute("SELECT * FROM hkex.control WHERE singleton").fetchone()
            now = datetime.now(timezone.utc)
            if c.execute(
                "SELECT 1 FROM hkex.requests WHERE state='unknown' LIMIT 1"
            ).fetchone():
                raise ValueError("REQUEST_RECONCILIATION_REQUIRED")
            if control["hold_code"] in {
                "SOURCE_403_MANUAL_REVIEW",
                "SOURCE_RETRY_AFTER_UNQUALIFIED",
            } or (control["hold_until"] and control["hold_until"] > now):
                raise ValueError("SOURCE_HOLD")
            if (
                control["last_read_at"]
                and (now - control["last_read_at"]).total_seconds()
                < policy.min_interval_seconds
            ):
                raise ValueError("SOURCE_CADENCE_HOLD")
            if self.deadline is None or time.monotonic() >= self.deadline:
                raise ValueError("RUN_DEADLINE")
            old = c.execute(
                "SELECT state FROM hkex.requests WHERE run_id=%s AND kind=%s AND request_key=%s",
                (run_id, kind, key),
            ).fetchone()
            if old:
                # Never blindly reissue an uncertain/failed request, or repeat a
                # successful response lost before its durable checkpoint.
                raise ValueError("REQUEST_RECONCILIATION_REQUIRED")
            budget = c.execute(
                "SELECT count(*) FILTER(WHERE run_id=%s) AS run_reads,count(*) FILTER(WHERE reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC') AS day_reads,COALESCE(sum(COALESCE(received_bytes,reserved_bytes)) FILTER(WHERE run_id=%s),0) AS run_bytes,COALESCE(sum(COALESCE(received_bytes,reserved_bytes)) FILTER(WHERE reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'),0) AS day_bytes FROM hkex.requests WHERE run_id=%s OR reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'",
                (run_id, run_id, run_id),
            ).fetchone()
            available = min(
                MAX_BODY,
                policy.bytes_run - budget["run_bytes"],
                policy.bytes_day - budget["day_bytes"],
            )
            if (
                budget["run_reads"] >= policy.reads_run
                or budget["day_reads"] >= policy.reads_day
                or available <= 0
            ):
                raise ValueError("SOURCE_BUDGET_EXHAUSTED")
            if kind not in policy.routes:
                raise ValueError("QUALIFIED_ROUTE_REQUIRED")
            request_id = c.execute(
                "INSERT INTO hkex.requests(run_id,kind,request_key,reserved_bytes) VALUES(%s,%s,%s,%s) RETURNING id",
                (run_id, kind, key, available),
            ).fetchone()["id"]
            c.execute("UPDATE hkex.control SET last_read_at=now() WHERE singleton")
            route = policy.routes[kind]
        # Adapter must enforce no redirects, fixed origins, timeout and stream cap.
        # No such production adapter is installed while qualification is pending.
        status, body, retry_after = self.adapter.fetch(
            kind,
            route,
            key,
            max_bytes=available,
            timeout=min(20, max(0.1, self.deadline - time.monotonic())),
        )
        if not isinstance(body, bytes) or len(body) > available:
            raise ValueError("SOURCE_BODY_LIMIT")
        raw_hash = hashlib.sha256(body).hexdigest()
        observed = datetime.now(timezone.utc)
        with self.store.connection("collect", "retain") as (c, policy):
            c.execute(
                "UPDATE hkex.requests SET state=%s,status=%s,received_bytes=%s,sha256=%s WHERE id=%s",
                (
                    "success" if status == 200 else "failed",
                    status,
                    len(body),
                    raw_hash,
                    request_id,
                ),
            )
            if status in (403, 429, 503):
                until, code = provider_hold(status, retry_after, observed)
                c.execute(
                    "UPDATE hkex.control SET hold_until=%s,hold_code=%s WHERE singleton",
                    (until, code),
                )
            capture_id = digest(
                {"run": run_id, "request": request_id, "hash": raw_hash}
            )
            c.execute(
                "INSERT INTO hkex.captures VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    capture_id,
                    run_id,
                    self.store.policy_hash,
                    kind,
                    route,
                    observed,
                    raw_hash,
                    TRANSFORM,
                    body if policy.modes["raw"] == "allowed" else None,
                    "validated" if status == 200 else "rejected",
                ),
            )
        if status != 200:
            raise ValueError("SOURCE_" + str(status))
        try:
            value = json.loads(
                body,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    ValueError("NONFINITE_JSON")
                ),
            )
        except (ValueError, UnicodeError) as exc:
            raise ValueError("SOURCE_SCHEMA_CHANGED") from exc
        return value, capture_id

    def run(self, window, scheduled_for):
        window = Window.model_validate(window)
        if (window.end - window.start).days != 7:
            raise ValueError("PILOT_REQUIRES_SEVEN_DAYS")
        if scheduled_for.tzinfo is None:
            raise ValueError("SCHEDULE_TIMEZONE_REQUIRED")
        with self.store.connection(
            "collect", "normalize", "retain", "history", "backup"
        ) as (_, policy):
            if (
                window.basis != policy.inventory_basis
                or policy.inventory_basis == "unknown"
            ):
                raise ValueError("FILING_INVENTORY_UNQUALIFIED")
            if self.adapter is None:
                raise ValueError("QUALIFIED_PROVIDER_ADAPTER_REQUIRED")
        with self.store.session():
            with self.store.connection("collect", "retain") as (c, _):
                run = c.execute(
                    "SELECT * FROM hkex.runs WHERE operation='pilot' AND scheduled_for=%s",
                    (scheduled_for,),
                ).fetchone()
                if run:
                    if (
                        run["scope_window"] != window.model_dump(mode="json")
                        or run["policy_hash"] != self.store.policy_hash
                    ):
                        raise ValueError("IDEMPOTENCY_SCOPE_CONFLICT")
                    if run["state"] in ("validated", "unchanged"):
                        return {"run": run["id"], "state": run["state"]}
                    if run["state"] == "failed":
                        raise ValueError("FAILED_RUN_REQUIRES_REVIEW")
                    run_id, state = run["id"], run["checkpoint"]
                    c.execute(
                        "UPDATE hkex.runs SET state='running',error_code=NULL WHERE id=%s",
                        (run_id,),
                    )
                else:
                    run_id, state = uuid.uuid4().hex, {
                        "pages": {},
                        "details": {},
                        "captures": {},
                    }
                    previous = c.execute(
                        "SELECT checkpoint FROM hkex.runs WHERE operation='pilot' AND state='partial' AND policy_hash=%s AND scope_window=%s ORDER BY scheduled_for DESC LIMIT 1",
                        (self.store.policy_hash, Jsonb(window.model_dump(mode="json"))),
                    ).fetchone()
                    if previous:
                        state = previous["checkpoint"]
                    c.execute(
                        "INSERT INTO hkex.runs(id,operation,scheduled_for,policy_hash,scope_window,state) VALUES(%s,'pilot',%s,%s,%s,'running')",
                        (
                            run_id,
                            scheduled_for,
                            self.store.policy_hash,
                            Jsonb(window.model_dump(mode="json")),
                        ),
                    )
            self.deadline = time.monotonic() + 600
            try:
                return self._complete(run_id, window, state)
            except Exception as exc:
                code = (
                    str(exc)
                    if isinstance(exc, ValueError)
                    and str(exc).isupper()
                    and len(str(exc)) < 80
                    else "SOURCE_FAILURE"
                )
                partial = code in {
                    "SOURCE_BUDGET_EXHAUSTED",
                    "SOURCE_CADENCE_HOLD",
                    "SOURCE_HOLD",
                    "RUN_DEADLINE",
                }
                # Persist failure independent of a revoked/expired policy; never
                # change the accepted pointer or pretend failure is empty data.
                from ..build import connect

                with connect(self.store.dsn) as c:
                    c.execute(
                        "UPDATE hkex.runs SET state=%s,error_code=%s,finished_at=now() WHERE id=%s",
                        ("partial" if partial else "failed", code, run_id),
                    )
                return {
                    "run": run_id,
                    "state": "partial" if partial else "failed",
                    "code": code,
                }

    def _complete(self, run_id, window, state):
        if "inventory" not in state:
            raw, _ = self._fetch(run_id, "inventory", digest(window))
            inventory = Inventory.model_validate(raw)
            with self.store.connection("collect", "retain") as (_, policy):
                if (
                    inventory.window != window
                    or inventory.method != policy.inventory_method
                    or len(set(inventory.serials)) != len(inventory.serials)
                ):
                    raise ValueError("INVENTORY_SCOPE_MISMATCH")
            if not set(inventory.serials) <= set(inventory.detail_hashes) or any(
                len(h) != 64 or any(ch not in "0123456789abcdef" for ch in h)
                for h in inventory.detail_hashes.values()
            ):
                raise ValueError("INDEPENDENT_DETAIL_HASH_INVENTORY_REQUIRED")
            state["inventory"] = inventory.model_dump(mode="json")
            self._checkpoint(run_id, state)
            with self.store.connection("collect", "retain") as (c, _):
                previous = c.execute(
                    "SELECT v.manifest FROM hkex.accepted a JOIN hkex.versions v USING(version) WHERE a.singleton AND v.policy_hash=%s",
                    (self.store.policy_hash,),
                ).fetchone()
                if previous and previous["manifest"]["coverage"].get(
                    "inventoryHash"
                ) == digest(inventory):
                    c.execute(
                        "UPDATE hkex.runs SET state='unchanged',finished_at=now() WHERE id=%s",
                        (run_id,),
                    )
                    return {"run": run_id, "state": "unchanged"}
        inventory = Inventory.model_validate(state["inventory"])
        for number in range(1, inventory.pages + 1):
            if str(number) in state["pages"]:
                continue
            raw, _ = self._fetch(run_id, "listing", str(number))
            page = Listing.model_validate(raw)
            if (page.snapshot, page.page, page.pages) != (
                inventory.snapshot,
                number,
                inventory.pages,
            ):
                raise ValueError("PAGE_DRIFT")
            state["pages"][str(number)] = page.model_dump(mode="json")
            self._checkpoint(run_id, state)
        serials = [
            serial for page in state["pages"].values() for serial in page["serials"]
        ]
        if len(serials) != len(set(serials)) or set(serials) != set(inventory.serials):
            raise ValueError("INVENTORY_SERIAL_MISMATCH")
        pending = set(serials)
        while pending:
            serial = min(pending)
            pending.remove(serial)
            if serial not in state["details"]:
                raw, capture = self._fetch(run_id, "detail", serial)
                if serial not in inventory.detail_hashes:
                    raise ValueError("REVISION_CLOSURE_INVENTORY_REQUIRED")
                with self.store.connection("collect", "retain") as (c, _):
                    actual = c.execute(
                        "SELECT raw_sha256 FROM hkex.captures WHERE id=%s", (capture,)
                    ).fetchone()["raw_sha256"]
                    if actual != inventory.detail_hashes[serial]:
                        raise ValueError("INDEPENDENT_DETAIL_HASH_MISMATCH")
                with self.store.connection("normalize", "retain") as (_, policy):
                    row = parse_filing(raw, policy)
                if (
                    row.serial != serial
                    or row.issuer_id != window.issuer_id
                    or row.channel != window.channel
                ):
                    raise ValueError("DETAIL_IDENTITY_MISMATCH")
                if serial in inventory.serials:
                    value = getattr(row, window.basis + "_date").value
                    if value is None or not window.start <= value < window.end:
                        raise ValueError("WINDOW_DATE_UNPROVEN")
                state["details"][serial] = row.model_dump(mode="json")
                state["captures"][serial] = capture
                self._checkpoint(run_id, state)
            row = state["details"][serial]
            for link in (row["replaces"], row["superseded_by"]):
                if link and link not in state["details"]:
                    pending.add(link)
        with self.store.connection("normalize", "retain") as (_, policy):
            filings = [
                parse_filing(raw, policy) for _, raw in sorted(state["details"].items())
            ]
        closure = revision_closure(filings)
        coverage = {
            "window": window.model_dump(mode="json"),
            "inventorySnapshot": inventory.snapshot,
            "inventoryHash": digest(inventory),
            "inventoryMethod": inventory.method,
            "issuer": {
                "id": window.issuer_id,
                "name": inventory.issuer_name,
                "securities": [s.model_dump(mode="json") for s in inventory.securities],
            },
            "expectedSerials": sorted(inventory.serials),
            "acceptedSerials": sorted(state["details"]),
            "closureOutsideWindow": sorted(
                set(state["details"]) - set(inventory.serials)
            ),
            "pages": inventory.pages,
            "complete": not closure["missing"],
            "comprehensiveIncremental": False,
        }
        version = self.store.stage(run_id, filings, state["captures"], coverage)
        return {
            "run": run_id,
            "state": "validated",
            "version": version,
            "coverage": coverage,
        }
