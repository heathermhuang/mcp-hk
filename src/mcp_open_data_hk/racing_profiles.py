"""Versioned professional observations on the existing racing SQLite/R2 path."""

import base64
import binascii
import hashlib
import hmac
import json
import csv
import io
import zipfile
import re
import secrets
import shutil
import time
from datetime import datetime, timezone
from importlib.resources import files

import httpx

from .curated.racing.policy import (
    RacingRejected,
    canonical,
    checksum,
    utc,
    require,
    validate_policy,
)
from .curated.racing.profiles import (
    parse_profile,
    merge_profiles,
    profile_url,
    profile_selection,
    normalize_retained_observation,
)
from .curated.racing.prototype_store import MAX_PAGE

TABLES = (
    "racing_profile_versions",
    "racing_profile_current",
    "racing_profile_queue",
    "racing_profile_meta",
)
VERSION = r"racing-profile-v1-[a-f0-9]{64}"


def transform_hash():
    return hashlib.sha256(
        files("mcp_open_data_hk.curated.racing").joinpath("profiles.py").read_bytes()
    ).hexdigest()


def required_scratch_bytes():
    # This store runs on the existing 8 GB gateway, separately from PostgreSQL.
    # Reserve a maximum SQLite backup copy, packed transfer and isolated restore.
    from .operations import MAX_DATABASE, MAX_BACKUP, MAX_RESTORE

    return MAX_DATABASE + MAX_BACKUP + MAX_RESTORE


