"""Stage a closed Hong Kong projection; never publish an unverified candidate."""

import hashlib
import json
import time
from importlib.resources import files

from ..archive_sql import SELECTED
from . import normalize as n
from .schema import DDL, INDEXES, META, TABLES, schema_name


def driver():
    try:
        import psycopg

        return psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Install mcp-hk[curated] for the optional read model"
        ) from exc


def connect(dsn, **kwargs):
    return driver().connect(dsn, connect_timeout=5, **kwargs)


def transform_hash():
    digest = hashlib.sha256()
    for module in ("normalize.py", "schema.py", "source.py", "build.py"):
        digest.update(files("mcp_open_data_hk.curated").joinpath(module).read_bytes())
    return digest.hexdigest()


def copy_rows(conn, table, rows):
    from psycopg import sql

    count = 0
    statement = sql.SQL("COPY {} ({}) FROM STDIN").format(
        sql.Identifier(table), sql.SQL(",").join(map(sql.Identifier, TABLES[table]))
    )
    with conn.cursor().copy(statement) as copy:
        for row in rows:
            copy.write_row(row)
            count += 1
    return count


def stage(dsn, source, version, progress=lambda report: None):
    from psycopg import sql

    schema = schema_name(version)
    manifest = dict(
        source.manifest,
        transform=n.TRANSFORM,
        transformSha256=transform_hash(),
        counts={},
    )
    started = time.monotonic()
    with connect(
        dsn,
        options="-c statement_timeout=1800000 -c lock_timeout=5000",
        tcp_user_timeout=30000,
    ) as conn:
        conn.execute(META)
        conn.execute(
            "INSERT INTO curated.dataset_versions(version,schema_name,state,manifest) VALUES (%s,%s,'staging',%s::jsonb)",
            (version, schema, json.dumps(manifest)),
        )
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        conn.execute(
            sql.SQL("SET search_path TO {},pg_catalog").format(sql.Identifier(schema))
        )
        conn.execute(DDL)
        conn.commit()
        listed = {
            r["issuer"]
            for r in source.rows(
                "issue",
                ["issuer"],
                "ID1 IN (SELECT IssueID FROM stocklistings WHERE StockExID IN (1,20))",
            )
        }
        licensed = {
            r["orgID"] for t in ("licrec", "olicrec") for r in source.rows(t, ["orgID"])
        }
        extra = ",".join(str(int(i)) for i in sorted(listed | licensed)) or "0"
        primary = f"Domicile=1 OR orgType=27 OR PersonID IN ({extra})"
        selection = f"SELECT PersonID FROM organisations WHERE {primary}"
        # Only dependency IDs are retained in Python. Millions of primary entities
        # stream directly into COPY, never into Store.snapshot or an object list.
        required = set()
        progress({"phase": "relationships", "version": version})
        import tempfile

        with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as relationships:
            for table, column in [
                ("directorships", "Company"),
                ("licrec", "orgID"),
                ("olicrec", "orgID"),
            ]:
                cols = SELECTED[table]
                for row in source.rows(table, cols, f"{column} IN ({selection})"):
                    required.add(row[column])
                    if table == "directorships":
                        required.add(row["Director"])
                    if table == "licrec":
                        required.add(row["staffID"])
                    relationships.write(
                        json.dumps([table, row], ensure_ascii=False) + "\n"
                    )
                source.check_disk()
            progress({"phase": "entities", "dependencyIds": len(required)})
            # Spool only selected, public-field entity facts to avoid repeating a
            # multi-million-row source query for identifiers and names.
            with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as facts:
                reasons_count = {}

                def entities():
                    cols = SELECTED
                    for row in source.rows(
                        "organisations", cols["organisations"], primary
                    ):
                        reasons = n.scope(row, listed, licensed)
                        for reason in reasons:
                            reasons_count[reason] = reasons_count.get(reason, 0) + 1
                        required.discard(row["PersonID"])
                        facts.write(
                            json.dumps(["organisation", row], ensure_ascii=False) + "\n"
                        )
                        yield n.entity(row, "organisation", reasons)
                    pending = sorted(required)
                    for offset in range(0, len(pending), 2000):
                        ids = ",".join(map(str, pending[offset : offset + 2000]))
                        for table, kind in [
                            ("organisations", "organisation"),
                            ("people", "person"),
                        ]:
                            for row in source.rows(
                                table, cols[table], f"PersonID IN ({ids})"
                            ):
                                if row["PersonID"] not in required:
                                    raise ValueError(
                                        "Source ID appears as both person and organisation"
                                    )
                                required.remove(row["PersonID"])
                                facts.write(
                                    json.dumps([kind, row], ensure_ascii=False) + "\n"
                                )
                                yield n.entity(row, kind, ["relationship_dependency"])
                    if required:
                        raise ValueError(
                            f"Unresolved relationship endpoints: {len(required)}"
                        )

                manifest["counts"]["entities"] = copy_rows(conn, "entities", entities())
                manifest["scopeCounts"] = reasons_count
                for table, fn in [
                    ("entity_identifiers", n.identifiers),
                    ("entity_names", n.names),
                ]:
                    facts.seek(0)

                    def transformed():
                        for line in facts:
                            kind, row = json.loads(line)
                            yield from fn(row, kind)

                    manifest["counts"][table] = copy_rows(conn, table, transformed())
                conn.commit()
            source.check_disk()
            for target, original, fn in [
                ("officer_appointments", "directorships", n.appointment),
                ("licences", "olicrec", n.licence),
                ("licence_relationships", "licrec", lambda row: n.licence(row, True)),
            ]:
                relationships.seek(0)

                def transformed_relationships():
                    for line in relationships:
                        table, row = json.loads(line)
                        if table == original:
                            yield fn(row)

                manifest["counts"][target] = copy_rows(
                    conn, target, transformed_relationships()
                )
                conn.commit()
        progress({"phase": "names_and_indexes", "counts": manifest["counts"]})
        # Name history is restricted to primary organisations; dependency names
        # are archive-name observations, not an expansion into foreign histories.
        manifest["counts"]["formerNames"] = copy_rows(
            conn,
            "entity_names",
            (
                name
                for row in source.rows(
                    "namechanges", SELECTED["namechanges"], f"personID IN ({selection})"
                )
                for name in n.old_names(row)
            ),
        )
        manifest["counts"]["entity_names"] += manifest["counts"]["formerNames"]

        def references():
            for table, key, label in [
                ("positions", "positionID", "posLong"),
                ("activity", "ID", "actName"),
                ("dateaccuracy", "AccID", "AccText"),
                ("domiciles", "ID", "FullName"),
                ("orgtypes", "orgType", "typeName"),
                ("dismodes", "ID", "disModeTxt"),
            ]:
                for row in source.rows(table, [key, label]):
                    yield table, row[key], row[label]

        manifest["counts"]["source_references"] = copy_rows(
            conn, "source_references", references()
        )
        conn.execute(INDEXES)
        conn.execute("ANALYZE")
        manifest["elapsedSeconds"] = round(time.monotonic() - started, 2)
        manifest["scopePolicy"] = (
            "HK domicile, source orgType 27, HK Main/GEM issuers, SFC firms; referenced officers/staff only; former names for primary organisations"
        )
        conn.execute(
            "UPDATE curated.dataset_versions SET manifest=%s::jsonb WHERE version=%s",
            (json.dumps(manifest), version),
        )
        conn.commit()
        progress(manifest)
    return manifest
