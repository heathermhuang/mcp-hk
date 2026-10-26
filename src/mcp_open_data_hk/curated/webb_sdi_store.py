"""Source-scoped loading, full logical restore and atomic Webb archive acceptance."""

import hashlib
import json
from datetime import date
from importlib.resources import files
from pathlib import Path

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .build import connect
from .normalize import search_key
from .security import safe_reader_role
from .webb_sdi_source import ARCHIVE_SHA, DATA_SHA, TABLES, canonical

LOCK = 0x57454242534449
DB_TABLES = (
    "versions",
    "accepted",
    "issues",
    "filings",
    "capacities",
    "events",
    "dictionaries",
)
NOTICE_SHA = "a81aeeee21c0f3c1eae7185822a64dbf65513a1c1b212c591d9431e0f1ab02fe"


def migrate(dsn):
    ddl = (
        files("mcp_open_data_hk.curated")
        .joinpath("migrations/005_webb_sdi_archive.sql")
        .read_text()
    )
    with connect(dsn) as c:
        if c.execute("SELECT 1 FROM pg_namespace WHERE nspname='webb_sdi'").fetchone():
            ddl = ddl.replace("CREATE SCHEMA IF NOT EXISTS webb_sdi;", "")
        c.execute(ddl)


def rows(directory, table):
    with (directory / (table + ".ndjson")).open() as stream:
        for line in stream:
            yield json.loads(line)


def day(value):
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def stage(dsn, directory):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if (
        manifest["archiveSha256"] != ARCHIVE_SHA
        or manifest["sourceDataSha256"] != DATA_SHA
        or manifest["noticeSha256"] != NOTICE_SHA
        or hashlib.sha256((directory / "NOTICE.txt").read_bytes()).hexdigest()
        != NOTICE_SHA
    ):
        raise ValueError("ORIGINAL_RELEASE_LINEAGE_REQUIRED")
    if (
        (directory / "FAILED.json").exists()
        or manifest["orphanCapacityParentIds"]
        or manifest["orphanEventParentIds"]
    ):
        raise ValueError("INCOMPLETE_SOURCE_PROJECTION")
    # Verify every projected byte before admitting rows, never just a row sample.
    for table in TABLES:
        h, count = hashlib.sha256(), 0
        with (directory / (table + ".ndjson")).open("rb") as stream:
            for line in stream:
                h.update(line)
                count += 1
        if (
            count != manifest["tables"][table]["rows"]
            or h.hexdigest() != manifest["tables"][table]["sha256"]
        ):
            raise ValueError("PROJECTION_CHECKSUM_MISMATCH")
    version = manifest["version"]
    manifest.update(
        attribution="David Webb / Webb-site, original openly released Enigma archive",
        view="webb_sdi_archive",
        currentVerification=False,
        sourceNotice="webb-site-NOTICE.txt",
        numericOriginalPrecisionRecovered=False,
        filingDateKnown=False,
        publicationDateKnown=False,
    )
    issues = {r["ID1"]: r for r in rows(directory, "issue")}
    with connect(
        dsn,
        row_factory=dict_row,
        options="-c statement_timeout=600000 -c lock_timeout=5000",
    ) as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        c.execute(
            "INSERT INTO webb_sdi.versions(version,state,manifest) VALUES(%s,'staging',%s)",
            (version, Jsonb(manifest)),
        )
        with c.cursor().copy(
            "COPY webb_sdi.issues(version,id,issuer_id,source) FROM STDIN"
        ) as copy:
            for r in issues.values():
                copy.write_row((version, int(r["ID1"]), int(r["issuer"]), Jsonb(r)))
        with c.cursor().copy(
            "COPY webb_sdi.filings(version,id,serial,legacy_filing,issue_id,issuer_id,stock_code,issuer_name,issuer_search_key,event_date,signed_date,source) FROM STDIN"
        ) as copy:
            for r in rows(directory, "sdi"):
                issue = issues[r["issueID"]]
                copy.write_row(
                    (
                        version,
                        int(r["ID"]),
                        r["serNo"],
                        r["filing"],
                        int(r["issueID"]),
                        int(issue["issuer"]),
                        r["stockCode"].zfill(5),
                        r["stockName"],
                        search_key(r["stockName"]),
                        day(r["relDate"]),
                        day(r["signDate"]),
                        Jsonb(r),
                    )
                )
        with c.cursor().copy(
            "COPY webb_sdi.capacities(version,filing_id,code,position_code,shares) FROM STDIN"
        ) as copy:
            for r in rows(directory, "sdicap"):
                copy.write_row(
                    (version, int(r["sdiID"]), r["capID"], r["posType"], r["shares"])
                )
        with c.cursor().copy(
            "COPY webb_sdi.events(version,filing_id,position_code,source) FROM STDIN"
        ) as copy:
            for r in rows(directory, "sdievent"):
                copy.write_row((version, int(r["sdiID"]), r["posType"], Jsonb(r)))
        with c.cursor().copy(
            "COPY webb_sdi.dictionaries(version,family,code,label,source) FROM STDIN"
        ) as copy:
            for table, label in (
                ("capacity", "capLong"),
                ("sdireason", "rsnLng"),
                ("currencies", "currency"),
            ):
                for r in rows(directory, table):
                    copy.write_row((version, table, r["ID"], r[label], Jsonb(r)))
        counts = {}
        for table in DB_TABLES[2:]:
            counts[table] = c.execute(
                sql.SQL(
                    "SELECT count(*) AS n FROM webb_sdi.{} WHERE version=%s"
                ).format(sql.Identifier(table)),
                (version,),
            ).fetchone()["n"]
        expected = {
            "issues": manifest["tables"]["issue"]["rows"],
            "filings": manifest["tables"]["sdi"]["rows"],
            "capacities": manifest["tables"]["sdicap"]["rows"],
            "events": manifest["tables"]["sdievent"]["rows"],
            "dictionaries": sum(
                manifest["tables"][t]["rows"]
                for t in ("capacity", "sdireason", "currencies")
            ),
        }
        if counts != expected:
            raise ValueError("DATABASE_CENSUS_MISMATCH")
        manifest["databaseCounts"] = counts
        manifest["issuerCount"] = c.execute(
            "SELECT count(DISTINCT issuer_id) AS n FROM webb_sdi.filings WHERE version=%s",
            (version,),
        ).fetchone()["n"]
        manifest["stockCodeQualification"] = (
            "Numeric source stock codes are left-zero-padded to five digits for query/display; original source_stock_code is retained. Codes are not permanent issuer identities."
        )
        size = c.execute(
            "SELECT COALESCE(sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))),0) AS n FROM pg_tables WHERE schemaname='webb_sdi'"
        ).fetchone()["n"]
        if size > 1024**3:
            raise ValueError("ARCHIVE_GROWTH_LIMIT")
        manifest["databaseBytesAtStage"] = int(size)
        c.execute(
            "UPDATE webb_sdi.versions SET state='validated',manifest=%s WHERE version=%s",
            (Jsonb(manifest), version),
        )
        for table in DB_TABLES[2:]:
            c.execute(sql.SQL("ANALYZE webb_sdi.{}").format(sql.Identifier(table)))
    return manifest


