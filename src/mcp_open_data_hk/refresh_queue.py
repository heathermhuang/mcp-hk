"""Bounded cadence-aware due queue. Skipped/held IDs never consume read slots."""

import asyncio
import json
import re
import time
from collections import deque, Counter
from urllib.parse import urlsplit

from .catalogue_store import unpack
from .contracts import DomainError
from .quality import HELD, REVISION, review_interval
from .review_config import (
    CONCURRENCY,
    PER_HOST_CONCURRENCY,
    DAILY_REVIEW_BUDGET,
    RECOVERY_BATCH_SIZE,
    SOURCE_REVIEW,
    RECOVERY_SECONDS,
    SCHEDULE_SECONDS,
)


class RefreshQueue:
    def __init__(self, catalogue):
        self.catalogue = catalogue
        self.store = catalogue.store
        with self.store.connect() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS resource_review_policy (id TEXT PRIMARY KEY, interval INTEGER NOT NULL, cache_ttl INTEGER NOT NULL, next_due REAL NOT NULL, last_attempt REAL, failures INTEGER NOT NULL DEFAULT 0);
            CREATE INDEX IF NOT EXISTS review_due ON resource_review_policy(next_due);
            CREATE TABLE IF NOT EXISTS resource_review_state (id INTEGER PRIMARY KEY CHECK(id=1), receipt TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS resource_review_setup (id INTEGER PRIMARY KEY CHECK(id=1), generation TEXT NOT NULL, revision TEXT NOT NULL);
            """
            )

    def prepare(self):
        generation = self.catalogue.head()
        with self.store.connect() as db:
            setup = db.execute(
                "SELECT * FROM resource_review_setup WHERE id=1"
            ).fetchone()
            if (
                setup
                and setup["generation"] == generation
                and setup["revision"] == REVISION
            ):
                return
            datasets = {
                r["id"]: unpack(r["payload"])
                for r in db.execute(
                    "SELECT id,payload FROM inventory_datasets WHERE generation=?",
                    (generation,),
                )
            }
            rows = db.execute(
                "SELECT r.id,r.dataset,r.payload,c.validated FROM inventory_resources r LEFT JOIN resource_checks c ON c.id=r.id WHERE r.generation=?",
                (generation,),
            ).fetchall()
            policies = []
            for row in rows:
                resource = unpack(row["payload"])
                interval = review_interval(datasets[row["dataset"]], resource)
                policies.append(
                    (
                        row["id"],
                        interval,
                        300 if resource.get("isApi") else 86400,
                        (row["validated"] or 0) + interval,
                    )
                )
            db.executemany(
                "INSERT INTO resource_review_policy(id,interval,cache_ttl,next_due) VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET interval=excluded.interval,cache_ttl=excluded.cache_ttl,next_due=CASE WHEN resource_review_policy.failures>0 THEN max(resource_review_policy.next_due,excluded.next_due) ELSE excluded.next_due END",
                policies,
            )
            # Older run-budget cancellations added a source-failure cooldown
            # without recording a source failure. Only recover still-queryable
            # accepted sources whose last check predates that failed review.
            # Actual source failures change check status and retain their backoff.
            db.execute(
                "UPDATE resource_review_policy SET next_due=min(next_due,(SELECT c.validated+resource_review_policy.interval FROM resource_checks c WHERE c.id=resource_review_policy.id)),failures=0 WHERE failures>0 AND EXISTS (SELECT 1 FROM resource_checks c WHERE c.id=resource_review_policy.id AND c.status='queryable' AND c.validated IS NOT NULL AND c.checked<resource_review_policy.last_attempt)"
            )
            db.execute(
                "INSERT OR REPLACE INTO resource_review_setup VALUES (1,?,?)",
                (generation, REVISION),
            )

    def due(self, batch, now):
        self.prepare()
        with self.store.connect() as db:
            # A confirmed source validation after a failed review ends that
            # failure's cooldown; otherwise a recovered five-minute feed can
            # become overdue again while an obsolete hour-long backoff remains.
            db.execute(
                "UPDATE resource_review_policy SET failures=0,next_due=(SELECT c.validated+resource_review_policy.interval FROM resource_checks c WHERE c.id=resource_review_policy.id) WHERE failures>0 AND EXISTS (SELECT 1 FROM resource_checks c WHERE c.id=resource_review_policy.id AND c.status='queryable' AND c.validated>=resource_review_policy.last_attempt)"
            )
            # On-demand successful reads satisfy the review deadline too.
            db.execute(
                "UPDATE resource_review_policy SET next_due=max(next_due,(SELECT validated+interval FROM resource_checks WHERE resource_checks.id=resource_review_policy.id)) WHERE EXISTS (SELECT 1 FROM resource_checks c WHERE c.id=resource_review_policy.id AND c.validated IS NOT NULL AND c.status='queryable')"
            )
            held = tuple(sorted(HELD))
            marks = ",".join("?" for _ in held)
            return [
                {
                    "id": r["id"],
                    "interval": r["interval"],
                    "status": r["status"],
                    "host": urlsplit(unpack(r["payload"])["url"]).hostname,
                }
                for r in db.execute(
                    f"SELECT r.id,r.payload,p.interval,c.status FROM resource_review_policy p JOIN inventory_resources r ON r.id=p.id LEFT JOIN resource_checks c ON c.id=r.id LEFT JOIN resource_policies t ON t.id=r.id WHERE r.generation=? AND (p.next_due<=? OR (p.next_due<=? AND c.status IN ('queryable','document') AND p.failures=0)) AND COALESCE(c.status,'pending') NOT IN ({marks}) AND t.ttl IS NULL ORDER BY CASE WHEN COALESCE(c.status,'pending')='pending' THEN 0 WHEN c.status IN ('queryable','document','stale') THEN 1 ELSE 2 END,(?-COALESCE(c.validated,c.checked,p.next_due-p.interval))/p.interval DESC,p.next_due,r.id LIMIT ?",
                    (
                        self.catalogue.head(),
                        now,
                        now + SCHEDULE_SECONDS,
                        *held,
                        now,
                        batch,
                    ),
                )
            ]

    def selectors(self, rid):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT schema_json FROM resource_variants WHERE resource=? AND schema_json IS NOT NULL ORDER BY validated DESC LIMIT 1",
                (rid,),
            ).fetchone()
        if not row:
            return {}
        schema = unpack(row[0])
        args = {}
        if schema.get("recordPath"):
            args["record_path"] = schema["recordPath"]
        if schema.get("sheet"):
            args["sheet"] = schema["sheet"]
        if schema.get("apiFamily") == "ArcGIS":
            m = re.search(
                r"/(?:FeatureServer|MapServer)/(\d+)",
                schema.get("resolvedSourceUrl", ""),
            )
            if m:
                args["layer"] = int(m.group(1))
        return args

    async def run(self, resources, batch, max_seconds):
        if (
            not 1 <= batch <= RECOVERY_BATCH_SIZE
            or not 0 < max_seconds <= RECOVERY_SECONDS
        ):
            raise ValueError("Audit exceeds bounded recovery limits")
        started = time.monotonic()
        selected = await asyncio.to_thread(self.due, batch, time.time())
        attempted = 0
        failures = 0
        deferred = 0
        budget_exhausted = False
        errors = []

        async def inspect(row):
            nonlocal attempted, failures, deferred, budget_exhausted
            remaining = max_seconds - (time.monotonic() - started)
            if remaining < 1 or budget_exhausted:
                return
            try:
                await asyncio.to_thread(
                    self.store.consume_budget,
                    "resource_maintenance",
                    DAILY_REVIEW_BUDGET,
                )
            except DomainError:
                budget_exhausted = True
                return
            attempted += 1
            error = None
            token = SOURCE_REVIEW.set(True)
            try:
                selectors = await asyncio.to_thread(self.selectors, row["id"])
                remaining = max_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    deferred += 1
                    return
                await asyncio.wait_for(
                    resources.schema(row["id"], require_fresh=True, **selectors),
                    timeout=remaining,
                )
            except asyncio.TimeoutError:
                # Exhausting this run's time budget says nothing about source
                # health. Keep the source due for the next bounded batch.
                deferred += 1
                return
            except DomainError as exc:
                failures += 1
                error = exc.code
            except Exception:
                failures += 1
                error = "REVIEW_INTERNAL_ERROR"
            finally:
                SOURCE_REVIEW.reset(token)
            if error and len(errors) < 10:
                errors.append({"resourceId": row["id"], "code": error})
            await asyncio.to_thread(self.record_attempt, row, error, time.time())

        # Do not occupy global slots with tasks waiting for the same host. Every
        # started task is awaited before checkpointing, including deadline exits.
        pending = deque(selected)
        active = Counter()
        running = {}
        try:
            while pending or running:
                remaining = max_seconds - (time.monotonic() - started)
                if remaining < 1 or budget_exhausted:
                    pending.clear()
                while pending and len(running) < CONCURRENCY:
                    row = None
                    for _ in range(len(pending)):
                        candidate = pending.popleft()
                        if active[candidate["host"]] < PER_HOST_CONCURRENCY:
                            row = candidate
                            break
                        pending.append(candidate)
                    if row is None:
                        break
                    active[row["host"]] += 1
                    running[asyncio.create_task(inspect(row))] = row["host"]
                if running:
                    done, _ = await asyncio.wait(
                        running, return_when=asyncio.FIRST_COMPLETED
                    )
                    for task in done:
                        active[running.pop(task)] -= 1
                        await task
        finally:
            for task in running:
                task.cancel()
            if running:
                await asyncio.gather(*running, return_exceptions=True)
        elapsed = time.monotonic() - started
        receipt = {
            "generation": self.catalogue.head(),
            "policyVersion": REVISION,
            "selection": "due_eligible_resources_by_relative_deadline",
            "selected": len(selected),
            "processed": attempted,
            "failed": failures,
            "deferred": deferred,
            "heldStatuses": sorted(HELD),
            "maxSeconds": max_seconds,
            "deadlineReached": bool(deferred)
            or (attempted < len(selected) and max_seconds - elapsed < 1),
            "elapsedSeconds": round(elapsed, 3),
            "dailySourceReadBudget": DAILY_REVIEW_BUDGET,
            "concurrency": CONCURRENCY,
            "perHostConcurrency": PER_HOST_CONCURRENCY,
            "failureExamples": errors,
            "budgetExhausted": budget_exhausted,
            "cycleComplete": not selected,
        }
        await asyncio.to_thread(self.record_receipt, receipt)
        return receipt

    def record_attempt(self, row, error, now):
        with self.store.connect() as db:
            old = db.execute(
                "SELECT failures FROM resource_review_policy WHERE id=?", (row["id"],)
            ).fetchone()[0]
            count = old + 1 if error else 0
            cooldown = (
                min(86400, 3600 * 2 ** min(count - 1, 5)) if error else row["interval"]
            )
            if error in {"ACCESS_RESTRICTED", "SOURCE_NOT_FOUND"}:
                cooldown = 86400
            db.execute(
                "UPDATE resource_review_policy SET next_due=?,last_attempt=?,failures=? WHERE id=?",
                (now + cooldown, now, count, row["id"]),
            )

    def record_receipt(self, receipt):
        with self.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO resource_review_state VALUES (1,?)",
                (json.dumps({**receipt, "completedAt": time.time()}),),
            )
