"""Bounded single-session capture engine. No default approved routes or scheduler."""

import hashlib
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .db import connect
from .policy import RacingRejected, checksum, utc
from .store import policy

MAX_BODY = 400 * 1024
MAX_RUN_BYTES = 16 * 1024 * 1024
MAX_DAY_BYTES = 64 * 1024 * 1024


class Collector:
    def __init__(self, dsn, digest, *, transport=None, enabled=False):
        self.dsn, self.digest, self.transport, self.enabled = (
            dsn,
            digest,
            transport,
            enabled,
        )

    def run(self, operation, scheduled_for, requests, *, checkpoint=None):
        """A failed/uncertain admission is retained. Same job key never silently retries."""
        from psycopg.types.json import Jsonb

        if not self.enabled:
            raise RacingRejected("RACING_COLLECTION_DISABLED")
        if operation not in {"meeting", "season", "history", "prospective"}:
            raise RacingRejected("INVALID_OPERATION")
        if not isinstance(requests, list) or len(requests) > 100000:
            raise RacingRejected("REQUEST_INVENTORY_LIMIT")
        inventory = checksum(requests)
        checkpoint = dict(checkpoint or {})
        start_index = checkpoint.get("next", 0)
        if (
            type(start_index) is not int
            or not 0 <= start_index <= len(requests)
            or start_index
            and checkpoint.get("requestInventorySha256") != inventory
        ):
            raise RacingRejected("CHECKPOINT_INVENTORY_MISMATCH")
        checkpoint["requestInventorySha256"] = inventory
        stamp = utc(scheduled_for)
        run_id = uuid.uuid4().hex
        started = time.monotonic()
        captures = []
        with connect(self.dsn, autocommit=True) as session:
            if not session.execute(
                "SELECT pg_try_advisory_lock(7242526) AS locked"
            ).fetchone()["locked"]:
                raise RacingRejected("SOURCE_SESSION_BUSY")
            admitted = session.execute(
                "INSERT INTO racing.jobs(operation,scheduled_for,run_id,state,checkpoint) VALUES(%s,%s,%s,'running',%s) ON CONFLICT DO NOTHING RETURNING run_id",
                (operation, stamp, run_id, Jsonb(checkpoint)),
            ).fetchone()
            if not admitted:
                return {"state": "duplicate", "captures": []}
            try:
                with httpx.Client(
                    transport=self.transport,
                    timeout=20,
                    follow_redirects=False,
                    trust_env=False,
                ) as client:
                    for index, (family, route) in enumerate(
                        requests[start_index:], start_index
                    ):
                        if (
                            index - start_index >= 40
                            or (index - start_index + 1) * MAX_BODY > MAX_RUN_BYTES
                            or time.monotonic() - started >= 580
                        ):
                            self.finish(run_id, "partial", {"next": index})
                            return {
                                "runId": run_id,
                                "state": "partial",
                                "captures": captures,
                            }
                        try:
                            request_id = self.reserve(run_id, family, route)
                        except RacingRejected as exc:
                            if str(exc) in {"SOURCE_CADENCE_HOLD", "SOURCE_DAILY_HOLD"}:
                                self.finish(run_id, "partial", {"next": index})
                                return {
                                    "runId": run_id,
                                    "state": "partial",
                                    "captures": captures,
                                }
                            raise
                        try:
                            with client.stream(
                                "GET",
                                route,
                                headers={
                                    "User-Agent": "mcp.hk-racing/1.0 (qualified read-only collector)"
                                },
                            ) as response:
                                if response.status_code != 200:
                                    self.settle(
                                        request_id,
                                        response.status_code,
                                        0,
                                        response.headers.get("retry-after"),
                                    )
                                    if response.status_code == 304:
                                        raise RacingRejected(
                                            "UNCHANGED_REQUIRES_EXISTING_CAPTURE"
                                        )
                                    raise RacingRejected("SOURCE_HTTP_HOLD")
                                content_type = (
                                    response.headers.get("content-type", "")
                                    .split(";")[0]
                                    .lower()
                                )
                                if content_type not in {
                                    "text/html",
                                    "application/json",
                                }:
                                    raise RacingRejected("SOURCE_CONTENT_TYPE")
                                body = bytearray()
                                for chunk in response.iter_bytes():
                                    body.extend(chunk)
                                    if len(body) > MAX_BODY:
                                        raise RacingRejected("SOURCE_BODY_LIMIT")
                                    if time.monotonic() - started >= 600:
                                        raise RacingRejected("SOURCE_RUN_TIMEOUT")
                            self.settle(request_id, 200, len(body))
                            # Recheck after the request. A revocation while in flight withholds bytes.
                            with connect(self.dsn) as conn:
                                policy(
                                    conn, self.digest, family, "collect", route=route
                                )
                                policy(conn, self.digest, family, "cache", route=route)
                            capture_id = self.persist_capture(
                                run_id, family, route, bytes(body)
                            )
                            captures.append(
                                {
                                    "captureId": capture_id,
                                    "family": family,
                                    "route": route,
                                    "body": bytes(body),
                                    "sha256": hashlib.sha256(body).hexdigest(),
                                    "retrievedAt": datetime.now(
                                        timezone.utc
                                    ).isoformat(),
                                    "runId": run_id,
                                }
                            )
                            self.checkpoint(
                                run_id,
                                {
                                    "next": index + 1,
                                    "captureHashes": [
                                        item["sha256"] for item in captures
                                    ],
                                },
                            )
                        except Exception:
                            # Unknown reservation survives process death; no free request/byte refund.
                            raise
                self.finish(run_id, "complete", {"next": len(requests)})
                return {"runId": run_id, "state": "complete", "captures": captures}
            except Exception:
                self.finish(run_id, "failed", {"next": start_index + len(captures)})
                raise
            finally:
                session.execute("SELECT pg_advisory_unlock(7242526)")

    def reserve(self, run_id, family, route):
        request_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc)
        with connect(self.dsn) as conn:
            policy(conn, self.digest, family, "collect", route=route)
            policy(conn, self.digest, family, "cache", route=route)
            job = conn.execute(
                "SELECT operation FROM racing.jobs WHERE run_id=%s", (run_id,)
            ).fetchone()
            if job["operation"] in {"season", "history"}:
                policy(conn, self.digest, family, "history", route=route)
            if not policy(conn, self.digest, family, "cache", route=route).get(
                "rawRetentionSeconds"
            ):
                raise RacingRejected("RAW_RETENTION_UNQUALIFIED")
            # Enforce cadence across every run/route, not just one in-memory session.
            grant = policy(conn, self.digest, family, "collect", route=route)
            hold = conn.execute(
                "SELECT hold_until FROM racing.source_state WHERE source='hkjc' FOR UPDATE"
            ).fetchone()["hold_until"]
            uncertain = conn.execute(
                "SELECT 1 FROM racing.requests WHERE settled_at IS NULL LIMIT 1"
            ).fetchone()
            if uncertain or hold and hold > now:
                raise RacingRejected("SOURCE_UNRECONCILED_OR_HELD")
            previous = conn.execute(
                "SELECT max(reserved_at) AS last FROM racing.requests"
            ).fetchone()["last"]
            if (
                previous
                and (now - previous).total_seconds() < grant["minIntervalSeconds"]
            ):
                raise RacingRejected("SOURCE_CADENCE_HOLD")
            conn.execute(
                "INSERT INTO racing.budgets(utc_day) VALUES(%s) ON CONFLICT DO NOTHING",
                (now.date(),),
            )
            budget = conn.execute(
                "UPDATE racing.budgets SET attempts=attempts+1,reserved_bytes=reserved_bytes+%s WHERE utc_day=%s AND attempts<200 AND reserved_bytes+%s<=%s AND (hold_until IS NULL OR hold_until<=%s) RETURNING attempts",
                (MAX_BODY, now.date(), MAX_BODY, MAX_DAY_BYTES, now),
            ).fetchone()
            if not budget:
                raise RacingRejected("SOURCE_DAILY_HOLD")
            conn.execute(
                "INSERT INTO racing.requests(request_id,run_id,route_hash) VALUES(%s,%s,%s)",
                (request_id, run_id, hashlib.sha256(route.encode()).hexdigest()),
            )
        return request_id

    def persist_capture(self, run_id, family, route, body):
        now = datetime.now(timezone.utc)
        capture_id = uuid.uuid4().hex
        with connect(self.dsn) as conn:
            grant = policy(conn, self.digest, family, "cache", route=route)
            retention = grant.get("rawRetentionSeconds", 0)
            if (
                type(retention) is not int
                or not 0 < retention <= grant["retentionSeconds"]
            ):
                raise RacingRejected("RAW_RETENTION_UNQUALIFIED")
            conn.execute(
                "INSERT INTO racing.capture_buffer(capture_id,run_id,family,route,raw_sha256,body,retrieved_at,expires_at,policy_digest) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    capture_id,
                    run_id,
                    family,
                    route,
                    hashlib.sha256(body).hexdigest(),
                    body,
                    now,
                    now + timedelta(seconds=retention),
                    self.digest,
                ),
            )
        return capture_id

    def retained_capture(self, capture_id):
        with connect(self.dsn) as conn:
            row = conn.execute(
                "SELECT * FROM racing.capture_buffer WHERE capture_id=%s AND body IS NOT NULL AND expires_at>now()",
                (capture_id,),
            ).fetchone()
            if not row:
                raise RacingRejected("CAPTURE_EXPIRED")
            policy(
                conn, row["policy_digest"], row["family"], "cache", route=row["route"]
            )
            body = bytes(row["body"])
            if hashlib.sha256(body).hexdigest() != row["raw_sha256"]:
                raise RacingRejected("CAPTURE_CHECKSUM_MISMATCH")
            return body

    def settle(self, request_id, status, size, retry_after=None):
        now = datetime.now(timezone.utc)
        until = None
        if status != 200:
            until = now + timedelta(hours=24 if status == 403 else 1)
            if retry_after:
                try:
                    parsed = now + timedelta(seconds=max(0, int(retry_after)))
                except ValueError:
                    try:
                        parsed = parsedate_to_datetime(retry_after)
                        if parsed.tzinfo is None:
                            raise ValueError()
                    except (ValueError, TypeError, OverflowError):
                        parsed = until
                until = max(until, parsed)
        with connect(self.dsn) as conn:
            conn.execute(
                "UPDATE racing.requests SET settled_at=now(),outcome=%s,bytes=%s WHERE request_id=%s AND settled_at IS NULL",
                (str(status), size, request_id),
            )
            if until:
                conn.execute(
                    "UPDATE racing.source_state SET hold_until=GREATEST(COALESCE(hold_until,%s),%s) WHERE source='hkjc'",
                    (until, until),
                )
                conn.execute(
                    "UPDATE racing.budgets SET hold_until=GREATEST(COALESCE(hold_until,%s),%s) WHERE utc_day=%s",
                    (until, until, now.date()),
                )

    def checkpoint(self, run_id, checkpoint):
        from psycopg.types.json import Jsonb

        with connect(self.dsn) as conn:
            conn.execute(
                "UPDATE racing.jobs SET checkpoint=checkpoint || %s WHERE run_id=%s AND state='running'",
                (Jsonb(checkpoint), run_id),
            )

    def finish(self, run_id, state, checkpoint):
        from psycopg.types.json import Jsonb

        with connect(self.dsn) as conn:
            conn.execute(
                "UPDATE racing.jobs SET state=%s,checkpoint=checkpoint || %s WHERE run_id=%s",
                (state, Jsonb(checkpoint), run_id),
            )
