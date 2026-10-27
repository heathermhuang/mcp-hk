"""Local, bounded acceptance journal shared by existing qualification owners.

No collection, schedule, publication or automatic retry is performed here. A
changed accepted version creates a separate journal; evidence is never relabelled.
"""

import csv
import fcntl
import hashlib
import io
import json
import re
import sqlite3
import time
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .official_acceptance import BASELINE_SHA256, SOURCE_KEYS_SHA256, SOURCE

COMPANY_STEPS = (
    "rest",
    "mcp",
    "browser_en",
    "browser_zh-Hant",
    "browser_zip_en",
    "browser_zip_zh-Hant",
)


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def company_plan(cohort):
    """Pin only a reconciled accepted cohort, never a staged count or old matrix."""
    cases = cohort["cases"]
    keys = [r["sourceKey"] for r in cases]
    version = cohort["acceptedVersion"]
    if (
        cohort.get("baselineSha256") != BASELINE_SHA256
        or cohort.get("sourceKeysSha256") != SOURCE_KEYS_SHA256
        or cohort.get("inventoryPublicationPassed") is not True
        or not re.fullmatch(r"official-[a-f0-9]{32}", version or "")
        or len(keys) != 188
        or len(set(keys)) != 188
        or sha(json.dumps(sorted(keys)).encode()) != SOURCE_KEYS_SHA256
        or any(not SOURCE.fullmatch(key) for key in keys)
    ):
        raise ValueError("FULL_ACCEPTED_ORIGINAL_COHORT_REQUIRED")
    result = []
    for case in sorted(cases, key=lambda r: r["sourceKey"]):
        if (
            not case["published"]
            or case["version"] != version
            or case["captureId"] != case["publishedCaptureId"]
            or not case.get("sampleRecord")
        ):
            raise ValueError("ACCEPTED_EVIDENCE_RECORD_REQUIRED")
        result.append(
            {
                "id": case["sourceKey"],
                "captureId": case["captureId"],
                "expected": case["sampleRecord"],
                "steps": list(COMPANY_STEPS),
            }
        )
    return {"version": version, "cases": result, "sourceKeysSha256": SOURCE_KEYS_SHA256}


