"""Private, resumable factual-results pilot. Independent of production source grants."""

import fcntl
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path

import httpx

from .policy import RacingRejected, canonical, checksum
from .public_results import parse_results, result_url

MAX_PAGE = 400 * 1024


class PrototypeStore:
    def __init__(self, filename):
        self.path = Path(filename).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS prototype_pages(
                    url TEXT PRIMARY KEY, observed TEXT NOT NULL,
                    sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prototype_attempts(
                    id INTEGER PRIMARY KEY, at REAL NOT NULL, url TEXT NOT NULL,
                    state TEXT NOT NULL, bytes INTEGER NOT NULL DEFAULT 409600,
                    error TEXT);
                CREATE TABLE IF NOT EXISTS prototype_snapshots(
                    version TEXT PRIMARY KEY, meeting TEXT NOT NULL,
                    created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS prototype_current(
                    meeting TEXT PRIMARY KEY, version TEXT NOT NULL);
            """
            )
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def reconcile_parser_fix(self, attempt, parser_sha256):
        """Reconcile a known completed-response parser failure; never HTTP/unknown holds."""
        actual = hashlib.sha256(
            Path(__file__).with_name("public_results.py").read_bytes()
        ).hexdigest()
        if parser_sha256 != actual:
            raise RacingRejected("DEVELOPMENT_FIX_CHECKSUM_MISMATCH")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE prototype_attempts SET state='reviewed_parser',error=error||? WHERE id=? AND state='held' AND error IN ('PUBLIC_RESULTS_LAYOUT_DRIFT','INVALID_RACING_ID')",
                ("; reviewed parser correction:" + parser_sha256, attempt),
            ).rowcount
            if changed != 1:
                raise RacingRejected("DEVELOPMENT_HOLD_NOT_RECONCILABLE")

    @contextmanager
    def collector_lock(self):
        with self.path.with_suffix(".collector.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RacingRejected("DEVELOPMENT_COLLECTOR_BUSY") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def page(self, url):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM prototype_pages WHERE url=?", (url,)
            ).fetchone()
        return dict(row) if row else None

    def reserve(self, url):
        now = time.time()
        day = int(now // 86400) * 86400
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM prototype_attempts WHERE state IN ('reserved','held','unknown') LIMIT 1"
            ).fetchone():
                raise RacingRejected("DEVELOPMENT_SOURCE_HELD")
            count, size = db.execute(
                "SELECT count(*),coalesce(sum(bytes),0) FROM prototype_attempts WHERE at>=?",
                (day,),
            ).fetchone()
            if count >= 200 or size + MAX_PAGE > 64 * 1024 * 1024:
                raise RacingRejected("DEVELOPMENT_DAILY_BUDGET")
            cur = db.execute(
                "INSERT INTO prototype_attempts(at,url,state) VALUES(?,?,'reserved')",
                (now, url),
            )
            return cur.lastrowid

    def settled(self, attempt, state, size, error=None, page=None):
        with self.connect() as db:
            db.execute(
                "UPDATE prototype_attempts SET state=?,bytes=?,error=? WHERE id=?",
                (state, size, error, attempt),
            )
            if page:
                db.execute(
                    "INSERT OR REPLACE INTO prototype_pages VALUES(?,?,?,?,?)", page
                )

    def publish(self, payload):
        if len(canonical(payload)) > 2 * 1024 * 1024:
            raise RacingRejected("DEVELOPMENT_OUTPUT_LIMIT")
        version = "private-results-v1-" + checksum(payload)
        payload = dict(payload, version=version)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO prototype_snapshots VALUES(?,?,?,?)",
                (
                    version,
                    payload["meeting"]["id"],
                    payload["observedAt"],
                    canonical(payload).decode(),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO prototype_current VALUES(?,?)",
                (payload["meeting"]["id"], version),
            )
        return payload

    def read(self, version=None, day=None, venue=None):
        with self.connect() as db:
            if version:
                row = db.execute(
                    "SELECT payload FROM prototype_snapshots WHERE version=?",
                    (version,),
                ).fetchone()
            else:
                rows = db.execute(
                    "SELECT s.payload FROM prototype_snapshots s JOIN prototype_current c ON s.version=c.version ORDER BY s.created DESC LIMIT 100"
                ).fetchall()
                row = next(
                    (
                        r
                        for r in rows
                        if (not day or json.loads(r[0])["meeting"]["date"] == day)
                        and (not venue or json.loads(r[0])["meeting"]["venue"] == venue)
                    ),
                    None,
                )
        if not row:
            raise RacingRejected("DEVELOPMENT_SNAPSHOT_NOT_FOUND")
        payload = json.loads(row[0])
        original = dict(payload)
        found_version = original.pop("version")
        if found_version != "private-results-v1-" + checksum(original):
            raise RacingRejected("DEVELOPMENT_SNAPSHOT_CHECKSUM_MISMATCH")
        if (
            day
            and payload["meeting"]["date"] != day
            or venue
            and payload["meeting"]["venue"] != venue
        ):
            raise RacingRejected("DEVELOPMENT_SNAPSHOT_NOT_FOUND")
        return payload

    def meetings(self):
        with self.connect() as db:
            rows = db.execute(
                "SELECT s.payload FROM prototype_snapshots s JOIN prototype_current c ON s.version=c.version ORDER BY s.created DESC LIMIT 100"
            ).fetchall()
        return [
            {
                "meeting": p["meeting"],
                "version": p["version"],
                "coverage": p["coverage"],
                "observedAt": p["observedAt"],
            }
            for row in rows
            for p in [json.loads(row[0])]
        ]


class PilotCollector:
    def __init__(self, store, client=None, refresh=False):
        self.store = store
        self.client = client
        self.refresh = refresh
        self.attempts = self.bytes = 0
        self.started = time.monotonic()

    def fetch(self, url, client):
        result_url(url)
        cached = self.store.page(url)
        if cached and not self.refresh:
            return json.loads(cached["payload"]), {
                k: cached[k] for k in ("url", "observed", "sha256", "bytes")
            }
        if (
            self.attempts >= 40
            or self.bytes + MAX_PAGE > 16 * 1024 * 1024
            or time.monotonic() - self.started >= 600
        ):
            raise RacingRejected("DEVELOPMENT_RUN_BUDGET")
        attempt = self.store.reserve(url)
        self.attempts += 1
        raw = bytearray()
        try:
            with client.stream("GET", url) as response:
                if response.status_code != 200:
                    self.store.settled(
                        attempt, "held", MAX_PAGE, "HTTP_" + str(response.status_code)
                    )
                    raise RacingRejected(
                        "DEVELOPMENT_HTTP_" + str(response.status_code)
                    )
                if "text/html" not in response.headers.get("content-type", "").lower():
                    raise RacingRejected("DEVELOPMENT_CONTENT_TYPE")
                for chunk in response.iter_bytes(chunk_size=16384):
                    raw.extend(chunk)
                    if len(raw) > MAX_PAGE:
                        raise RacingRejected("RESULT_BODY_LIMIT")
            parsed = parse_results(raw.decode("utf-8"), url)
        except RacingRejected as exc:
            self.store.settled(attempt, "held", MAX_PAGE, str(exc))
            raise
        except (httpx.HTTPError, UnicodeError) as exc:
            self.store.settled(attempt, "unknown", MAX_PAGE, type(exc).__name__)
            raise RacingRejected("DEVELOPMENT_REQUEST_UNKNOWN") from exc
        observed = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(raw).hexdigest()
        self.store.settled(
            attempt,
            "success",
            len(raw),
            page=(url, observed, digest, len(raw), canonical(parsed).decode()),
        )
        self.bytes += len(raw)
        # Only factual parsed fields and source checksum persist, never page commentary/media.
        time.sleep(1)
        return parsed, {
            "url": url,
            "observed": observed,
            "sha256": digest,
            "bytes": len(raw),
        }

    def collect(self, day, venue):
        if (
            venue not in {"ST", "HV"}
            or date.fromisoformat(day) >= datetime.now(timezone.utc).date()
        ):
            raise RacingRejected("COMPLETED_PAST_MEETING_REQUIRED")
        base = (
            "https://racing.hkjc.com/en-us/local/information/localresults?racedate="
            + day.replace("-", "/")
            + "&Racecourse="
            + venue
        )
        with (
            self.store.collector_lock(),
            self.client
            or httpx.Client(
                timeout=40,
                follow_redirects=False,
                headers={"User-Agent": "mcp.hk-private-development/1.0"},
            ) as client,
        ):
            first, receipt = self.fetch(base, client)
            if first["meeting"]["venue"] != venue:
                raise RacingRejected("MEETING_IDENTITY_MISMATCH")
            inventory = first["inventory"]
            expected = sorted(map(int, inventory))
            races, captures = [], [receipt]
            for number in expected:
                url = inventory.get(str(number), inventory.get(number))
                en, capture = (
                    (first, receipt)
                    if number == first["race"]["number"]
                    else self.fetch(url, client)
                )
                if (
                    en["meeting"] != first["meeting"]
                    or sorted(map(int, en["inventory"])) != expected
                    or en["race"]["number"] != number
                ):
                    raise RacingRejected("DEVELOPMENT_MEETING_INVENTORY_DRIFT")
                zh, translated = self.fetch(url.replace("/en-us/", "/zh-hk/"), client)
                if (
                    zh["meeting"] != en["meeting"]
                    or sorted(map(int, zh["inventory"])) != expected
                    or zh["race"]["id"] != en["race"]["id"]
                ):
                    raise RacingRejected("BILINGUAL_MEETING_MISMATCH")
                left, right = en["race"], zh["race"]
                a = {r["participantId"]: r for r in left["results"]}
                b = {r["participantId"]: r for r in right["results"]}
                fields = (
                    "horseNumber",
                    "draw",
                    "placing",
                    "status",
                    "deadHeat",
                    "timeSeconds",
                    "weightLb",
                    "bodyWeightLb",
                    "winOddsFinal",
                )
                if set(a) != set(b) or any(
                    any(a[k][f] != b[k][f] for f in fields) for k in a
                ):
                    raise RacingRejected("BILINGUAL_FACT_MISMATCH")
                for key in a:
                    for kind in ("horse", "jockey", "trainer"):
                        if a[key][kind]["id"] != b[key][kind]["id"]:
                            raise RacingRejected("BILINGUAL_IDENTITY_MISMATCH")
                        a[key][kind]["nameZhHant"] = b[key][kind]["name"]
                    a[key].pop("revision")
                    a[key]["revision"] = checksum(a[key])
                left["nameZhHant"] = right["name"]
                left["goingZhHant"] = right["goingRaw"]
                left["courseZhHant"] = right["courseRaw"]
                left["provenance"] = [capture, translated]
                races.append(left)
                captures.extend([capture, translated])
            unique = {r["url"]: r for r in captures}
            payload = {
                "scope": "private_development",
                "sourceLicence": "unverified",
                "publicRedistributionEnabled": False,
                "meeting": first["meeting"],
                "races": races,
                "provenance": list(unique.values()),
                "observedAt": max(r["observed"] for r in unique.values()),
                "coverage": {
                    "expectedRaces": len(expected),
                    "observedRaces": len(races),
                    "resultRows": sum(len(r["results"]) for r in races),
                    "resultRaceInventoryComplete": True,
                    "declaredRunnerReconciliation": "not_yet_verified",
                    "seasonComplete": False,
                    "profileCoverage": "identity_from_results_only",
                    "intradayOddsHistory": False,
                },
            }
            return self.store.publish(payload)
