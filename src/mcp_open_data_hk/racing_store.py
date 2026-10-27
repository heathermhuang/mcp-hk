"""Source-isolated racing state inside the service's existing SQLite/R2 checkpoint.

Public pointers advance only after the staged source state survives an actual
offsite checkpoint download and isolated restore. No licence flag is involved.
"""

import hashlib
import json
import re
import time
import os
import uuid
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .curated.racing.normalize import meeting, race, result_row
from .curated.racing.policy import RacingRejected, canonical, checksum, utc
from .curated.racing.prototype_store import ResultsStore, PilotCollector, MAX_PAGE
from .curated.racing.public_results import result_url
from .racing_calendar import source_url, CalendarCollector


def dividend_parser_hash():
    from .curated.racing import dividends, public_results

    return hashlib.sha256(
        Path(dividends.__file__).read_bytes()
        + Path(public_results.__file__).read_bytes()
    ).hexdigest()


def validate_snapshot(payload):
    if len(canonical(payload)) > 2 * 1024 * 1024:
        raise RacingRejected("RACING_OUTPUT_LIMIT")
    m = payload["meeting"]
    if (
        m["id"] != meeting(m["date"], m["venue"])
        or date.fromisoformat(m["date"]) > datetime.now(timezone.utc).date()
    ):
        raise RacingRejected("RACING_MEETING_IDENTITY")
    races = payload["races"]
    if not 1 <= len(races) <= 20 or [r["number"] for r in races] != list(
        range(1, len(races) + 1)
    ):
        raise RacingRejected("RACING_MEETING_INVENTORY")
    captures = {c["url"]: c for c in payload["provenance"]}
    for c in captures.values():
        result_url(c["url"])
        utc(c["observed"])
        if (
            not re.fullmatch("[a-f0-9]{64}", c["sha256"])
            or not 0 < c["bytes"] <= MAX_PAGE
        ):
            raise RacingRejected("RACING_CAPTURE_IDENTITY")
    rows = 0
    for r in races:
        if "dividendCandidate" in r:
            raise RacingRejected("DIVIDEND_UNRECONCILED_CANDIDATE")
        if "dividends" in r:
            from .curated.racing.dividends import validate_observation

            validate_observation(r["dividends"], r["id"])
        if (
            r["id"] != race(m["date"], m["venue"], r["number"])
            or len(r["provenance"]) != 2
        ):
            raise RacingRejected("RACING_RACE_IDENTITY")
        if any(captures.get(c["url"]) != c for c in r["provenance"]):
            raise RacingRejected("RACING_CAPTURE_LINEAGE")
        ids = set()
        ties = {}
        for f in r["results"]:
            normalized = result_row(
                {
                    "horseId": f["horse"]["sourceId"],
                    "horseNumber": f["horseNumber"],
                    "draw": f["draw"],
                    "placing": f["placingRaw"],
                    "time": f["timeRaw"],
                    "weightLb": f["weightLb"],
                    "claimLb": f["claimLb"],
                    "marginRaw": f["marginRaw"],
                },
                r["id"],
            )
            if (
                any(f[k] != v for k, v in normalized.items() if k != "revision")
                or f["participantId"] in ids
            ):
                raise RacingRejected("RACING_RESULT_SEMANTICS")
            raw = dict(f)
            digest = raw.pop("revision")
            if checksum(raw) != digest:
                raise RacingRejected("RACING_RESULT_CHECKSUM")
            ids.add(f["participantId"])
            if f["placing"] is not None:
                ties.setdefault(f["placing"], []).append(f)
            for kind in ("horse", "jockey", "trainer"):
                p = f[kind]
                if (
                    p["id"] != "hkjc:" + kind + ":" + p["sourceId"]
                    or not p["name"]
                    or len(p["name"]) > 200
                ):
                    raise RacingRejected("RACING_PARTICIPANT_IDENTITY")
        if (
            not 1 <= len(ids) <= 30
            or (
                1 not in ties
                and not (
                    r.get("status") == "void"
                    and all(f["status"] == "race_void" for f in r["results"])
                )
            )
            or any((len(g) > 1) != all(f["deadHeat"] for f in g) for g in ties.values())
        ):
            raise RacingRejected("RACING_RESULT_GROUP")
        rows += len(ids)
    c = payload["coverage"]
    if (
        c["expectedRaces"] != len(races)
        or c["observedRaces"] != len(races)
        or c["resultRows"] != rows
        or c["resultRaceInventoryComplete"] is not True
    ):
        raise RacingRejected("RACING_COVERAGE_MISMATCH")
    return payload


