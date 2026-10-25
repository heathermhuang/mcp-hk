"""Offline immutable racing exports; never construct full exports in HTTP requests."""

import csv
import hashlib
import io
import json
import zipfile

from .policy import RacingRejected, canonical, require


def build_export(
    record, pinned, family, version, rows, *, fields, cutoff, now=None, historical=False
):
    require(record, pinned, family, "export", fields=fields, now=now)
    if historical:
        require(record, pinned, family, "history", fields=fields, now=now)
    if len(rows) > 100000 or not fields or any(set(row) != set(fields) for row in rows):
        raise RacingRejected("EXPORT_SCOPE_REJECTED")
    csv_file = io.StringIO(newline="")
    writer = csv.DictWriter(
        csv_file, fieldnames=fields, lineterminator="\n", quoting=csv.QUOTE_ALL
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: (
                    "'" + str(value)
                    if str(value).lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                    else value
                )
                for key, value in row.items()
            }
        )
    files = {
        "records.json": canonical(rows),
        "records.csv": csv_file.getvalue().encode("utf-8-sig"),
        "fields.json": canonical(
            {
                "fields": fields,
                "identifiers": "strings",
                "moneyOdds": "decimal strings",
                "csv": "formula-like values prefixed with apostrophe; raw facts preserved in JSON",
            }
        ),
        "NOTICE.txt": b"Source: The Hong Kong Jockey Club. Use only within the qualified source policy. No betting advice.\n",
    }
    size = sum(map(len, files.values()))
    if size > 16 * 1024 * 1024:
        raise RacingRejected("EXPORT_SIZE_LIMIT")
    manifest = {
        "source": "hkjc",
        "version": version,
        "family": family,
        "cutoff": cutoff,
        "policySha256": pinned,
        "files": {
            name: {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}
            for name, body in files.items()
        },
    }
    files["manifest.json"] = canonical(manifest)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, body)
    require(record, pinned, family, "export", fields=fields, now=now)
    return output.getvalue(), json.loads(canonical(manifest))