def grant_reader(dsn, role):
    with connect(dsn, row_factory=dict_row) as c:
        if not safe_reader_role(c, role):
            raise ValueError("DEDICATED_SELECT_ONLY_ROLE_REQUIRED")
        c.execute(
            sql.SQL("GRANT USAGE ON SCHEMA webb_sdi TO {}").format(sql.Identifier(role))
        )
        c.execute(
            sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA webb_sdi TO {}").format(
                sql.Identifier(role)
            )
        )


def snapshot(dsn):
    result = {}
    with connect(dsn) as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL TIME ZONE 'UTC'")
        for table in DB_TABLES:
            leaves = []
            with c.cursor(name="webb_sdi_fingerprint") as cur:
                cur.itersize = 1000
                cur.execute(
                    sql.SQL("SELECT to_jsonb(t) FROM webb_sdi.{} t").format(
                        sql.Identifier(table)
                    )
                )
                for row in cur:
                    leaves.append(hashlib.sha256(canonical(row[0])).hexdigest())
            result[table] = {
                "rows": len(leaves),
                "sha256": hashlib.sha256(
                    "\n".join(sorted(leaves)).encode()
                ).hexdigest(),
            }
    return result


def qualify_restore(dsn, restored_dsn, version, backup_sha):
    if len(backup_sha) != 64 or any(ch not in "0123456789abcdef" for ch in backup_sha):
        raise ValueError("INVALID_BACKUP_HASH")
    identities = []
    for target in (dsn, restored_dsn):
        with connect(target) as c:
            identities.append(
                c.execute(
                    "SELECT current_database(),inet_server_addr(),inet_server_port(),(SELECT oid FROM pg_database WHERE datname=current_database())"
                ).fetchone()
            )
    if identities[0] == identities[1]:
        raise ValueError("INDEPENDENT_RESTORE_REQUIRED")
    original, restored = snapshot(dsn), snapshot(restored_dsn)
    if original != restored:
        raise ValueError("RESTORE_CONTENT_MISMATCH")
    proof = {
        "backupSha256": backup_sha,
        "allTables": original,
        "independentRestore": True,
    }
    with connect(dsn) as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        if (
            c.execute(
                "UPDATE webb_sdi.versions SET state='restore-qualified',restore_proof=%s WHERE version=%s AND state='validated'",
                (Jsonb(proof), version),
            ).rowcount
            != 1
        ):
            raise ValueError("VALIDATED_VERSION_REQUIRED")
    return proof


def publish(dsn, version, expected_version):
    with connect(dsn, row_factory=dict_row) as c:
        c.execute("SELECT pg_advisory_xact_lock(%s)", (LOCK,))
        old = c.execute(
            "SELECT version FROM webb_sdi.accepted WHERE singleton"
        ).fetchone()
        if (old["version"] if old else None) != expected_version:
            raise ValueError("PUBLICATION_CONFLICT")
        row = c.execute(
            "SELECT * FROM webb_sdi.versions WHERE version=%s AND state IN ('restore-qualified','published') AND restore_proof IS NOT NULL",
            (version,),
        ).fetchone()
        if not row:
            raise ValueError("RESTORE_QUALIFIED_VERSION_REQUIRED")
        c.execute(
            "UPDATE webb_sdi.versions SET state='published' WHERE version=%s",
            (version,),
        )
        c.execute(
            "INSERT INTO webb_sdi.accepted(singleton,version) VALUES(true,%s) ON CONFLICT(singleton) DO UPDATE SET version=excluded.version,published_at=now()",
            (version,),
        )
    return version
