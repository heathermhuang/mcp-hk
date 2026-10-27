"""Public racing facts and operator-controlled collection. Public reads never scrape."""

import asyncio
import csv
import hashlib
import io
import json
import os
import tempfile
import time
import urllib.request
import zipfile
from contextvars import ContextVar
from pathlib import Path

from starlette.concurrency import run_in_threadpool

from .contracts import DomainError
from .curated.racing.prototype import PrototypeReader
from .curated.racing.policy import RacingRejected, canonical
from .racing_store import RacingStore

ingestion_context = ContextVar("racing_ingestion", default=None)


def ingestion_status():
    value = ingestion_context.get()
    if value is None and os.environ.get("MCP_HK_EDGE_MODE") == "true":
        from fastmcp.server.dependencies import get_http_headers
        from .operations import authorized

        headers = get_http_headers()
        raw = headers.get("x-mcp-racing-budget", "")
        if (
            authorized("Bearer " + headers.get("x-mcp-edge-token", ""))
            and raw
            and len(raw) <= 4096
        ):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and parsed.get("durable") is True:
                    value = parsed
            except ValueError:
                pass
    return value


class RacingReader(PrototypeReader):
    def envelope(self, snapshot, data):
        from .curated.racing.dividends import validate_observation

        records = (
            data.get("items", [])
            if isinstance(data, dict) and "items" in data
            else [data]
        )
        for record in records:
            if isinstance(record, dict) and "dividends" in record:
                validate_observation(record["dividends"], record["id"])
        return {
            "data": data,
            "meta": {
                "pack": "hkjc_racing",
                "version": snapshot["version"],
                "sourceBasis": "public_factual_results",
                "lastObservedAt": snapshot["observedAt"],
            },
            "coverage": snapshot["coverage"],
            "provenance": snapshot["provenance"],
            "warnings": [
                {
                    "code": "RESULTS_PAGE_COVERAGE",
                    "message": "Result races and published runners are covered as stated. Separate declared-runner inventory, full profiles and intraday odds history are not implied.",
                }
            ],
        }

    def status(self):
        from .racing_coverage import inventory, families

        meetings = self.store.meetings()
        profiles = self.store.profiles.status()
        with self.store.connect() as db:
            queue = [
                dict(r)
                for r in db.execute(
                    "SELECT state,count(*) AS meetings FROM racing_queue GROUP BY state"
                )
            ]
            totals = dict(
                db.execute(
                    "SELECT count(*) AS meetings,coalesce(sum(json_extract(coverage,'$.observedRaces')),0) AS races,coalesce(sum(json_extract(coverage,'$.resultRows')),0) AS resultRows,min(day) AS earliest,max(day) AS latest FROM racing_accepted"
                ).fetchone()
            )
            dividends = dict(
                db.execute(
                    "SELECT count(*) AS observedRaces,coalesce(sum(json_array_length(json_extract(r.value,'$.dividends.quotes'))),0) AS quotedRows FROM racing_accepted a JOIN racing_snapshots s USING(version),json_each(s.payload,'$.races') r WHERE json_extract(r.value,'$.dividends.state')='observed'"
                ).fetchone()
            )
            held = db.execute(
                "SELECT state,error FROM racing_attempts WHERE state IN ('reserved','unknown','held') ORDER BY id DESC LIMIT 1"
            ).fetchone()
            seasons = inventory(db)
            family_coverage = families(db, totals, dividends, profiles)
        return {
            "data": {
                "dividendCoverage": {
                    **dividends,
                    "scope": "quoted final-dividend tables in accepted results",
                    "stakeNormalized": False,
                },
                "source": "hkjc",
                "state": "available" if meetings else "ingestion_in_progress",
                "liveQualified": bool(meetings),
                "acceptedVersion": meetings[0]["version"] if meetings else None,
                "sourceBasis": "public_factual_results",
                "coverage": totals,
                "profileObservations": profiles,
                "seasonCoverage": seasons,
                "meetings": meetings,
                "queue": queue,
                "hold": dict(held) if held else None,
                "durableIngestion": ingestion_status(),
                "collectionOnRead": False,
                "scheduled": True,
                "families": family_coverage,
                "cadence": "one bounded source step per existing five-minute maintenance tick; manual bounded backfill batches share the same durable budget",
            },
            "meta": {"pack": "hkjc_racing"},
            "provenance": [
                {
                    "sourceUrl": "https://racing.hkjc.com/en-us/local/information/localresults",
                    "attribution": "The Hong Kong Jockey Club public racing facts",
                }
            ],
        }

    def archive(self, version, race_id):
        payload = self.results(race_id, version)
        fields = (
            "horseNumber",
            "placing",
            "status",
            "participantId",
            "draw",
            "timeSeconds",
            "weightLb",
            "bodyWeightLb",
            "winOddsFinal",
            "marginRaw",
        )
        text = io.StringIO(newline="")
        writer = csv.DictWriter(
            text, fieldnames=fields, quoting=csv.QUOTE_ALL, lineterminator="\n"
        )
        writer.writeheader()
        for row in payload["data"]["results"]:
            writer.writerow(
                {
                    k: (
                        "'" + str(row[k])
                        if str(row[k])
                        .lstrip()
                        .startswith(("=", "+", "-", "@", "\t", "\r"))
                        else row[k]
                    )
                    for k in fields
                }
            )
        files = {
            "results.json": canonical(payload),
            "results.csv": text.getvalue().encode("utf-8-sig"),
            "NOTICE.txt": b"Source: The Hong Kong Jockey Club public factual results. Independent mcp.hk dataset; not endorsed by HKJC. Coverage and observation times are explicit. No betting advice, media or commentary.\n",
        }
        dividend = payload["data"].get(
            "dividends", {"state": "not_extracted", "quotes": None}
        )
        dividend_fields = (
            "id",
            "pool",
            "winningCombinationRaw",
            "amount",
            "amountRaw",
            "currency",
            "stakeBasis",
        )
        if dividend["state"] == "observed":
            stream = io.StringIO(newline="")
            csvwriter = csv.DictWriter(
                stream,
                fieldnames=dividend_fields,
                quoting=csv.QUOTE_ALL,
                lineterminator="\n",
            )
            csvwriter.writeheader()
            for quote in dividend["quotes"]:
                csvwriter.writerow({k: quote[k] for k in dividend_fields})
            files["dividends.csv"] = stream.getvalue().encode("utf-8-sig")
        files["schema.json"] = canonical(
            {
                "format": "mcp-hk-race-export-v1",
                "scope": "one accepted race and version",
                "results.csv": {
                    "scope": "runner summary; full nested facts in results.json",
                    "fields": list(fields),
                },
                "dividends.csv": {
                    "scope": "quoted final-dividend rows when observed; not stake-normalized returns",
                    "fields": list(dividend_fields),
                    "types": {k: "string" for k in dividend_fields},
                },
                "unknown": "JSON null remains unknown; no inferred stake or current value",
                "numericStrings": "source decimal precision preserved; import combination identifiers as text",
            }
        )
        files["manifest.json"] = canonical(
            {
                "version": version,
                "raceId": race_id,
                "rowCount": len(payload["data"]["results"]),
                "resultRows": len(payload["data"]["results"]),
                "dividendRows": (
                    len(dividend["quotes"]) if dividend["state"] == "observed" else None
                ),
                "dividendState": dividend["state"],
                "files": {
                    n: {"bytes": len(b), "sha256": hashlib.sha256(b).hexdigest()}
                    for n, b in files.items()
                },
            }
        )
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, body in sorted(files.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, body)
        if len(output.getvalue()) > 2 * 1024 * 1024:
            raise RacingRejected("RACING_OUTPUT_LIMIT")
        return output.getvalue()