class RacingStore(ResultsStore):
    version_prefix = "racing-results-v1-"

    def __init__(self, filename):
        super().__init__(filename)
        with self.connect() as db:
            db.executescript(
                """
              CREATE TABLE IF NOT EXISTS racing_publications(version TEXT PRIMARY KEY,state TEXT NOT NULL,proof TEXT);
              CREATE TABLE IF NOT EXISTS racing_accepted(meeting TEXT PRIMARY KEY,day TEXT NOT NULL,venue TEXT NOT NULL,version TEXT NOT NULL,observed TEXT NOT NULL,coverage TEXT NOT NULL);
              CREATE INDEX IF NOT EXISTS racing_accepted_date ON racing_accepted(day DESC,venue,version);
              CREATE TABLE IF NOT EXISTS racing_queue(day TEXT NOT NULL,venue TEXT NOT NULL,state TEXT NOT NULL,error TEXT,updated REAL NOT NULL,PRIMARY KEY(day,venue));
              CREATE TABLE IF NOT EXISTS racing_control(key TEXT PRIMARY KEY,value TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS racing_calendar(period TEXT PRIMARY KEY,observed TEXT NOT NULL,state TEXT NOT NULL,payload TEXT NOT NULL,receipt TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS racing_remote_requests(local_id INTEGER PRIMARY KEY,remote_id TEXT UNIQUE NOT NULL);
              CREATE TABLE IF NOT EXISTS racing_redirect_inspections(inspection_attempt INTEGER PRIMARY KEY,original_attempt INTEGER NOT NULL,payload TEXT NOT NULL);
            """
            )
        from .racing_profiles import Profiles

        self.profiles = Profiles(self)

    def admission(self, body):
        origin = os.environ.get("MCP_HK_BOOTSTRAP_URL", "")
        if origin not in {
            "https://mcp-hk.measurable.workers.dev/__ops/snapshot",
            "https://mcp.hk/__ops/snapshot",
        }:
            raise RacingRejected("RACING_ADMISSION_ORIGIN")

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise ValueError("Admission redirects rejected")

        request = urllib.request.Request(
            origin.replace("/snapshot", "/racing/admission"),
            data=canonical(body),
            method="POST",
            headers={
                "Authorization": "Bearer " + os.environ.get("MCP_HK_OPS_TOKEN", ""),
                "Content-Type": "application/json",
                "User-Agent": "mcp.hk-racing-admission/1.0",
            },
        )
        with urllib.request.build_opener(NoRedirect).open(
            request, timeout=20
        ) as response:
            return json.loads(response.read(20000))

    def reserve(self, url):
        local = super().reserve(url)
        if os.environ.get("MCP_HK_EDGE_MODE") != "true":
            return local
        remote = uuid.uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO racing_remote_requests VALUES(?,?)", (local, remote)
            )
        try:
            result = self.admission({"action": "reserve", "id": remote})
        except (OSError, ValueError) as exc:
            super().settled(
                local, "unknown", MAX_PAGE, "RACING_ADMISSION_NOT_CONFIRMED"
            )
            raise RacingRejected("RACING_ADMISSION_NOT_CONFIRMED") from exc
        if result.get("allowed") is not True:
            code = result.get("code", "RACING_ADMISSION_NOT_CONFIRMED")
            super().settled(local, "admission_denied", 0, code)
            with self.connect() as db:
                if code == "RACING_DAILY_BUDGET":
                    db.execute(
                        "INSERT OR REPLACE INTO racing_control VALUES(?,?)",
                        ("budget-until", str((int(time.time() // 86400) + 1) * 86400)),
                    )
                elif code == "RACING_SOURCE_HELD":
                    db.execute(
                        "INSERT OR REPLACE INTO racing_control VALUES(?,?)",
                        ("remote-hold", "true"),
                    )
            raise RacingRejected(code)
        return local

    def settled(self, attempt, state, size, error=None, page=None):
        with self.connect() as db:
            row = db.execute(
                "SELECT remote_id FROM racing_remote_requests WHERE local_id=?",
                (attempt,),
            ).fetchone()
        if row:
            try:
                self.admission(
                    {
                        "action": "settle",
                        "id": row[0],
                        "state": state,
                        "bytes": min(size, MAX_PAGE),
                        "code": error,
                    }
                )
            except (OSError, ValueError) as exc:
                raise RacingRejected("RACING_ADMISSION_NOT_CONFIRMED") from exc
        return super().settled(attempt, state, size, error, page)

    def reconcile_parser_fix(self, attempt, parser_sha256):
        with self.connect() as db:
            remote = db.execute(
                "SELECT r.remote_id,a.error,a.bytes,a.url,a.state FROM racing_remote_requests r JOIN racing_attempts a ON a.id=r.local_id WHERE r.local_id=?",
                (attempt,),
            ).fetchone()
        files = Path(__file__).parent / "curated" / "racing"
        if (
            parser_sha256
            != hashlib.sha256(
                (files / "public_results.py").read_bytes()
                + (files / "normalize.py").read_bytes()
            ).hexdigest()
        ):
            raise RacingRejected("DEVELOPMENT_FIX_CHECKSUM_MISMATCH")
        if remote:
            if remote["state"] != "held" or remote["error"] not in {
                "PUBLIC_RESULTS_LAYOUT_DRIFT",
                "INVALID_RACING_ID",
                "UNKNOWN_RESULT_CODE",
            }:
                raise RacingRejected("DEVELOPMENT_HOLD_NOT_RECONCILABLE")
            self.admission(
                {
                    "action": "settle",
                    "id": remote[0],
                    "state": "reviewed_parser",
                    "bytes": remote["bytes"],
                    "code": remote["error"],
                }
            )
        super().reconcile_parser_fix(attempt, parser_sha256)
        with self.connect() as db:
            original = db.execute(
                "SELECT url FROM racing_attempts WHERE id=?", (attempt,)
            ).fetchone()
            q = {
                k.lower(): v
                for k, v in parse_qs(urlsplit(original["url"]).query).items()
            }
            if "racedate" in q and "racecourse" in q:
                db.execute(
                    "UPDATE racing_queue SET state='partial',error=NULL WHERE day=? AND venue=? AND state='held'",
                    (q["racedate"][0].replace("/", "-"), q["racecourse"][0]),
                )

    def before_source(self):
        with self.connect() as db:
            values = dict(
                db.execute(
                    "SELECT key,value FROM racing_control WHERE key IN ('budget-until','remote-hold')"
                )
            )
        if float(values.get("budget-until", "0")) > time.time():
            return {"state": "budget_wait"}
        if values.get("remote-hold") and os.environ.get("MCP_HK_EDGE_MODE") == "true":
            status = self.admission({"action": "status"})
            if status.get("unresolved"):
                return {"state": "held", "code": "RACING_SOURCE_HELD"}
            with self.connect() as db:
                db.execute("DELETE FROM racing_control WHERE key='remote-hold'")
        return None

    def publish(self, payload):
        payload = dict(validate_snapshot(payload))
        payload.pop("version", None)
        payload.pop("sourceLicence", None)
        payload.pop("publicRedistributionEnabled", None)
        payload["coverage"] = dict(
            payload["coverage"],
            unreportedStatusRows=sum(
                f["status"] == "not_reported"
                for r in payload["races"]
                for f in r["results"]
            ),
            declaredRunnerReconciliation="not_yet_verified",
            seasonComplete=False,
            profileCoverage="identity_from_results_only",
            intradayOddsHistory=False,
        )
        payload.update(
            scope="public_factual_results",
            sourceBasis="HKJC public factual results pages",
        )
        result = super().publish(payload)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO racing_publications VALUES(?,'staged',NULL)",
                (result["version"],),
            )
        return result

    def read(self, version=None, day=None, venue=None):
        with self.connect() as db:
            if version:
                row = db.execute(
                    "SELECT 1 FROM racing_publications WHERE version=? AND state='accepted'",
                    (version,),
                ).fetchone()
                if row is None:
                    raise RacingRejected("RACING_VERSION_NOT_FOUND")
            else:
                row = db.execute(
                    "SELECT version FROM racing_accepted WHERE (? IS NULL OR day=?) AND (? IS NULL OR venue=?) ORDER BY day DESC,venue LIMIT 1",
                    (day, day, venue, venue),
                ).fetchone()
                if row is None:
                    raise RacingRejected("RACING_DATA_NOT_READY")
                version = row[0]
        return super().read(version, day, venue)

    def meetings(self, limit=100, after=None):
        if not 1 <= limit <= 100:
            raise RacingRejected("RACING_INVALID_LIMIT")
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM racing_accepted WHERE (? IS NULL OR meeting<?) ORDER BY day DESC,venue DESC LIMIT ?",
                (after, after, limit + 1),
            ).fetchall()
        return [
            {
                "meeting": {"id": r["meeting"], "date": r["day"], "venue": r["venue"]},
                "version": r["version"],
                "coverage": json.loads(r["coverage"]),
                "observedAt": r["observed"],
            }
            for r in rows[:limit]
        ]

    def pending(self):
        with self.connect() as db:
            row = db.execute(
                "SELECT s.version FROM racing_snapshots s JOIN racing_current c USING(version) LEFT JOIN racing_publications p USING(version) WHERE s.version LIKE 'racing-results-v1-%' AND (p.state IS NULL OR p.state='staged') ORDER BY s.created LIMIT 1"
            ).fetchone()
        return row[0] if row else self.profiles.pending()

    def raw(self, version):
        return ResultsStore.read(self, version)

    def fingerprint(self):
        from .racing_profiles import TABLES as PROFILE_TABLES

        result = {}
        with self.connect() as db:
            for table in (
                "racing_pages",
                "racing_attempts",
                "racing_snapshots",
                "racing_current",
                "racing_publications",
                "racing_accepted",
                "racing_queue",
                "racing_control",
                "racing_calendar",
                "racing_remote_requests",
                "racing_redirect_inspections",
            ) + PROFILE_TABLES:
                digest = hashlib.sha256()
                count = 0
                # SQLite rows are sorted by their canonical serialization, not a sample.
                for raw in sorted(
                    canonical(dict(row)) for row in db.execute("SELECT * FROM " + table)
                ):
                    digest.update(len(raw).to_bytes(8, "big"))
                    digest.update(raw)
                    count += 1
                result[table] = {"rows": count, "sha256": digest.hexdigest()}
        return result

    def accept_restored(self, restored, version, backup_sha256):
        if version.startswith("racing-profile-v1-"):
            return self.profiles.accept(restored.profiles, version, backup_sha256)
        if self.path == restored.path or not re.fullmatch(
            "[a-f0-9]{64}", backup_sha256
        ):
            raise RacingRejected("RACING_INDEPENDENT_RESTORE_REQUIRED")
        source = self.raw(version)
        other = restored.raw(version)
        if source != other or self.fingerprint() != restored.fingerprint():
            raise RacingRejected("RACING_RESTORE_MISMATCH")
        proof = {
            "backupSha256": backup_sha256,
            "version": version,
            "sourceTables": self.fingerprint(),
            "raceCount": len(source["races"]),
            "resultRows": source["coverage"]["resultRows"],
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
        }
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT version FROM racing_current WHERE meeting=?",
                (source["meeting"]["id"],),
            ).fetchone()
            if not current or current[0] != version:
                raise RacingRejected("RACING_CANDIDATE_SUPERSEDED")
            db.execute(
                "UPDATE racing_publications SET state='accepted',proof=? WHERE version=? AND state='staged'",
                (canonical(proof).decode(), version),
            )
            if (
                db.execute(
                    "SELECT state FROM racing_publications WHERE version=?", (version,)
                ).fetchone()[0]
                != "accepted"
            ):
                raise RacingRejected("RACING_CANDIDATE_NOT_STAGED")
            m = source["meeting"]
            db.execute(
                "INSERT OR REPLACE INTO racing_accepted VALUES(?,?,?,?,?,?)",
                (
                    m["id"],
                    m["date"],
                    m["venue"],
                    version,
                    source["observedAt"],
                    canonical(source["coverage"]).decode(),
                ),
            )
            db.execute(
                "UPDATE racing_queue SET state='accepted',error=NULL WHERE day=? AND venue=?",
                (m["date"], m["venue"]),
            )
        return proof

    def import_bundle(self, bundle):
        snapshot = dict(bundle["snapshot"])
        version = snapshot.pop("version")
        if version != "private-results-v1-" + checksum(snapshot):
            raise RacingRejected("RACING_IMPORT_CHECKSUM")
        validate_snapshot(snapshot)
        pages = bundle.get("pages", [])
        attempts = bundle.get("attempts", [])
        if len(pages) > 200 or len(attempts) > 200:
            raise RacingRejected("RACING_IMPORT_LIMIT")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for a in attempts:
                if a["state"] not in {
                    "success",
                    "reviewed_parser",
                    "reviewed_layout",
                    "reviewed_input",
                }:
                    raise RacingRejected("RACING_IMPORT_UNSETTLED")
                source_url(a["url"])
                if not 0 <= a["bytes"] <= MAX_PAGE:
                    raise RacingRejected("RACING_IMPORT_LIMIT")
                if not db.execute(
                    "SELECT 1 FROM racing_attempts WHERE at=? AND url=?",
                    (a["at"], a["url"]),
                ).fetchone():
                    db.execute(
                        "INSERT INTO racing_attempts(at,url,state,bytes,error) VALUES(?,?,?,?,?)",
                        (a["at"], a["url"], a["state"], a["bytes"], a.get("error")),
                    )
            for p in pages:
                result_url(p["url"])
                utc(p["observed"])
                if (
                    not re.fullmatch("[a-f0-9]{64}", p["sha256"])
                    or not 0 < p["bytes"] <= MAX_PAGE
                ):
                    raise RacingRejected("RACING_IMPORT_CAPTURE")
                parsed = json.loads(p["payload"])
                if parsed["meeting"] != snapshot["meeting"]:
                    raise RacingRejected("RACING_IMPORT_CAPTURE")
                db.execute(
                    "INSERT OR IGNORE INTO racing_pages VALUES(?,?,?,?,?)",
                    (p["url"], p["observed"], p["sha256"], p["bytes"], p["payload"]),
                )
        return self.publish(snapshot)

    def enqueue(self, meetings, refresh=False):
        if not 1 <= len(meetings) <= 100:
            raise RacingRejected("RACING_QUEUE_LIMIT")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for m in meetings:
                meeting(m["date"], m["venue"])
                if date.fromisoformat(m["date"]) > datetime.now(timezone.utc).date():
                    raise RacingRejected("COMPLETED_PAST_MEETING_REQUIRED")
                accepted = db.execute(
                    "SELECT 1 FROM racing_accepted WHERE meeting=?",
                    (meeting(m["date"], m["venue"]),),
                ).fetchone()
                if refresh:
                    db.execute(
                        "INSERT INTO racing_queue VALUES(?,?,'refresh',NULL,?) ON CONFLICT(day,venue) DO UPDATE SET state='refresh',error=NULL,updated=excluded.updated",
                        (m["date"], m["venue"], time.time()),
                    )
                else:
                    db.execute(
                        "INSERT OR IGNORE INTO racing_queue VALUES(?,?,?,NULL,?)",
                        (
                            m["date"],
                            m["venue"],
                            "accepted" if accepted else "pending",
                            time.time(),
                        ),
                    )
                if refresh:
                    key = "refresh:" + m["date"] + ":" + m["venue"]
                    db.execute(
                        "INSERT OR REPLACE INTO racing_control VALUES(?,?)",
                        (key, datetime.now(timezone.utc).isoformat()),
                    )

    def queue_dividend_recapture(self):
        """One checkpointed recapture per meeting/parser through the existing queue.

        No reads or accepted-pointer changes. An explicit refresh (including July
        15) or pending recovery takes precedence. Missing tables after this pass
        require changed source/parser evidence, never repeated blind recapture.
        """
        parser = dividend_parser_hash()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if (
                db.execute(
                    "SELECT 1 FROM racing_control WHERE key LIKE 'refresh:%' LIMIT 1"
                ).fetchone()
                or db.execute(
                    "SELECT 1 FROM racing_publications p JOIN racing_current c USING(version) WHERE p.state='staged' LIMIT 1"
                ).fetchone()
                or db.execute(
                    "SELECT 1 FROM racing_profile_versions WHERE state='staged' LIMIT 1"
                ).fetchone()
                or db.execute(
                    "SELECT 1 FROM racing_attempts WHERE state IN ('unknown','reserved','held') LIMIT 1"
                ).fetchone()
            ):
                return {
                    "state": "deferred_existing_owner_or_hold",
                    "providerRequests": 0,
                }
            rows = db.execute(
                "SELECT a.meeting,a.day,a.venue,a.version FROM racing_accepted a JOIN racing_snapshots s USING(version) JOIN racing_queue q ON q.day=a.day AND q.venue=a.venue WHERE q.state='accepted' AND EXISTS(SELECT 1 FROM json_each(s.payload,'$.races') r WHERE coalesce(json_extract(r.value,'$.dividends.state'),'not_extracted')<>'observed') AND NOT EXISTS(SELECT 1 FROM racing_control c WHERE c.key='dividend-recapture:'||a.meeting AND c.value=?) ORDER BY (a.day BETWEEN '2025-09-01' AND '2026-08-31') DESC,a.day,a.venue LIMIT 1",
                (parser,),
            ).fetchall()
            if not rows:
                return {"state": "unchanged", "providerRequests": 0}
            row = rows[0]
            db.execute(
                "UPDATE racing_queue SET state='refresh',error=NULL,updated=? WHERE day=? AND venue=? AND state='accepted'",
                (time.time(), row["day"], row["venue"]),
            )
            db.execute(
                "INSERT INTO racing_control VALUES(?,?)",
                (
                    "refresh:" + row["day"] + ":" + row["venue"],
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO racing_control VALUES(?,?)",
                ("dividend-recapture:" + row["meeting"], parser),
            )
            return {
                "state": "queued",
                "meeting": row["meeting"],
                "baseVersion": row["version"],
                "parserSha256": parser,
                "providerRequests": 0,
                "acceptedPointerChanged": False,
            }

    def calendar(self, year, month, client=None):
        if (
            not 1970 <= year <= datetime.now(timezone.utc).year + 1
            or not 1 <= month <= 12
        ):
            raise RacingRejected("RACING_FIXTURE_PERIOD")
        period = f"{year:04d}-{month:02d}"
        parsed, receipt = CalendarCollector(self, refresh=True).month(
            year, month, client
        )
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO racing_calendar VALUES(?,?,?,?,?)",
                (
                    period,
                    receipt["observed"],
                    parsed["state"],
                    canonical(parsed).decode(),
                    canonical(receipt).decode(),
                ),
            )
        eligible = [
            m
            for m in parsed["meetings"]
            if date.fromisoformat(m["date"]) < datetime.now(timezone.utc).date()
            and m["plannedRaces"] > 0
        ]
        if eligible:
            self.enqueue(eligible)
        # Recheck only the two most recent accepted meetings within fourteen days.
        # The persisted refresh cutoff prevents mixing old and newly fetched locales.
        now = datetime.now(timezone.utc)
        for accepted in self.meetings(limit=2):
            m = accepted["meeting"]
            if (now - utc(accepted["observedAt"])).total_seconds() >= 86400 and 0 <= (
                now.date() - date.fromisoformat(m["date"])
            ).days <= 14:
                with self.connect() as db:
                    job = db.execute(
                        "SELECT state FROM racing_queue WHERE day=? AND venue=?",
                        (m["date"], m["venue"]),
                    ).fetchone()
                if not job or job["state"] in {"accepted", "staged"}:
                    self.enqueue([m], True)
        return {
            "period": period,
            "state": parsed["state"],
            "sourceMeetings": len(parsed["meetings"]),
            "eligibleMeetings": len(eligible),
        }

    def discover_due(self, client=None):
        now = datetime.now(timezone.utc)
        period = now.strftime("%Y-%m")
        with self.connect() as db:
            previous = db.execute(
                "SELECT observed,payload FROM racing_calendar WHERE period=?", (period,)
            ).fetchone()
        if previous and (now - utc(previous["observed"])).total_seconds() < 86400:
            eligible = [
                m
                for m in json.loads(previous["payload"])["meetings"]
                if date.fromisoformat(m["date"]) < now.date() and m["plannedRaces"] > 0
            ]
            if eligible:
                self.enqueue(eligible)
            return {"state": "unchanged"}
        return self.calendar(now.year, now.month, client)

    def advance(self, max_requests=1, client=None):
        blocked = self.before_source()
        if blocked:
            return blocked
        with self.connect() as db:
            job = db.execute(
                "SELECT * FROM racing_queue WHERE state IN ('pending','partial','refresh') ORDER BY day DESC,venue LIMIT 1"
            ).fetchone()
        if not job:
            return {"state": "unchanged"}
        try:
            key = "refresh:" + job["day"] + ":" + job["venue"]
            with self.connect() as db:
                refresh = db.execute(
                    "SELECT value FROM racing_control WHERE key=?", (key,)
                ).fetchone()
            collector = PilotCollector(
                self,
                client,
                max_requests=max_requests,
                refresh_after=refresh[0] if refresh else None,
            )
            snapshot = collector.collect(job["day"], job["venue"])
            state, error = "staged", None
            result = {
                "state": state,
                "version": snapshot["version"],
                "requests": collector.attempts,
            }
            with self.connect() as db:
                if refresh:
                    # An existing explicit refresh already exercises this parser;
                    # do not schedule a duplicate recapture after it completes.
                    db.execute(
                        "INSERT OR REPLACE INTO racing_control VALUES(?,?)",
                        (
                            "dividend-recapture:" + meeting(job["day"], job["venue"]),
                            dividend_parser_hash(),
                        ),
                    )
                db.execute("DELETE FROM racing_control WHERE key=?", (key,))
        except RacingRejected as exc:
            error = str(exc)
            state = (
                "partial"
                if error
                in {
                    "DEVELOPMENT_RUN_BUDGET",
                    "DEVELOPMENT_DAILY_BUDGET",
                    "RACING_DAILY_BUDGET",
                    "RACING_SOURCE_HELD",
                }
                else "held"
            )
            result = {"state": state, "code": error}
        with self.connect() as db:
            db.execute(
                "UPDATE racing_queue SET state=?,error=?,updated=? WHERE day=? AND venue=?",
                (state, error, time.time(), job["day"], job["venue"]),
            )
        return result
