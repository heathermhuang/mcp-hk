"""Offline, bounded export of an accepted read model. Never a request-time query."""

import argparse
import gzip
import hashlib
import json
import os
import shutil
import tarfile
import time
from importlib.resources import files
from pathlib import Path

from mcp_open_data_hk.curated.build import connect
from mcp_open_data_hk.curated.schema import TABLES, schema_name
from mcp_open_data_hk.curated.security import safe_reader_role

CHUNK_BYTES = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 2 * 1024**3


def encoded(value):
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str) + "\n"
    ).encode()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        while data := stream.read(1024 * 1024):
            h.update(data)
    return h.hexdigest()


def build(dsn, version, output, *, reserve_bytes=20 * 1024**3, deadline=3600):
    """Exclusive destination; failures retain their files and cannot publish."""
    from psycopg import sql
    from psycopg.rows import dict_row

    schema = schema_name(version)
    output = Path(output)
    output.mkdir(mode=0o700)  # Refuse overwriting an earlier accepted/failed build.
    started = time.monotonic()
    report = {
        "formatVersion": 1,
        "version": version,
        "view": "archive",
        "scope": "complete_approved_subset",
        "sourceObservedAt": None,
        "currentVerification": False,
        "asOfSupported": False,
        "tables": [],
    }

    def check():
        if time.monotonic() - started > deadline:
            raise TimeoutError("Export deadline exceeded")
        if shutil.disk_usage(output).free < reserve_bytes:
            raise ValueError("Export disk reserve reached")

    try:
        check()
        with connect(dsn, row_factory=dict_row) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            conn.execute("SET LOCAL statement_timeout='15min'")
            conn.execute("SET LOCAL lock_timeout='250ms'")
            if not safe_reader_role(
                conn, conn.execute("SELECT current_user AS role").fetchone()["role"]
            ):
                raise ValueError("Use the dedicated unprivileged reader for exports")
            release = conn.execute(
                "SELECT * FROM curated.dataset_versions WHERE version=%s", (version,)
            ).fetchone()
            if (
                not release
                or release["state"] != "published"
                or not (release["restore_proof"] or {}).get("independentlyRestored")
                or release["schema_name"] != schema
            ):
                raise ValueError(
                    "Export requires an independently qualified published version"
                )
            report["source"] = release["manifest"]
            report["temporalQualification"] = release["restore_proof"]["temporal"]
            report["scopeDescription"] = (
                "HK-qualified organisations and necessary officer/SFC dependency parties; all seven approved model tables. Not the original global archive or a current register."
            )
            schemas = {}
            for table, fields in TABLES.items():
                check()
                columns = conn.execute(
                    "SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                    (schema, table),
                ).fetchall()
                if [c["column_name"] for c in columns] != fields:
                    raise ValueError("Export schema differs from approved projection")
                schemas[table] = {
                    "columns": [
                        {
                            "name": c["column_name"],
                            "postgresType": c["data_type"],
                            "nullable": c["is_nullable"] == "YES",
                        }
                        for c in columns
                    ],
                    "encoding": "UTF-8",
                    "format": "NDJSON",
                    "dates": "ISO dates retain separate raw/precision fields; null means unknown",
                    "identifiers": "Namespaced strings retain leading zeros",
                }
                path = output / (table + ".ndjson")
                keys = {
                    "entity_identifiers": ["entity_id", "namespace", "value"],
                    "source_references": ["family", "code"],
                }.get(table, [fields[0]])
                query = sql.SQL("SELECT {} FROM {}.{} ORDER BY {}").format(
                    sql.SQL(",").join(map(sql.Identifier, fields)),
                    sql.Identifier(schema),
                    sql.Identifier(table),
                    sql.SQL(",").join(map(sql.Identifier, keys)),
                )
                count = 0
                h = hashlib.sha256()
                with (
                    conn.cursor(name="company_export") as cursor,
                    path.open("xb") as stream,
                ):
                    cursor.execute(query)
                    while rows := cursor.fetchmany(2000):
                        check()
                        for row in rows:
                            data = encoded(row)
                            stream.write(data)
                            h.update(data)
                            count += 1
                if count != release["manifest"]["counts"][table]:
                    raise ValueError("Export row count differs: " + table)
                report["tables"].append(
                    {
                        "name": table,
                        "file": path.name,
                        "rows": count,
                        "bytes": path.stat().st_size,
                        "sha256": h.hexdigest(),
                    }
                )
                print(
                    json.dumps({"table": table, "rows": count, "status": "written"}),
                    flush=True,
                )
        schema_file = output / "schema.json"
        schema_file.write_bytes(
            encoded({"formatVersion": 1, "version": version, "tables": schemas})
        )
        notice = output / "NOTICE.txt"
        notice.write_bytes(
            files("mcp_open_data_hk").joinpath("webb-site-NOTICE.txt").read_bytes()
        )
        readme = output / "README.txt"
        readme.write_text(
            "mcp.hk / David Webb original Enigma archival subset\n香港機構歷史資料；並非現況核實。\n\nOne UTF-8 JSON object per line; arrays, integers and nulls retain their JSON types. Dates retain raw/precision fields. Entity IDs are source keys, not verified business registration numbers. Dependency people are included only to close the approved relationships. No current/as-of status is inferred.\n\nVerify each uncompressed file against manifest.json and the downloaded .tar.gz against the external download manifest. Retain NOTICE.txt, schema.json and source attribution when reusing data.\n",
            encoding="utf-8",
        )
        report["supportingFiles"] = [
            {"file": f.name, "bytes": f.stat().st_size, "sha256": digest(f)}
            for f in (schema_file, notice, readme)
        ]
        (output / "manifest.json").write_bytes(encoded(report))
        archive = output / "companies.tar.gz"
        with (
            archive.open("xb") as raw,
            gzip.GzipFile(
                fileobj=raw, mode="wb", filename="", mtime=0, compresslevel=6
            ) as gz,
            tarfile.open(fileobj=gz, mode="w|") as tar,
        ):
            for item in [t["file"] for t in report["tables"]] + [
                "schema.json",
                "NOTICE.txt",
                "README.txt",
                "manifest.json",
            ]:
                check()
                f = output / item
                info = tar.gettarinfo(str(f), arcname=item)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                with f.open("rb") as stream:
                    tar.addfile(info, stream)
        check()
        if archive.stat().st_size > MAX_ARCHIVE_BYTES:
            raise ValueError("Archive exceeds the approved delivery bound")
        parts = []
        with archive.open("rb") as stream:
            while data := stream.read(CHUNK_BYTES):
                check()
                name = f"part-{len(parts):03d}"
                (output / name).write_bytes(data)
                parts.append(
                    {
                        "file": name,
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        publication = {
            **report,
            "archive": {
                "file": "companies.tar.gz",
                "bytes": archive.stat().st_size,
                "sha256": digest(archive),
                "parts": parts,
            },
            "schema": json.loads(schema_file.read_text()),
            "noticeSha256": digest(notice),
        }
        (output / "publication.json").write_bytes(encoded(publication))
        (output / "build-receipt.json").write_bytes(
            encoded(
                {
                    "status": "built_not_published",
                    "version": version,
                    "archiveSha256": publication["archive"]["sha256"],
                    "elapsedSeconds": round(time.monotonic() - started, 2),
                }
            )
        )
        return publication
    except Exception as exc:
        (output / "failed-receipt.json").write_bytes(
            encoded(
                {
                    "status": "failed_not_published",
                    "exceptionType": type(exc).__name__,
                    "elapsedSeconds": round(time.monotonic() - started, 2),
                }
            )
        )
        raise


def verify(directory):
    """Verify actual archive bytes, member hashes, row counts and JSON field types."""
    directory = Path(directory)
    publication = json.loads((directory / "publication.json").read_text())
    archive = directory / "companies.tar.gz"
    if (
        digest(archive) != publication["archive"]["sha256"]
        or archive.stat().st_size != publication["archive"]["bytes"]
    ):
        raise ValueError("Archive checksum/size differs")
    expected = {t["file"]: t for t in publication["tables"]}
    expected.update({f["file"]: f for f in publication["supportingFiles"]})
    expected["manifest.json"] = None
    seen = set()
    with tarfile.open(archive, "r|gz") as tar:
        for member in tar:
            if (
                not member.isfile()
                or member.name not in expected
                or member.name in seen
            ):
                raise ValueError("Unexpected archive member")
            seen.add(member.name)
            h, count = hashlib.sha256(), 0
            stream = tar.extractfile(member)
            meta = expected[member.name]
            if meta and "rows" in meta:
                columns = publication["schema"]["tables"][meta["name"]]["columns"]
                for line in stream:
                    h.update(line)
                    row = json.loads(line)
                    if list(row) != [c["name"] for c in columns]:
                        raise ValueError("JSON fields differ")
                    for c in columns:
                        value = row[c["name"]]
                        typ = c["postgresType"]
                        if value is None:
                            if not c["nullable"]:
                                raise ValueError("Unexpected null")
                        elif typ in {"bigint", "integer"}:
                            if type(value) is not int:
                                raise ValueError("Integer type lost")
                        elif typ == "ARRAY":
                            if not isinstance(value, list) or any(
                                not isinstance(v, str) for v in value
                            ):
                                raise ValueError("Array type lost")
                        elif not isinstance(value, str):
                            raise ValueError("String/date type lost")
                    count += 1
                if count != meta["rows"]:
                    raise ValueError("Downloaded row count differs")
            else:
                while data := stream.read(1024 * 1024):
                    h.update(data)
            if meta and (
                member.size != meta["bytes"] or h.hexdigest() != meta["sha256"]
            ):
                raise ValueError("Downloaded member checksum differs")
    if seen != set(expected):
        raise ValueError("Archive member missing")
    return {
        "verified": True,
        "version": publication["version"],
        "archiveSha256": publication["archive"]["sha256"],
        "rows": {t["name"]: t["rows"] for t in publication["tables"]},
        "typedNdjsonVerified": True,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["build", "verify"])
    parser.add_argument("--version", default="enigma251227-hk-v1")
    parser.add_argument("--directory", type=Path, required=True)
    args = parser.parse_args()
    result = (
        build(os.environ["CURATED_DSN"], args.version, args.directory)
        if args.action == "build"
        else verify(args.directory)
    )
    print(
        json.dumps(
            {
                "version": result["version"],
                "verified": result.get("verified", False),
                "archiveSha256": result.get(
                    "archiveSha256", result.get("archive", {}).get("sha256")
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
