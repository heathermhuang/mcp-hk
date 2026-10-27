"""Immutable prebuilt SFC export. Serving never builds an export or fetches SFC.

A trusted source reader supplies fresh policy/version metadata before delivery.
Default application configuration exposes no artifact. No raw HTML or contacts.
"""

import csv
import io
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .contracts import Corporation, Rejected, digest, encoded

MAX_BYTES = 2 * 1024**2
NOTICE = b"Source: Securities and Futures Commission public register. Dated corporate observations for the qualified tracked verification cohort only. Unknown dates do not imply licence status or revocation. Independent mcp.hk service; not endorsed by SFC.\n"


def build_from_reader(reader, version, folder):
    state = reader.artifact_state(version, mode="export")
    records = [
        reader.verify(ce, version, mode="export")["data"] for ce in state["cohort"]
    ]
    if reader.artifact_state(version, mode="export") != state:
        raise Rejected("SFC_EXPORT_STATE_CHANGED")
    return build(records, state, reader.policy, folder)


def build(records, state, policy, folder, *, now=None):
    now = now or datetime.now(timezone.utc)
    policy.require("export", "retention", now=now)
    validate_state(state, policy, now)
    facts = [Corporation.model_validate(r).model_dump(mode="json") for r in records]
    facts.sort(key=lambda r: r["ce"])
    if (
        not 1 <= len(facts) <= 25
        or len({r["ce"] for r in facts}) != len(facts)
        or set(r["ce"] for r in facts) != set(state["cohort"])
        or not set(state["cohort"]) <= set(policy.trackedCorporateReferences)
        or digest(encoded(facts)) != state["factsSha256"]
    ):
        raise Rejected("SFC_EXPORT_COHORT_MISMATCH")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n", quoting=csv.QUOTE_ALL)
    columns = list(Corporation.model_fields)
    writer.writerow(columns)
    for row in facts:
        values = []
        for key in columns:
            value = row[key]
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            elif value is None:
                value = ""
            elif isinstance(value, str) and (
                re.match(r"^[\s\x00-\x1f\x7f-\x9f\u200b-\u200f]*[=+\-@]", value)
                or re.fullmatch(r"0\d+", value)
            ):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    members = {
        "records.json": encoded(facts),
        "records.csv": stream.getvalue().encode("utf-8-sig"),
        "schema.json": encoded(
            {
                "format": "sfc-corporate-export-v1",
                "fields": columns,
                "nestedCsv": "JSON text",
                "csvTextEscape": "apostrophe before formula-like and leading-zero strings",
                "temporalBasis": "dated observation; unknown dates remain unknown",
            }
        ),
        "provenance.json": encoded(state),
        "NOTICE.txt": NOTICE,
    }
    manifest = {
        "format": "sfc-corporate-export-v1",
        "version": state["version"],
        "policySha256": policy.sha256,
        "scope": "accepted_tracked_corporate_cohort",
        "rowCount": len(facts),
        "expiresAt": state["expiresAt"],
        "files": {
            k: {"bytes": len(v), "sha256": digest(v)} for k, v in members.items()
        },
    }
    members["manifest.json"] = encoded(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, body in sorted(members.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o100600 << 16
            archive.writestr(info, body)
    raw = out.getvalue()
    if len(raw) > MAX_BYTES:
        raise Rejected("SFC_EXPORT_SIZE_LIMIT")
    folder = Path(folder) / state["version"]
    folder.mkdir(mode=0o700, parents=True, exist_ok=False)
    (folder / "corporations.zip").write_bytes(raw)
    descriptor = {
        "version": state["version"],
        "policySha256": policy.sha256,
        "factsSha256": state["factsSha256"],
        "expiresAt": state["expiresAt"],
        "bytes": len(raw),
        "sha256": digest(raw),
    }
    (folder / "descriptor.json").write_bytes(encoded(descriptor))
    return descriptor


def validate_state(state, policy, now):
    try:
        expires = datetime.fromisoformat(state["expiresAt"])
        if (
            not re.fullmatch(r"sfc-[a-f0-9]{32}", state["version"])
            or state["policySha256"] != policy.sha256
            or state["acceptedAndRestored"] is not True
            or expires.tzinfo is None
            or expires <= now
        ):
            raise ValueError()
    except (KeyError, ValueError, TypeError):
        raise Rejected("SFC_EXPORT_STATE_UNQUALIFIED") from None


def deliver(folder, version, current_state, policy, *, mode="browser", now=None):
    """Read immutable bytes only after fresh source/mode/expiry/hash verification."""
    now = now or datetime.now(timezone.utc)
    if mode not in {"rest", "mcp", "browser"}:
        raise Rejected("SFC_EXPORT_MODE_UNQUALIFIED")
    policy.require(mode, "export", "retention", now=now)
    if not re.fullmatch(r"sfc-[a-f0-9]{32}", version):
        raise Rejected("SFC_EXPORT_VERSION_INVALID")
    state = current_state(version)
    validate_state(state, policy, now)
    if state["version"] != version:
        raise Rejected("SFC_EXPORT_VERSION_INVALID")
    root = Path(folder).resolve()
    path = root / version
    if path.is_symlink() or not path.is_dir():
        raise Rejected("SFC_EXPORT_UNAVAILABLE")
    descriptor_path, archive = path / "descriptor.json", path / "corporations.zip"
    if (
        descriptor_path.is_symlink()
        or archive.is_symlink()
        or descriptor_path.stat().st_size > 16384
        or archive.stat().st_size > MAX_BYTES
    ):
        raise Rejected("SFC_EXPORT_UNAVAILABLE")
    descriptor = json.loads(descriptor_path.read_bytes())
    if any(
        descriptor[k] != state[k]
        for k in ("version", "policySha256", "factsSha256", "expiresAt")
    ):
        raise Rejected("SFC_EXPORT_STATE_CHANGED")
    raw = archive.read_bytes()
    if len(raw) != descriptor["bytes"] or digest(raw) != descriptor["sha256"]:
        raise Rejected("SFC_EXPORT_HASH_MISMATCH")
    policy.require(mode, "export", "retention", now=now)
    if current_state(version) != state:
        raise Rejected("SFC_EXPORT_STATE_CHANGED")
    return raw, descriptor