class Profiles:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript(
                """
            CREATE TABLE IF NOT EXISTS racing_profile_versions(version TEXT PRIMARY KEY,kind TEXT NOT NULL,source_id TEXT NOT NULL,base_version TEXT,created REAL NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,proof TEXT);
            CREATE TABLE IF NOT EXISTS racing_profile_current(kind TEXT,source_id TEXT,version TEXT NOT NULL,PRIMARY KEY(kind,source_id));
            CREATE TABLE IF NOT EXISTS racing_profile_queue(kind TEXT,source_id TEXT,last_seen TEXT NOT NULL,last_attempt REAL,last_success REAL,next_due REAL NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending',refresh_after TEXT,pending_version TEXT,error TEXT,PRIMARY KEY(kind,source_id));
            CREATE INDEX IF NOT EXISTS racing_profile_due ON racing_profile_queue(next_due,last_seen);
            CREATE TABLE IF NOT EXISTS racing_profile_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            """
            )
            db.execute(
                "INSERT OR IGNORE INTO racing_profile_meta VALUES('cursor_secret',?)",
                (secrets.token_hex(32),),
            )

    def install_policy(self, record, pinned):
        validate_policy(record)
        if (
            checksum(record) != pinned
            or len(canonical(record)) > 32768
            or set(record["families"]) != {"profiles"}
        ):
            raise RacingRejected("PROFILE_POLICY_REJECTED")
        with self.store.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO racing_profile_meta VALUES(?,?)",
                ("policy:" + pinned, canonical(record).decode()),
            )
            db.execute(
                "INSERT OR REPLACE INTO racing_profile_meta VALUES('policy',?)",
                (canonical({"record": record, "sha256": pinned}).decode(),),
            )

    def require(self, mode, url=None):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT value FROM racing_profile_meta WHERE key='policy'"
            ).fetchone()
        if not row:
            raise RacingRejected("SOURCE_MODE_UNQUALIFIED")
        value = json.loads(row[0])
        route = url.split("?", 1)[0] if url else None
        return require(
            value["record"],
            value["sha256"],
            "profiles",
            mode,
            route=route,
            fields=("professional_attributes", "displayed_form_history"),
        )

    def scheduled(self):
        try:
            self.require("schedule")
            self.require("collect")
            return True
        except RacingRejected:
            return False

    def seed(self):
        with self.store.connect() as db:
            accepted = db.execute(
                "SELECT a.meeting,a.day,a.version,s.payload FROM racing_accepted a JOIN racing_snapshots s USING(version) ORDER BY a.meeting"
            ).fetchall()
            identity = checksum([[r["meeting"], r["version"]] for r in accepted])
            previous = db.execute(
                "SELECT value FROM racing_profile_meta WHERE key='seed' "
            ).fetchone()
            if previous and previous[0] == identity:
                return
            for row in accepted:
                for race in json.loads(row["payload"])["races"]:
                    for result in race["results"]:
                        for kind in ("horse", "jockey", "trainer"):
                            source_id = result[kind]["sourceId"]
                            try:
                                profile_url(kind, source_id)
                                state, error = "pending", None
                            except RacingRejected:
                                state, error = "held", "INVALID_PROFILE_ID"
                            db.execute(
                                "INSERT INTO racing_profile_queue(kind,source_id,last_seen,state,error) VALUES(?,?,?,?,?) ON CONFLICT(kind,source_id) DO UPDATE SET last_seen=max(last_seen,excluded.last_seen)",
                                (kind, source_id, row["day"], state, error),
                            )
            db.execute(
                "INSERT OR REPLACE INTO racing_profile_meta VALUES('seed',?)",
                (identity,),
            )

    def stage(self, observations, captures):
        self.require("collect")
        self.require("cache")
        self.require("history")
        self.seed()
        if len(observations) != 2 or len(captures) != 2:
            raise RacingRejected("PROFILE_BILINGUAL_CAPTURE_REQUIRED")
        input_hashes = {o["language"]: o["factsSha256"] for o in observations}
        observations = [normalize_retained_observation(o) for o in observations]
        english = next((r for r in observations if r.get("language") == "en-us"), None)
        chinese = next((r for r in observations if r.get("language") == "zh-hk"), None)
        if not english or not chinese:
            raise RacingRejected("PROFILE_BILINGUAL_CAPTURE_REQUIRED")
        for observed, capture in zip(observations, captures):
            from .curated.racing.profiles import validate_observation

            validate_observation(observed)
            kind, source_id, lang = profile_selection(capture["url"])
            if (
                set(capture) != {"url", "observed", "sha256", "bytes"}
                or (kind, source_id, lang)
                != (observed["kind"], observed["sourceId"], observed["language"])
                or capture["url"] != observed["sourceUrl"]
                or capture["observed"] != observed["observedAt"]
                or not re.fullmatch("[a-f0-9]{64}", capture["sha256"])
                or type(capture["bytes"]) is not int
                or not 0 < capture["bytes"] <= MAX_PAGE
                or utc(observed["observedAt"]) > datetime.now(timezone.utc)
            ):
                raise RacingRejected("PROFILE_CAPTURE_IDENTITY")
            fact = {
                k: v
                for k, v in observed.items()
                if k
                not in {
                    "observedAt",
                    "effectiveAt",
                    "sourceUrl",
                    "factsSha256",
                    "coverage",
                }
            }
            if checksum(fact) != observed["factsSha256"]:
                raise RacingRejected("PROFILE_FACT_CHECKSUM")
        merged = merge_profiles(english, chinese)
        kind, source_id = merged["kind"], merged["sourceId"]
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            queued = db.execute(
                "SELECT state,pending_version FROM racing_profile_queue WHERE kind=? AND source_id=?",
                (kind, source_id),
            ).fetchone()
            if not queued or queued["state"] == "held":
                raise RacingRejected("PROFILE_OUTSIDE_ACCEPTED_COHORT")
            current = db.execute(
                "SELECT version FROM racing_profile_current WHERE kind=? AND source_id=?",
                (kind, source_id),
            ).fetchone()
            if current:
                old = db.execute(
                    "SELECT payload FROM racing_profile_versions WHERE version=?",
                    (current[0],),
                ).fetchone()
                if any(
                    utc(merged["observations"][lang])
                    < utc(json.loads(old[0])["observations"][lang])
                    for lang in ("en", "zhHant")
                ):
                    raise RacingRejected("PROFILE_OBSERVATION_REGRESSION")
                if json.loads(old[0])["factsSha256"] == merged["factsSha256"]:
                    if queued["pending_version"]:
                        raise RacingRejected("PROFILE_CANDIDATE_PENDING")
                    db.execute(
                        "UPDATE racing_profile_queue SET state='available',last_success=?,next_due=?,refresh_after=NULL,error=NULL WHERE kind=? AND source_id=?",
                        (time.time(), time.time() + 30 * 86400, kind, source_id),
                    )
                    return {"state": "unchanged", "version": current[0]}
            payload = dict(
                merged,
                provenance=captures,
                transformSha256=transform_hash(),
                transformBasis="validated_normalized_observation_v1",
                inputFactsSha256=input_hashes,
                rawParseTransformSha256=None,
                sourceBasis="public_professional_profile_facts",
                policySha256=json.loads(
                    db.execute(
                        "SELECT value FROM racing_profile_meta WHERE key='policy'"
                    ).fetchone()[0]
                )["sha256"],
            )
            if len(canonical(payload)) > 2 * 1024 * 1024:
                raise RacingRejected("PROFILE_OUTPUT_LIMIT")
            version = "racing-profile-v1-" + checksum(payload)
            used = db.execute(
                "SELECT coalesce(sum(length(CAST(payload AS BLOB))),0) FROM racing_profile_versions"
            ).fetchone()[0]
            exists = db.execute(
                "SELECT 1 FROM racing_profile_versions WHERE version=?", (version,)
            ).fetchone()
            if not exists and (
                used + len(canonical(payload)) > 32 * 1024 * 1024
                or shutil.disk_usage(self.store.path.parent).free
                < required_scratch_bytes()
            ):
                raise RacingRejected("PROFILE_GROWTH_CAPACITY_HOLD")
            if queued["pending_version"] and queued["pending_version"] != version:
                raise RacingRejected("PROFILE_CANDIDATE_PENDING")
            db.execute(
                "INSERT OR IGNORE INTO racing_profile_versions VALUES(?,?,?,?,?,?,'staged',NULL)",
                (
                    version,
                    kind,
                    source_id,
                    current[0] if current else None,
                    time.time(),
                    canonical(payload).decode(),
                ),
            )
            db.execute(
                "UPDATE racing_profile_queue SET state='staged',pending_version=? WHERE kind=? AND source_id=?",
                (version, kind, source_id),
            )
        return {"state": "staged", "version": version}

    def pending(self):
        with self.store.connect() as db:
            row = db.execute(
                "SELECT version FROM racing_profile_versions WHERE state='staged' ORDER BY created LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def raw(self, version):
        if not isinstance(version, str) or not re.fullmatch(VERSION, version):
            raise RacingRejected("INVALID_PROFILE_VERSION")
        with self.store.connect() as db:
            row = db.execute(
                "SELECT * FROM racing_profile_versions WHERE version=?", (version,)
            ).fetchone()
        if not row:
            raise RacingRejected("PROFILE_NOT_FOUND")
        if version != "racing-profile-v1-" + checksum(json.loads(row["payload"])):
            raise RacingRejected("PROFILE_CONTENT_MISMATCH")
        return dict(row)

    def accept(self, restored, version, backup_sha):
        self.require("cache")
        self.require("history")
        self.require("rest")
        row, other = self.raw(version), restored.raw(version)
        if (
            self.store.path == restored.store.path
            or not re.fullmatch("[a-f0-9]{64}", backup_sha)
            or row != other
            or self.store.fingerprint() != restored.store.fingerprint()
        ):
            raise RacingRejected("RACING_RESTORE_MISMATCH")
        proof = {
            "version": version,
            "backupSha256": backup_sha,
            "sourceTables": self.store.fingerprint(),
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
        }
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT version FROM racing_profile_current WHERE kind=? AND source_id=?",
                (row["kind"], row["source_id"]),
            ).fetchone()
            queued = db.execute(
                "SELECT pending_version FROM racing_profile_queue WHERE kind=? AND source_id=?",
                (row["kind"], row["source_id"]),
            ).fetchone()
            if (
                row["state"] != "staged"
                or (current[0] if current else None) != row["base_version"]
                or not queued
                or queued[0] != version
            ):
                raise RacingRejected("PROFILE_CANDIDATE_SUPERSEDED")
            db.execute(
                "UPDATE racing_profile_versions SET state='accepted',proof=? WHERE version=?",
                (canonical(proof).decode(), version),
            )
            db.execute(
                "INSERT OR REPLACE INTO racing_profile_current VALUES(?,?,?)",
                (row["kind"], row["source_id"], version),
            )
            db.execute(
                "UPDATE racing_profile_queue SET state='available',last_success=?,next_due=?,refresh_after=NULL,pending_version=NULL,error=NULL WHERE kind=? AND source_id=?",
                (time.time(), time.time() + 30 * 86400, row["kind"], row["source_id"]),
            )
        return proof

    def read(self, kind, source_id, version=None, mode="rest"):
        grant = self.require(mode)
        profile_url(kind, source_id)
        if version is None:
            with self.store.connect() as db:
                current = db.execute(
                    "SELECT version FROM racing_profile_current WHERE kind=? AND source_id=?",
                    (kind, source_id),
                ).fetchone()
            if not current:
                raise RacingRejected("PROFILE_NOT_FOUND")
            version = current[0]
        row = self.raw(version)
        if (
            row["state"] != "accepted"
            or not row["proof"]
            or (row["kind"], row["source_id"]) != (kind, source_id)
        ):
            raise RacingRejected("PROFILE_NOT_FOUND")
        payload = json.loads(row["payload"])
        if any(
            time.time() - utc(observed).timestamp() > grant["retentionSeconds"]
            for observed in payload["observations"].values()
        ):
            raise RacingRejected("SOURCE_RETENTION_EXPIRED")
        if json.loads(row["proof"]).get("version") != version:
            raise RacingRejected("PROFILE_CONTENT_MISMATCH")
        # History is paginated separately; this detail remains bounded.
        data = {k: v for k, v in payload.items() if k != "formHistory"}
        return {
            "data": data,
            "meta": {
                "version": version,
                "view": "profile_observation",
                "currentValuesAppliedToPastRaces": False,
            },
            "coverage": payload["coverage"],
        }

    def history(
        self,
        kind,
        source_id,
        version=None,
        limit=20,
        cursor=None,
        language="en",
        mode="rest",
    ):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise RacingRejected("INVALID_PROFILE_LIMIT")
        if language not in {"en", "zhHant"}:
            raise RacingRejected("INVALID_PROFILE_LANGUAGE")
        with self.store.connect() as db:
            secret = (
                db.execute(
                    "SELECT value FROM racing_profile_meta WHERE key='cursor_secret'"
                )
                .fetchone()[0]
                .encode()
            )
        offset = 0
        if cursor:
            try:
                if (
                    not isinstance(cursor, str)
                    or len(cursor) > 2048
                    or not re.fullmatch("[A-Za-z0-9_-]+", cursor)
                ):
                    raise ValueError()
                raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                body, signature = raw[:-32], raw[-32:]
                if not hmac.compare_digest(
                    hmac.digest(secret, body, "sha256"), signature
                ):
                    raise ValueError()
                value = json.loads(body)
                if (
                    value["kind"] != kind
                    or value["sourceId"] != source_id
                    or value["language"] != language
                    or version
                    and value["version"] != version
                    or type(value["expires"]) is not int
                    or value["expires"] < time.time()
                ):
                    raise ValueError()
                version, offset = value["version"], value["offset"]
                if type(offset) is not int or offset < 0:
                    raise ValueError()
            except (ValueError, KeyError, TypeError, binascii.Error):
                raise RacingRejected("INVALID_PROFILE_CURSOR") from None
        selected = self.read(kind, source_id, version, mode)
        row = self.raw(selected["meta"]["version"])
        rows = json.loads(row["payload"])["formHistory"][language]
        data = rows[offset : offset + limit]
        token = None
        if offset + limit < len(rows):
            body = canonical(
                {
                    "kind": kind,
                    "sourceId": source_id,
                    "version": row["version"],
                    "language": language,
                    "offset": offset + limit,
                    "expires": (
                        value["expires"] if cursor else int(time.time()) + 172800
                    ),
                }
            )
            token = (
                base64.urlsafe_b64encode(body + hmac.digest(secret, body, "sha256"))
                .decode()
                .rstrip("=")
            )
        return {
            "data": {"items": data},
            "meta": {
                "version": row["version"],
                "language": language,
                "nextCursor": token,
                "returnedCount": len(data),
                "scope": "profile_displayed_form_history",
            },
            "coverage": selected["coverage"],
        }

    def status(self):
        with self.store.connect() as db:
            state = {
                "cohortSource": "exact participants in accepted results",
                "refreshAfterDays": 30,
                "guaranteedWholeCohortCycleDays": None,
                "queue": [
                    dict(r)
                    for r in db.execute(
                        "SELECT kind,state,count(*) AS participants FROM racing_profile_queue GROUP BY kind,state"
                    )
                ],
                "accepted": db.execute(
                    "SELECT count(*) FROM racing_profile_current"
                ).fetchone()[0],
                "historyBeforeFirstObservationInferred": False,
            }
        free = shutil.disk_usage(self.store.path.parent).free
        required = required_scratch_bytes()
        state["scratchCapacity"] = {
            "freeBytes": free,
            "requiredBytes": required,
            "sufficient": free >= required,
            "basis": "gateway_backup_copy_packed_transfer_and_isolated_restore",
        }
        state["modes"] = {}
        for mode in ("rest", "mcp", "browser", "export", "schedule"):
            try:
                self.require(mode)
                state["modes"][mode] = True
            except RacingRejected:
                state["modes"][mode] = False
        state["available"] = bool(state["accepted"] and state["modes"]["rest"])
        return state

    def archive(
        self, kind, source_id, version=None, language="en", limit=20, cursor=None
    ):
        self.require("export")
        detail = self.read(kind, source_id, version)
        page = self.history(
            kind, source_id, detail["meta"]["version"], limit, cursor, language
        )
        text = io.StringIO(newline="")
        writer = csv.writer(text, quoting=csv.QUOTE_ALL, lineterminator="\n")
        writer.writerow(["sourceAnnualIndex", "raceId", "date", "sourceFields"])
        for row in page["data"]["items"]:
            identity = row["race"] or {}
            values = [
                row["sourceAnnualIndex"],
                identity.get("raceId", ""),
                identity.get("date", ""),
                json.dumps(row["fields"], ensure_ascii=False, sort_keys=True),
            ]
            writer.writerow(
                [
                    (
                        "'" + v
                        if v.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                        else v
                    )
                    for v in values
                ]
            )
        members = {
            "profile.json": canonical(detail),
            "history.json": canonical(page),
            "history.csv": text.getvalue().encode("utf-8-sig"),
            "schema.json": canonical(
                {
                    "schema": "racing-profile-export-v1",
                    "identifiers": "HKJC source IDs retained as strings; sourceAnnualIndex is not a global race ID",
                    "attributes": "sourceLabel and raw preserve the displayed fact; value is a decimal string, count object, or null when not qualified",
                    "currency": "HKD only with an explicit HK$/HKD source marker; a bare dollar sign has unknown currency",
                    "dates": "observed UTC is separate from source statistics cutoff; absent effective/import-date interpretation stays null",
                    "history": "only the selected source-displayed form page; race identity comes from an exact source link; current profile attributes never backfill historical races",
                }
            ),
            "NOTICE.txt": b"Source: Hong Kong Jockey Club public professional profile facts. Independent mcp.hk dataset; no endorsement. This archive contains one profile observation and the selected history page, not a complete career. Current values do not amend past races. No biography, contact details or media.\n",
        }
        members["manifest.json"] = canonical(
            {
                "version": detail["meta"]["version"],
                "participantId": detail["data"]["participantId"],
                "language": language,
                "scope": "profile_and_selected_history_page",
                "historyRows": len(page["data"]["items"]),
                "files": {
                    name: {
                        "bytes": len(body),
                        "sha256": hashlib.sha256(body).hexdigest(),
                    }
                    for name, body in members.items()
                },
            }
        )
        if sum(map(len, members.values())) > 2 * 1024 * 1024:
            raise RacingRejected("PROFILE_OUTPUT_LIMIT")
        packed = io.BytesIO()
        with zipfile.ZipFile(packed, "w", zipfile.ZIP_DEFLATED) as output:
            for name, body in sorted(members.items()):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                output.writestr(info, body)
        return packed.getvalue()

    def collect(self, max_requests=1, client=None):
        self.require("collect")
        if type(max_requests) is not int or not 1 <= max_requests <= 40:
            raise RacingRejected("PROFILE_REQUEST_LIMIT")
        self.seed()
        with self.store.connect() as db:
            target = db.execute(
                "SELECT * FROM racing_profile_queue WHERE state IN ('pending','partial','available') AND next_due<=? ORDER BY last_success IS NOT NULL,last_seen DESC,kind,source_id LIMIT 1",
                (time.time(),),
            ).fetchone()
            if not target:
                return {"state": "unchanged"}
            target = dict(target)
            if not target["refresh_after"]:
                target["refresh_after"] = datetime.now(timezone.utc).isoformat()
                db.execute(
                    "UPDATE racing_profile_queue SET refresh_after=?,last_attempt=? WHERE kind=? AND source_id=?",
                    (
                        target["refresh_after"],
                        time.time(),
                        target["kind"],
                        target["source_id"],
                    ),
                )
        captures = []
        observations = []
        reads = 0
        retry_at = 0
        try:
            with (
                self.store.collector_lock(),
                client
                or httpx.Client(
                    timeout=15, trust_env=False, follow_redirects=False
                ) as transport,
            ):
                for lang in ("en-us", "zh-hk"):
                    url = profile_url(target["kind"], target["source_id"], lang)
                    cached = self.store.page(url)
                    grant = self.require("collect", url)
                    parsed = json.loads(cached["payload"]) if cached else None
                    if (
                        not cached
                        or utc(cached["observed"]) < utc(target["refresh_after"])
                        or parsed.get("transformSha256") != transform_hash()
                    ):
                        if reads >= max_requests:
                            raise RacingRejected("PROFILE_PARTIAL_BUDGET")
                        with self.store.connect() as db:
                            last = (
                                db.execute(
                                    "SELECT max(at) FROM racing_attempts"
                                ).fetchone()[0]
                                or 0
                            )
                        gap = last + grant["minIntervalSeconds"] - time.time()
                        if gap > 10:
                            retry_at = time.time() + gap
                            raise RacingRejected("PROFILE_INTERVAL_WAIT")
                        if gap > 0:
                            time.sleep(gap)
                        attempt = self.store.reserve(url)
                        reads += 1
                        body = bytearray()
                        try:
                            with transport.stream(
                                "GET",
                                url,
                                headers={
                                    "Accept-Encoding": "identity",
                                    "User-Agent": "mcp.hk-racing/1.0",
                                },
                            ) as response:
                                for chunk in response.iter_bytes(chunk_size=32768):
                                    body.extend(chunk)
                                    if len(body) > MAX_PAGE:
                                        raise RacingRejected("PROFILE_BODY_LIMIT")
                                if response.status_code in {403, 429}:
                                    self.store.settled(
                                        attempt,
                                        "held",
                                        len(body),
                                        "SOURCE_HTTP_" + str(response.status_code),
                                    )
                                    attempt = None
                                    raise RacingRejected("RACING_SOURCE_HELD")
                                if response.status_code != 200:
                                    self.store.settled(
                                        attempt,
                                        "success",
                                        len(body),
                                        "PROFILE_HTTP_" + str(response.status_code),
                                    )
                                    attempt = None
                                    retry_at = time.time() + 86400
                                    raise RacingRejected("PROFILE_SOURCE_UNAVAILABLE")
                                if (
                                    "text/html"
                                    not in response.headers.get(
                                        "content-type", ""
                                    ).lower()
                                ):
                                    self.store.settled(
                                        attempt,
                                        "success",
                                        len(body),
                                        "PROFILE_CONTENT_TYPE",
                                    )
                                    attempt = None
                                    raise RacingRejected("PROFILE_CONTENT_TYPE")
                                observed = datetime.now(timezone.utc).isoformat()
                                try:
                                    profile = parse_profile(
                                        body.decode("utf-8"), url, observed
                                    )
                                except (ValueError, UnicodeError) as error:
                                    self.store.settled(
                                        attempt,
                                        "success",
                                        len(body),
                                        "PROFILE_PARSE_REJECTED",
                                    )
                                    attempt = None
                                    raise RacingRejected(
                                        "PROFILE_PARSE_REJECTED"
                                    ) from error
                                parsed = {
                                    "profile": profile,
                                    "transformSha256": transform_hash(),
                                }
                                rawsha = hashlib.sha256(body).hexdigest()
                                self.store.settled(
                                    attempt,
                                    "success",
                                    len(body),
                                    None,
                                    (
                                        url,
                                        observed,
                                        rawsha,
                                        len(body),
                                        canonical(parsed).decode(),
                                    ),
                                )
                                attempt = None
                                cached = self.store.page(url)
                        except Exception:
                            if attempt is not None:
                                self.store.settled(
                                    attempt,
                                    "unknown",
                                    MAX_PAGE,
                                    "PROFILE_REQUEST_UNCERTAIN",
                                )
                            raise
                    observations.append(parsed["profile"])
                    captures.append(
                        {k: cached[k] for k in ("url", "observed", "sha256", "bytes")}
                    )
                return self.stage(observations, captures)
        except (RacingRejected, httpx.HTTPError) as error:
            code = (
                str(error)
                if isinstance(error, RacingRejected)
                else "PROFILE_NETWORK_UNKNOWN"
            )
            state = (
                "partial"
                if code
                in {
                    "PROFILE_PARTIAL_BUDGET",
                    "RACING_DAILY_BUDGET",
                    "RACING_SOURCE_HELD",
                    "DEVELOPMENT_DAILY_BUDGET",
                    "DEVELOPMENT_SOURCE_HELD",
                    "PROFILE_INTERVAL_WAIT",
                    "PROFILE_SOURCE_UNAVAILABLE",
                }
                else "held"
            )
            with self.store.connect() as db:
                db.execute(
                    "UPDATE racing_profile_queue SET state=?,error=?,next_due=? WHERE kind=? AND source_id=?",
                    (state, code, retry_at, target["kind"], target["source_id"]),
                )
            return {"state": state, "code": code, "requests": reads}