class Racing:
    def __init__(self, store):
        self.store = RacingStore(store.path)
        self.reader = RacingReader(self.store)
        self.slots = asyncio.Semaphore(4)

    async def query(self, operation, **params):
        if operation not in {
            "status",
            "races",
            "results",
            "profile",
            "archive",
            "meetings",
            "profile_observation",
            "profile_history",
            "profile_archive",
        }:
            raise DomainError("INVALID_QUERY", "Unknown racing operation", 400)
        try:
            await asyncio.wait_for(self.slots.acquire(), 0.25)
        except asyncio.TimeoutError as exc:
            raise DomainError(
                "QUERY_BUSY", "Racing query slots busy", 429, retry_after=1
            ) from exc
        try:
            if operation in {
                "profile_observation",
                "profile_history",
                "profile_archive",
            }:
                fn = {
                    "profile_observation": self.store.profiles.read,
                    "profile_history": self.store.profiles.history,
                    "profile_archive": self.store.profiles.archive,
                }[operation]
            else:
                fn = (
                    self.store.meetings
                    if operation == "meetings"
                    else getattr(self.reader, operation)
                )
            return await run_in_threadpool(fn, **params)
        except RacingRejected as exc:
            code = str(exc)
            status = (
                404
                if code.endswith("NOT_FOUND")
                else (
                    503
                    if code == "RACING_DATA_NOT_READY"
                    or code.startswith("SOURCE_")
                    or code == "PROFILE_CONTENT_MISMATCH"
                    or code == "DIVIDEND_RECORD_INVALID"
                    or code == "DEVELOPMENT_SNAPSHOT_CHECKSUM_MISMATCH"
                    else 400
                )
            )
            raise DomainError(
                code, "Racing data is not available for this exact selection", status
            ) from exc
        finally:
            self.slots.release()

    def advance(self, max_requests=1):
        try:
            blocked = self.store.before_source()
        except (OSError, ValueError):
            return {"state": "held", "code": "RACING_ADMISSION_NOT_CONFIRMED"}
        if blocked:
            return blocked
        # Discovery is one independently budgeted step; ingestion resumes next tick.
        try:
            discovered = self.store.discover_due()
            if discovered.get("state") != "unchanged":
                return discovered
        except RacingRejected as exc:
            return {"state": "held", "code": str(exc)}
        self.store.profiles.seed()
        with self.store.connect() as db:
            profile_due = db.execute(
                "SELECT 1 FROM racing_profile_queue WHERE state IN ('pending','partial','available') AND next_due<=? LIMIT 1",
                (time.time(),),
            ).fetchone()
            result_due = db.execute(
                "SELECT 1 FROM racing_queue WHERE state IN ('pending','partial','refresh') LIMIT 1"
            ).fetchone()
            turn = db.execute(
                "SELECT value FROM racing_control WHERE key='source-family-turn'"
            ).fetchone()
            choose_profile = (
                self.store.profiles.scheduled()
                and profile_due
                and (not result_due or turn and turn[0] == "profiles")
            )
            db.execute(
                "INSERT OR REPLACE INTO racing_control VALUES('source-family-turn',?)",
                ("results" if choose_profile else "profiles",),
            )
        return (
            self.store.profiles.collect(max_requests)
            if choose_profile
            else self.store.advance(max_requests)
        )

    def qualify_checkpoint(self, version, digest):
        from .operations import MAX_BACKUP, restore

        origin = os.environ.get("MCP_HK_BOOTSTRAP_URL")
        if origin not in {
            "https://mcp-hk.measurable.workers.dev/__ops/snapshot",
            "https://mcp.hk/__ops/snapshot",
        }:
            raise RacingRejected("RACING_OFFSITE_ORIGIN_REQUIRED")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("Checkpoint redirects rejected")

        token = os.environ.get("MCP_HK_OPS_TOKEN", "")
        if not token:
            raise RacingRejected("RACING_OFFSITE_CREDENTIAL_REQUIRED")
        request = urllib.request.Request(
            origin,
            headers={
                "Authorization": "Bearer " + token,
                "User-Agent": "mcp.hk-racing-recovery/1.0",
            },
        )
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=120
        ) as response:
            if response.headers.get("X-Snapshot-SHA256") != digest:
                raise RacingRejected("RACING_OFFSITE_POINTER_CHANGED")
            packed = response.read(MAX_BACKUP + 1)
        with tempfile.TemporaryDirectory(prefix="racing-restore-") as folder:
            target = Path(folder) / "restored.sqlite3"
            restore(packed, digest, str(target))
            return self.store.accept_restored(RacingStore(target), version, digest)
