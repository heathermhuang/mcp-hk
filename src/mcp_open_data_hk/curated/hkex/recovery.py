"""Source-complete immutable dump/restore and offline exports; no request-time SQL export."""

import csv
import hashlib
import io
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict

from ..backup import file_hash
from ..build import connect
from .contracts import Filing, NOTICE, canonical, digest
from .store import current_policy, fingerprint, quiescent


def pg_environment(dsn):
    config = conninfo_to_dict(dsn)
    supported = {
        "host": "PGHOST",
        "hostaddr": "PGHOSTADDR",
        "port": "PGPORT",
        "dbname": "PGDATABASE",
        "user": "PGUSER",
        "password": "PGPASSWORD",
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "connect_timeout": "PGCONNECT_TIMEOUT",
    }
    if set(config) - set(supported):
        raise ValueError("UNSUPPORTED_BACKUP_CONNECTION_OPTION")
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env.update({supported[k]: v for k, v in config.items()})
    env["PGCONNECT_TIMEOUT"] = "10"
    return env


def backup(dsn, destination):
    destination = Path(destination)
    with quiescent(dsn) as c:
        current_policy(c, modes=("backup", "retain"))
        size = c.execute(
            "SELECT COALESCE(sum(pg_total_relation_size(quote_ident(schemaname)||'.'||quote_ident(tablename))),0) AS bytes FROM pg_tables WHERE schemaname='hkex'"
        ).fetchone()["bytes"]
        if size > 1024**3 or shutil.disk_usage(destination.parent).free < 20 * 1024**3:
            raise ValueError("HKEX_GROWTH_RESERVE_REQUIRED")
        return _backup(dsn, destination)


def _backup(dsn, destination):
    destination = Path(destination)
    # Exclusive private create preserves failed artifacts and prior accepted dumps.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            result = subprocess.run(
                [
                    "pg_dump",
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--schema=hkex",
                ],
                env=pg_environment(dsn),
                stdout=stream,
                stderr=subprocess.PIPE,
                timeout=600,
            )
        if result.returncode:
            raise ValueError("HKEX_BACKUP_FAILED")
    except Exception:
        # Partial file remains deliberately; do not overwrite on retry.
        raise
    return {
        "schema": "hkex",
        "sha256": file_hash(destination),
        "bytes": destination.stat().st_size,
        "tables": fingerprint(dsn),
    }


def restore(dsn, path, expected_sha256):
    path = Path(path)
    if path.is_symlink() or file_hash(path) != expected_sha256:
        raise ValueError("HKEX_BACKUP_CHECKSUM_MISMATCH")
    with connect(dsn) as c:
        if (
            c.execute(
                "SELECT count(*) FROM pg_namespace WHERE nspname NOT LIKE 'pg_%' AND nspname<>'information_schema' AND nspname<>'public'"
            ).fetchone()[0]
            or c.execute(
                "SELECT count(*) FROM pg_tables WHERE schemaname='public'"
            ).fetchone()[0]
        ):
            raise ValueError("EMPTY_ISOLATED_RESTORE_REQUIRED")
    with path.open("rb") as stream:
        result = subprocess.run(
            [
                "pg_restore",
                "--dbname=" + conninfo_to_dict(dsn)["dbname"],
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
            ],
            env=pg_environment(dsn),
            stdin=stream,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            timeout=600,
        )
    if result.returncode:
        raise ValueError("HKEX_RESTORE_FAILED")
    return fingerprint(dsn)


def spreadsheet(value):
    value = "" if value is None else str(value)
    return (
        "'" + value
        if value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
        or (len(value) > 1 and value.startswith("0"))
        else value
    )


def build_export(reader, version, destination):
    # Published immutable version only; export right checked on every bounded page.
    status = reader.status(mode="export", include_inventory=True)
    if (
        status["acceptedVersion"] != version
        or status["modes"].get("export") != "allowed"
    ):
        raise ValueError("HKEX_EXPORT_UNQUALIFIED")
    w = status["coverage"]["window"]
    params = dict(
        issuerId=w["issuer_id"],
        start=w["start"],
        end=w["end"],
        basis=w["basis"],
        channel=w["channel"],
        version=version,
        limit=100,
    )
    rows, cursor = [], None
    while True:
        result = reader.query("disclosures", dict(params, cursor=cursor), mode="export")
        rows.extend(result["data"])
        if len(rows) > 5000 or len(canonical(rows)) > 16 * 1024 * 1024:
            raise ValueError("HKEX_EXPORT_SIZE_LIMIT")
        cursor = result["nextCursor"]
        if not cursor:
            break
    # Include linked notices outside the nominal window; all declared pilot facts.
    serials = set(status["coverage"]["acceptedSerials"])
    for serial in sorted(serials - {row["serial"] for row in rows}):
        rows.append(
            reader.query(
                "disclosure", {"filingId": serial, "version": version}, mode="export"
            )["data"]
        )
    if {row["serial"] for row in rows} != serials:
        raise ValueError("HKEX_EXPORT_COVERAGE_MISMATCH")
    rows.sort(key=lambda x: x["serial"])
    # Full nested JSON preserves lossless decimals and all typed positions.
    csvfile = io.StringIO(newline="")
    writer = csv.writer(csvfile)
    writer.writerow(
        [
            "serial",
            "issuer_id",
            "form",
            "state",
            "event_date",
            "filed_date",
            "published_date",
        ]
    )
    for row in rows:
        writer.writerow(
            [
                spreadsheet(row[key]["value"] if key.endswith("_date") else row[key])
                for key in (
                    "serial",
                    "issuer_id",
                    "form",
                    "state",
                    "event_date",
                    "filed_date",
                    "published_date",
                )
            ]
        )
    members = {
        "records.json": canonical(rows),
        "summary.csv": csvfile.getvalue().encode("utf-8-sig"),
        "schema.json": canonical(Filing.model_json_schema()),
        "dictionaries.json": canonical(result["dictionaries"]),
        "coverage.json": canonical(status["coverage"]),
        "NOTICE.txt": NOTICE.encode(),
        "fields.json": canonical(
            {
                "numericStrings": "Unrounded source decimal strings; null is unknown",
                "csv": "Summary only; formula-like and leading-zero text prefixed with apostrophe",
                "dates": "Event/filing/publication separate; window end exclusive; unknown preserved",
                "source": "HKEX DI, subject to independently qualified reuse",
                "rawDocumentsIncluded": False,
            }
        ),
    }
    manifest = {
        "version": version,
        "source": "hkex_di",
        "rows": len(rows),
        "coverage": status["coverage"],
        "files": {
            name: {"sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}
            for name, body in members.items()
        },
    }
    members["manifest.json"] = canonical(manifest)
    if sum(map(len, members.values())) > 20 * 1024 * 1024:
        raise ValueError("HKEX_EXPORT_SIZE_LIMIT")
    # Recheck policy after potentially long construction, before materialisation.
    if (
        reader.status(mode="export", include_inventory=True)["modes"].get("export")
        != "allowed"
    ):
        raise ValueError("HKEX_EXPORT_UNQUALIFIED")
    destination = Path(destination)
    with destination.open("xb") as stream:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, body in members.items():
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, body)
    return {
        "sha256": file_hash(destination),
        "bytes": destination.stat().st_size,
        "manifestHash": digest(manifest),
    }
