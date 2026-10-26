"""Read the openly released Webb SDI tables from verified mysqldump literals.

No source SQL is executed and no HKEX request is made. Numeric tokens are retained
as strings: the original FLOAT/DOUBLE storage cannot recover original decimal input.
"""

import argparse
import hashlib
import json
import os
import time
from collections import Counter
from contextlib import ExitStack
from datetime import date
from pathlib import Path

from ..archive_qualify import decode_literal
from ..archive_sql import INSERT, MAX_STATEMENT, value_rows

ARCHIVE_SHA = "9c2c42ae5e762d34b60954f43b37199b92b546033e229a292ed08b76323f6de2"
DATA_SHA = "39ca9e09601d2c99ef60a52a6f86f222d7304d885e13f25b9898d208dec578af"
TABLES = {
    "sdi": None,
    "sdicap": None,
    "sdievent": None,
    "sdireason": None,
    "capacity": None,
    "currencies": None,
    "issue": {"ID1", "issuer", "SEHKID", "typeID"},
}
MAX_OUTPUT = 1024**3


def canonical(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()


def literal(value, kind):
    if value == b"NULL":
        return None
    if value.startswith(b"'"):
        return decode_literal(value, kind)
    # Preserve both identifiers and numeric source lexemes without float coercion.
    return value.decode("ascii")


def extract(workspace, output, *, data_path=None, expected_sha=DATA_SHA, census=None):
    workspace, output = Path(workspace), Path(output)
    schema = json.loads((workspace / "source-schema.json").read_text())
    audit = json.loads((workspace / "archive-audit.json").read_text())
    acquisition = json.loads((workspace / "acquisition.json").read_text())
    if (
        audit["status"] != "source_fidelity_verified"
        or acquisition["sha256"] != ARCHIVE_SHA
    ):
        raise ValueError("VERIFIED_ORIGINAL_WEBB_RELEASE_REQUIRED")
    census = (
        Path(census)
        if census
        else Path(__file__).resolve().parents[3]
        / "docs/data/enigma-audit-20261023.json"
    )
    counted = json.loads(census.read_text())
    if (
        counted["archiveSha256"] != ARCHIVE_SHA
        or audit["sourceDataSha256"] != expected_sha
    ):
        raise ValueError("SOURCE_CENSUS_LINEAGE_MISMATCH")
    expected = counted["sourceTableRows"]
    if data_path is None:
        data_path = workspace / "member-6bddc01042c901c34e8a70d6.sql"
    data_path = Path(data_path)
    if data_path.is_symlink() or data_path.stat().st_size > 13 * 1024**3:
        raise ValueError("SOURCE_MEMBER_SIZE_OR_PATH")
    output.mkdir(mode=0o700)  # Never overwrite an existing accepted/failed attempt.
    counts = Counter()
    hashes = {table: hashlib.sha256() for table in TABLES}
    source_hash = hashlib.sha256()
    forms, dates, nulls = Counter(), {}, Counter()
    ids, serials, issue_ids = set(), set(), set()
    cap_parents, event_parents, revisions = set(), set(), set()
    total_output, source_bytes = 0, 0
    started = time.monotonic()
    try:
        with ExitStack() as stack:
            streams = {}
            for table in TABLES:
                fd = os.open(
                    output / (table + ".ndjson"),
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                streams[table] = stack.enter_context(os.fdopen(fd, "wb"))
            source = stack.enter_context(data_path.open("rb"))
            while line := source.readline(MAX_STATEMENT + 1):
                source_hash.update(line)
                source_bytes += len(line)
                if len(line) > MAX_STATEMENT or time.monotonic() - started > 600:
                    raise ValueError("BOUNDED_SOURCE_EXTRACTION_EXCEEDED")
                match = INSERT.match(line)
                if not match:
                    continue
                table = match[1].decode("ascii")
                if table not in TABLES:
                    continue
                columns = schema[table]["columns"]
                selected = TABLES[table]
                for values in value_rows(line[match.end() :].strip(), len(columns)):
                    row = {
                        c["name"]: literal(v, c["type"].split("(")[0].split()[0])
                        for c, v in zip(columns, values)
                        if (selected is None or c["name"] in selected)
                        and c["name"] != "ccc"
                    }
                    if table == "sdi":
                        if row["ID"] in ids:
                            raise ValueError("DUPLICATE_WEBB_SDI_ID")
                        ids.add(row["ID"])
                        forms[row["form"] or "unknown"] += 1
                        if row["serNo"]:
                            if row["serNo"] in serials:
                                raise ValueError("DUPLICATE_FORM_SERIAL")
                            serials.add(row["serNo"])
                        for key in ("relDate", "awDate", "signDate", "modified"):
                            value = row[key]
                            if value is None:
                                nulls[key] += 1
                            else:
                                day = value[:10]
                                try:
                                    date.fromisoformat(day)
                                except ValueError:
                                    nulls[key + ":invalid"] += 1
                                else:
                                    low, high = dates.get(key, (day, day))
                                    dates[key] = (min(low, day), max(high, day))
                        if row["issueID"] is None:
                            nulls["issueID"] += 1
                        if row["filing"] is not None:
                            nulls["legacyFilingKeyPresent"] += 1
                        if row["serNoAmend"]:
                            revisions.add(row["serNoAmend"])
                        if row["serNoSuper"]:
                            revisions.add(row["serNoSuper"])
                    elif table == "sdicap":
                        cap_parents.add(row["sdiID"])
                    elif table == "sdievent":
                        event_parents.add(row["sdiID"])
                    elif table == "issue":
                        issue_ids.add(row["ID1"])
                    payload = canonical(row) + b"\n"
                    total_output += len(payload)
                    if total_output > MAX_OUTPUT:
                        raise ValueError("WEBB_SDI_PROJECTION_SIZE_LIMIT")
                    streams[table].write(payload)
                    hashes[table].update(payload)
                    counts[table] += 1
        if source_hash.hexdigest() != expected_sha:
            raise ValueError("SOURCE_MEMBER_CHECKSUM_MISMATCH")
        for table in TABLES:
            if counts[table] != expected[table]["rows"]:
                raise ValueError("SOURCE_CENSUS_MISMATCH:" + table)
        notice = (workspace / "webb-site-NOTICE.txt").read_bytes()
        (output / "NOTICE.txt").write_bytes(notice)
        manifest = {
            "source": "webb_sdi_archive",
            "version": "webb-sdi-enigma251227-v1",
            "archiveSha256": ARCHIVE_SHA,
            "sourceDataSha256": expected_sha,
            "sourceBytes": source_bytes,
            "projectionBytes": total_output,
            "tables": {
                t: {"rows": counts[t], "sha256": hashes[t].hexdigest()} for t in TABLES
            },
            "forms": dict(forms),
            "dateRanges": dates,
            "nullCounts": dict(nulls),
            "uniqueSerials": len(serials),
            "unresolvedRevisionSerials": len(revisions - serials),
            "orphanCapacityParentIds": len(cap_parents - ids),
            "orphanEventParentIds": len(event_parents - ids),
            "noticeSha256": hashlib.sha256(notice).hexdigest(),
            "numericQualification": "Original FLOAT/DOUBLE storage; source dump numeric lexemes retained as strings, not reconstructed exact original decimal input",
            "dateQualification": "relDate=relevant event; awDate=awareness; signDate=signature; modified=archive record edit. None is silently a filing/publication timestamp.",
            "scope": "All SDI records present in this original Webb release; not complete/current HKEX coverage",
            "collectorQualification": "Released SDI.vb implements Form 3A. Original source director matching is heuristic and is not newly verified.",
            "elapsedSeconds": round(time.monotonic() - started, 3),
        }
        (output / "manifest.json").write_bytes(canonical(manifest) + b"\n")
        return manifest
    except Exception as exc:
        (output / "FAILED.json").write_bytes(
            canonical(
                {
                    "state": "failed",
                    "code": (
                        str(exc) if isinstance(exc, ValueError) else type(exc).__name__
                    ),
                    "sourceBytes": source_bytes,
                }
            )
        )
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--census", type=Path)
    args = parser.parse_args()
    print(
        json.dumps(
            extract(args.workspace, args.output, census=args.census), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
