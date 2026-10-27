"""Read-only reconciliation of the original company inventory, not publication."""

import hashlib
import json
import os
import re

from psycopg.rows import dict_row

from .build import connect

BASELINE_SHA256 = "6cd172c5f30142adb43c1ca51295800c37629066133835d22a7fcc7bdd118f54"
SOURCE_KEYS_SHA256 = "48ecc65094f222c99acb3a930f8036a38fd15bad9fa94f51d68369125458a8fe"
SOURCE = re.compile(
    r"https://www\.cr\.gov\.hk/docs/wrpt/RNC063/RNC063([LF])_([0-9]{8})\.csv"
)


def reconcile(baseline, rows, version):
    keys = baseline["sourceKeys"]
    keys_sha256 = hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()
    if (
        baseline["sha256"] != BASELINE_SHA256
        or len(keys) != 188
        or len(set(keys)) != 188
        or any(not SOURCE.fullmatch(k) for k in keys)
        or keys_sha256 != SOURCE_KEYS_SHA256
    ):
        raise ValueError("ORIGINAL_COMPANY_INVENTORY_REQUIRED")
    pairs = {}
    for key in keys:
        match = SOURCE.fullmatch(key)
        pairs.setdefault(match[2], set()).add(match[1])
    if len(pairs) != 94 or any(registers != {"L", "F"} for registers in pairs.values()):
        raise ValueError("ORIGINAL_COMPANY_PAIRS_REQUIRED")
    by_key = {}
    for row in rows:
        if row["sourceKey"] in by_key:
            raise ValueError("DUPLICATE_COMPANY_SOURCE_KEY")
        by_key[row["sourceKey"]] = row
    issues, published, qualified = [], 0, 0
    cases = []
    for key in sorted(keys):
        row = by_key.get(key)
        if row is None:
            issues.append({"sourceKey": key, "code": "MISSING_ORIGINAL_SOURCE_KEY"})
            continue
        receipt = row.get("receipt") or {}
        valid = (
            row.get("valid") is True
            and row.get("captureId")
            and row.get("transformSha256")
            and receipt.get("sourceUrl") == key
            and receipt.get("independentXlsVerified") is True
            and receipt.get("verificationSha256")
            and type(receipt.get("rowCount")) is int
            and receipt["rowCount"] == row.get("storedRows")
            and receipt.get("sha256") == row.get("rawSha256")
        )
        if not valid:
            issues.append({"sourceKey": key, "code": "SOURCE_CAPTURE_UNQUALIFIED"})
        else:
            qualified += 1
        accepted = valid and row.get("publishedCaptureId") == row["captureId"]
        published += bool(accepted)
        cases.append(
            {
                **row,
                "register": "local" if SOURCE.fullmatch(key)[1] == "L" else "foreign",
                "week": SOURCE.fullmatch(key)[2],
                "published": bool(accepted),
                "version": version if accepted else None,
                "liveVerification": "pending",
            }
        )
    return {
        "baselineSha256": baseline["sha256"],
        "sourceKeysSha256": keys_sha256,
        "originalPairs": 94,
        "originalFiles": 188,
        "qualifiedFiles": qualified,
        "publishedQualifiedFiles": published,
        "acceptedVersion": version,
        "inventoryPublicationPassed": bool(version)
        and qualified == published == 188
        and not issues,
        "restMcpBrowserDownloadAcceptancePassed": False,
        "freshAcceptedBackupRestorePassed": False,
        "issues": issues,
        "newSourceKeys": sorted(set(by_key) - set(keys)),
        "cases": cases,
    }


def snapshot(conn):
    # A coherent pointer/capture/record membership view, even across publication.
    with conn.transaction():
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        baseline = conn.execute(
            "SELECT state FROM curated.official_source_state WHERE family='inventory_baseline'"
        ).fetchone()["state"]
        pointer = conn.execute(
            "SELECT version FROM curated.official_pointer"
        ).fetchone()
        version = pointer["version"] if pointer else None
        rows = conn.execute(
            """SELECT i.source_key AS "sourceKey",coalesce(s.capture_id,m.capture_id) AS "captureId",m.capture_id AS "publishedCaptureId",c.valid,c.sha256 AS "rawSha256",c.transform_sha256 AS "transformSha256",c.receipt,(SELECT count(*) FROM curated.official_records r WHERE r.capture_id=c.capture_id) AS "storedRows",(SELECT r.record FROM curated.official_records r WHERE r.capture_id=c.capture_id ORDER BY r.fact_id LIMIT 1) AS "sampleRecord" FROM curated.official_inventory i LEFT JOIN curated.official_staged s USING(source_key) LEFT JOIN curated.official_members m ON m.version=%s AND m.source_key=i.source_key LEFT JOIN curated.official_captures c ON c.capture_id=coalesce(s.capture_id,m.capture_id) ORDER BY i.source_key""",
            (version,),
        ).fetchall()
        return reconcile(baseline, rows, version)


def main():
    # SELECT-only environment. No source fetch, backup, publish or schedule action.
    with connect(
        os.environ["CURATED_DSN"],
        row_factory=dict_row,
        options="-c default_transaction_read_only=on -c statement_timeout=30000 -c lock_timeout=250",
    ) as conn:
        print(json.dumps(snapshot(conn), ensure_ascii=False))


if __name__ == "__main__":
    main()