class Journal:
    """Single-owner local proof journal; interrupted steps remain unknown/charged.

    A verifier returns paths to actual receipts, which are hashed before success.
    Failed/unknown work requires an explicit reviewed retry, never a scheduler loop.
    """

    def __init__(self, filename, plan):
        self.path = Path(filename)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.plan = plan
        self.plan_sha = sha(canonical(plan))
        with self.connect() as db:
            db.executescript(
                "CREATE TABLE IF NOT EXISTS identity(sha TEXT PRIMARY KEY);"
                "CREATE TABLE IF NOT EXISTS attempts("
                "id INTEGER PRIMARY KEY,case_id TEXT,step TEXT,state TEXT,"
                "at TEXT,receipt TEXT,code TEXT);"
            )
            old = db.execute("SELECT sha FROM identity").fetchone()
            if old and old[0] != self.plan_sha:
                raise ValueError("ACCEPTANCE_PLAN_CHANGED_USE_NEW_JOURNAL")
            db.execute("INSERT OR IGNORE INTO identity VALUES(?)", (self.plan_sha,))
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=0.25)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def owner(self):
        with self.path.with_suffix(".lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ValueError("ACCEPTANCE_OWNER_BUSY") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def pending(self):
        with self.connect() as db:
            settled = {
                (r[0], r[1]): r[2]
                for r in db.execute(
                    "SELECT case_id,step,state FROM attempts ORDER BY id"
                )
            }
        return [
            (case, step)
            for case in self.plan["cases"]
            for step in case["steps"]
            if settled.get((case["id"], step), "ready") == "ready"
        ]

    def reopen(self, case_id, step, review):
        """Explicit post-investigation retry; preserve the original failure/unknown."""
        if (
            not review.get("reason")
            or not re.fullmatch(r"[a-f0-9]{40}", review.get("correctedRelease", ""))
            or not re.fullmatch(r"[a-f0-9]{64}", review.get("evidenceSha256", ""))
        ):
            raise ValueError("ACCEPTANCE_REVIEW_REQUIRED")
        with self.owner(), self.connect() as db:
            previous = db.execute(
                "SELECT id,state FROM attempts WHERE case_id=? AND step=? ORDER BY id DESC LIMIT 1",
                (case_id, step),
            ).fetchone()
            if not previous or previous[1] not in {"failed", "unknown"}:
                raise ValueError("ACCEPTANCE_FAILED_ATTEMPT_REQUIRED")
            db.execute(
                "INSERT INTO attempts(case_id,step,state,at,receipt) VALUES(?,?,'ready',?,?)",
                (
                    case_id,
                    step,
                    datetime.now(timezone.utc).isoformat(),
                    json.dumps(dict(review, previousAttempt=previous[0])),
                ),
            )

    def run(self, verify, *, limit=4, seconds=90, steps=None):
        if type(limit) is not int or not 1 <= limit <= 20 or not 0 < seconds <= 580:
            raise ValueError("ACCEPTANCE_BATCH_BOUND_REQUIRED")
        started, completed = time.monotonic(), 0
        with self.owner():
            pending = [
                (case, step)
                for case, step in self.pending()
                if steps is None or step in steps
            ]
            for case, step in pending[:limit]:
                if time.monotonic() - started >= seconds:
                    break
                with self.connect() as db:
                    key = db.execute(
                        "INSERT INTO attempts(case_id,step,state,at) VALUES(?,?,'unknown',?)",
                        (case["id"], step, datetime.now(timezone.utc).isoformat()),
                    ).lastrowid
                try:
                    # The callback must enforce its own request/browser deadline.
                    paths = verify(case, step, self.plan["version"])
                    if not paths:
                        raise ValueError("ACCEPTANCE_RECEIPT_REQUIRED")
                    artifacts = [
                        {
                            "path": str(Path(p).resolve()),
                            "sha256": sha(Path(p).read_bytes()),
                        }
                        for p in paths
                    ]
                except Exception:
                    with self.connect() as db:
                        db.execute(
                            "UPDATE attempts SET state='failed',code='VERIFICATION_FAILED' WHERE id=?",
                            (key,),
                        )
                    # Stop at the first changed failure; no retry of unchanged work.
                    raise
                with self.connect() as db:
                    db.execute(
                        "UPDATE attempts SET state='passed',receipt=? WHERE id=?",
                        (json.dumps(artifacts), key),
                    )
                completed += 1
        return {"completedSteps": completed, "unattemptedSteps": len(self.pending())}

    def summary(self):
        with self.connect() as db:
            counts = dict(
                db.execute(
                    "SELECT state,count(*) FROM attempts WHERE id IN (SELECT max(id) FROM attempts GROUP BY case_id,step) GROUP BY state"
                )
            )
        required = sum(len(c["steps"]) for c in self.plan["cases"])
        return {
            "version": self.plan["version"],
            "planSha256": self.plan_sha,
            "requiredSteps": required,
            "states": counts,
            "allRequiredStepsPassed": counts.get("passed", 0) == required,
        }


def verify_company_record(envelope, case, version):
    if envelope.get("meta", {}).get("version") != version:
        raise ValueError("ACCEPTANCE_VERSION_MISMATCH")
    if envelope["meta"].get("view") != "latest_observed":
        raise ValueError("ACCEPTANCE_VIEW_MISMATCH")
    expected = case["expected"]
    data = envelope["data"]
    rows = data.get("observations", data.get("items", []))
    matches = [r for r in rows if r.get("fact_id") == expected["fact_id"]]
    if len(matches) != 1 or matches[0] != expected:
        raise ValueError("ACCEPTANCE_FACT_OR_LINEAGE_MISMATCH")
    return True


def verify_page_zip(raw, envelope, selection):
    """Verify bytes from an actual download against its exact captured live page.

    This verifies package contents only. The browser runner separately supplies
    visible-action evidence; a locally generated ZIP is never browser acceptance.
    """
    if len(raw) > 17 * 1024**2:
        raise ValueError("ACCEPTANCE_ZIP_LIMIT")
    expected_names = {
        "records.json",
        "records.csv",
        "schema.json",
        "provenance.json",
        "NOTICE.txt",
        "manifest.json",
    }
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        entries = archive.infolist()
        if (
            {e.filename for e in entries} != expected_names
            or len(entries) != len(expected_names)
            or sum(e.file_size for e in entries) > 16 * 1024**2
            or any(e.flag_bits & 1 for e in entries)
        ):
            raise ValueError("ACCEPTANCE_ZIP_MEMBERS")
        files = {e.filename: archive.read(e) for e in entries}
    manifest = json.loads(files["manifest.json"])
    rows = envelope["data"]["items"]
    if (
        manifest.get("version") != envelope["meta"]["version"]
        or manifest.get("view") != envelope["meta"].get("view", "archive")
        or manifest.get("scope") != "this_page"
        or manifest.get("currentVerification") is not False
        or manifest.get("selection") != selection
        or manifest.get("rowCount") != len(rows)
        or not rows
        or json.loads(files["records.json"]) != rows
        or json.loads(files["provenance.json"])
        != {k: envelope[k] for k in ("meta", "provenance", "warnings")}
    ):
        raise ValueError("ACCEPTANCE_ZIP_PAGE_MISMATCH")
    members = manifest["files"]
    if (
        len(members) != 5
        or {m["file"] for m in members} != expected_names - {"manifest.json"}
        or any(
            m["bytes"] != len(files[m["file"]]) or m["sha256"] != sha(files[m["file"]])
            for m in members
        )
    ):
        raise ValueError("ACCEPTANCE_ZIP_HASH_MISMATCH")
    schema = json.loads(files["schema.json"])
    columns = [c["name"] for c in schema["columns"]]
    if len(columns) != len(set(columns)) or set(columns) != set().union(*rows):
        raise ValueError("ACCEPTANCE_ZIP_SCHEMA_MISMATCH")

    def json_type(value):
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        return {str: "string", dict: "object", list: "array", float: "number"}[
            type(value)
        ]

    if (
        any(
            c.get("jsonTypes") != sorted({json_type(r.get(c["name"])) for r in rows})
            for c in schema["columns"]
        )
        or schema.get("csv", {}).get("encoding") != "UTF-8 with BOM"
        or schema["csv"].get("null") != "empty cell"
        or schema["csv"].get("nestedValues") != "JSON text"
        or not schema["csv"].get("spreadsheetTextEscape")
        or not files["records.csv"].startswith(b"\xef\xbb\xbf")
    ):
        raise ValueError("ACCEPTANCE_ZIP_SCHEMA_TYPES_OR_ENCODING")
    csv_rows = list(csv.reader(io.StringIO(files["records.csv"].decode("utf-8-sig"))))
    if not csv_rows or csv_rows[0] != columns or len(csv_rows) != len(rows) + 1:
        raise ValueError("ACCEPTANCE_ZIP_CSV_ROWS")
    for actual, row in zip(csv_rows[1:], rows):
        if len(actual) != len(columns):
            raise ValueError("ACCEPTANCE_ZIP_CSV_COLUMNS")
        for column, cell in zip(columns, actual):
            value = row.get(column)
            if isinstance(value, (dict, list)):
                equal = json.loads(cell) == value
            elif value is None:
                equal = cell == ""
            else:
                expected = str(value).lower() if isinstance(value, bool) else str(value)
                if isinstance(value, str) and (
                    re.match(r"^[\s\x00-\x1f\x7f-\x9f\u200b-\u200f]*[=+\-@]", value)
                    or re.fullmatch(r"0\d+", value)
                ):
                    expected = "'" + expected
                equal = cell == expected
            if not equal:
                raise ValueError("ACCEPTANCE_ZIP_CSV_VALUE")
    if not files["NOTICE.txt"].strip():
        raise ValueError("ACCEPTANCE_ZIP_NOTICE")
    return {
        "zipSha256": sha(raw),
        "bytes": len(raw),
        "rows": len(rows),
        "members": members,
    }
