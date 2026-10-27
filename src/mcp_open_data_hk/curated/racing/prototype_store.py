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

from .policy import RacingRejected, canonical, checksum, utc
from .public_results import parse_results, result_url, archive_redirect

MAX_PAGE = 400 * 1024


class ResultsStore:
    version_prefix = "private-results-v1-"

    def __init__(self, filename):
        self.path = Path(filename).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = {
                r[0]
                for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            for suffix in ("pages", "attempts", "snapshots", "current"):
                old, new = "prototype_" + suffix, "racing_" + suffix
                if old in existing:
                    if new in existing:
                        raise RacingRejected("RACING_NAMESPACE_CONFLICT")
                    db.execute(f"ALTER TABLE {old} RENAME TO {new}")
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS racing_pages(
                    url TEXT PRIMARY KEY, observed TEXT NOT NULL,
                    sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS racing_attempts(
                    id INTEGER PRIMARY KEY, at REAL NOT NULL, url TEXT NOT NULL,
                    state TEXT NOT NULL, bytes INTEGER NOT NULL DEFAULT 409600,
                    error TEXT);
                CREATE TABLE IF NOT EXISTS racing_snapshots(
                    version TEXT PRIMARY KEY, meeting TEXT NOT NULL,
                    created TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS racing_current(
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
            + Path(__file__).with_name("normalize.py").read_bytes()
        ).hexdigest()
        if parser_sha256 != actual:
            raise RacingRejected("DEVELOPMENT_FIX_CHECKSUM_MISMATCH")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE racing_attempts SET state='reviewed_parser',error=error||? WHERE id=? AND state='held' AND error IN ('PUBLIC_RESULTS_LAYOUT_DRIFT','INVALID_RACING_ID','UNKNOWN_RESULT_CODE')",
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
                "SELECT * FROM racing_pages WHERE url=?", (url,)
            ).fetchone()
        return dict(row) if row else None

    def reserve(self, url):
        now = time.time()
        day = int(now // 86400) * 86400
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM racing_attempts WHERE state IN ('reserved','held','unknown') LIMIT 1"
            ).fetchone():
                raise RacingRejected("DEVELOPMENT_SOURCE_HELD")
            count, size = db.execute(
                "SELECT count(*),coalesce(sum(bytes),0) FROM racing_attempts WHERE at>=? AND state<>'admission_denied'",
                (day,),
            ).fetchone()
            if count >= 200 or size + MAX_PAGE > 64 * 1024 * 1024:
                raise RacingRejected("DEVELOPMENT_DAILY_BUDGET")
            cur = db.execute(
                "INSERT INTO racing_attempts(at,url,state) VALUES(?,?,'reserved')",
                (now, url),
            )
            return cur.lastrowid

    def settled(self, attempt, state, size, error=None, page=None):
        with self.connect() as db:
            db.execute(
                "UPDATE racing_attempts SET state=?,bytes=?,error=? WHERE id=?",
                (state, size, error, attempt),
            )
            if page:
                db.execute(
                    "INSERT OR REPLACE INTO racing_pages VALUES(?,?,?,?,?)", page
                )

    def publish(self, payload):
        if len(canonical(payload)) > 2 * 1024 * 1024:
            raise RacingRejected("DEVELOPMENT_OUTPUT_LIMIT")
        version = self.version_prefix + checksum(payload)
        payload = dict(payload, version=version)
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO racing_snapshots VALUES(?,?,?,?)",
                (
                    version,
                    payload["meeting"]["id"],
                    payload["observedAt"],
                    canonical(payload).decode(),
                ),
            )
            db.execute(
                "INSERT OR REPLACE INTO racing_current VALUES(?,?)",
                (payload["meeting"]["id"], version),
            )
        return payload

    def read(self, version=None, day=None, venue=None):
        with self.connect() as db:
            if version:
                row = db.execute(
                    "SELECT payload FROM racing_snapshots WHERE version=?",
                    (version,),
                ).fetchone()
            else:
                rows = db.execute(
                    "SELECT s.payload FROM racing_snapshots s JOIN racing_current c ON s.version=c.version ORDER BY s.created DESC LIMIT 100"
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
        if found_version != self.version_prefix + checksum(original):
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
                "SELECT s.payload FROM racing_snapshots s JOIN racing_current c ON s.version=c.version ORDER BY s.created DESC LIMIT 100"
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


PrototypeStore = ResultsStore


class PilotCollector:
    validate_url = staticmethod(result_url)
    parse_page = staticmethod(parse_results)

    def __init__(
        self,
        store,
        client=None,
        refresh=False,
        max_requests=40,
        max_seconds=600,
        refresh_after=None,
    ):
        self.store = store
        self.client = client
        self.refresh = refresh
        self.max_requests = min(40, max_requests)
        self.max_seconds = min(600, max_seconds)
        self.refresh_after = refresh_after or (
            datetime.now(timezone.utc).isoformat() if refresh else None
        )
        self.attempts = self.bytes = 0
        self.started = time.monotonic()

    def fetch(self, url, client, archive_hop=False):
        self.validate_url(url)
        cached = self.store.page(url)
        if cached and (
            not self.refresh_after or utc(cached["observed"]) >= utc(self.refresh_after)
        ):
            parsed = json.loads(cached["payload"])
            if parsed.get("kind") == "qualified_archive_redirect":
                if archive_hop:
                    raise RacingRejected("RACING_ARCHIVE_REDIRECT_REJECTED")
                target = archive_redirect(url, parsed["target"])
                return self.fetch(target, client, archive_hop=True)
            return parsed, {
                k: cached[k] for k in ("url", "observed", "sha256", "bytes")
            }
        if (
            self.attempts >= self.max_requests
            or self.bytes + MAX_PAGE > 16 * 1024 * 1024
            or time.monotonic() - self.started >= self.max_seconds
        ):
            raise RacingRejected("DEVELOPMENT_RUN_BUDGET")
        attempt = self.store.reserve(url)
        self.attempts += 1
        raw = bytearray()
        redirect = None
        try:
            with client.stream("GET", url, follow_redirects=False) as response:
                if response.status_code == 302 and not archive_hop:
                    try:
                        redirect = archive_redirect(
                            url, response.headers.get("location")
                        )
                    except RacingRejected:
                        pass
                if response.status_code != 200 and redirect is None:
                    self.store.settled(
                        attempt, "held", MAX_PAGE, "HTTP_" + str(response.status_code)
                    )
                    raise RacingRejected(
                        "DEVELOPMENT_HTTP_" + str(response.status_code)
                    )
                if (
                    redirect is None
                    and "text/html"
                    not in response.headers.get("content-type", "").lower()
                ):
                    raise RacingRejected("DEVELOPMENT_CONTENT_TYPE")
                for chunk in response.iter_bytes(chunk_size=16384):
                    raw.extend(chunk)
                    if len(raw) > MAX_PAGE:
                        raise RacingRejected("RESULT_BODY_LIMIT")
            parsed = (
                {
                    "kind": "qualified_archive_redirect",
                    "target": redirect,
                    "locationSha256": hashlib.sha256(
                        response.headers["location"].encode()
                    ).hexdigest(),
                }
                if redirect
                else self.parse_page(raw.decode("utf-8"), url)
            )
            if not redirect and "race" in parsed:
                from .dividends import candidate

                parsed["race"]["dividendCandidate"] = candidate(
                    raw.decode("utf-8"),
                    parsed["race"]["id"],
                    "zhHant" if "/zh-hk/" in url else "en",
                )
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
            error="QUALIFIED_ARCHIVE_REDIRECT" if redirect else None,
            page=(url, observed, digest, len(raw), canonical(parsed).decode()),
        )
        self.bytes += len(raw)
        # Only factual parsed fields and source checksum persist, never page commentary/media.
        time.sleep(1)
        if redirect:
            return self.fetch(redirect, client, archive_hop=True)
        return parsed, {
            "url": url,
            "observed": observed,
            "sha256": digest,
            "bytes": len(raw),
        }

    def collect(self, day, venue):
        if (
            venue not in {"ST", "HV"}
            or date.fromisoformat(day) > datetime.now(timezone.utc).date()
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
                timeout=15,
                follow_redirects=False,
                headers={"User-Agent": "mcp.hk-racing/1.0"},
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
                left, right = dict(en["race"]), zh["race"]
                from .dividends import qualified_pair

                left["dividends"] = qualified_pair(
                    left.pop("dividendCandidate", None), right.get("dividendCandidate")
                )
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
