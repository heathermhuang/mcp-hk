"""Bounded WFS paging using identity declared by its advertised Esri JSON.

This remains WFS access. Native attributes, geometry and CRS are not converted.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time

from .contracts import DomainError

MAX_BYTES = 128_000_000


async def read_pages(
    endpoint, type_name, expected, output_format, read_json, hit_count
):
    fd, name = tempfile.mkstemp(prefix="mcp-hk-wfs-", suffix=".json")
    os.close(fd)
    path = Path(name)
    count, pages, previous = 0, 0, None
    page_size = 1000
    header, oid, native_oid = None, None, None
    digest = hashlib.sha256()
    started = time.monotonic()
    try:
        with path.open("wb") as target:
            target.write(b"[")
            while count < expected:
                if pages >= 128 or time.monotonic() - started > 120:
                    raise DomainError(
                        "SOURCE_TOO_LARGE",
                        "WFS paging exceeded its bounded request/deadline window",
                        422,
                    )
                pages += 1
                requested = min(page_size, expected - count) if oid else 1
                try:
                    value, raw, headers, final = await read_json(
                        endpoint,
                        {
                            "service": "WFS",
                            "version": "2.0.0",
                            "request": "GetFeature",
                            "typeNames": type_name,
                            "outputFormat": output_format,
                            "count": requested,
                            "startIndex": count,
                        },
                    )
                except DomainError as exc:
                    if exc.code != "SOURCE_TOO_LARGE" or not oid or requested == 1:
                        raise
                    page_size = max(1, requested // 2)
                    continue
                fields = value.get("fields")
                if not isinstance(fields, list) or len(fields) > 1000:
                    raise DomainError(
                        "SOURCE_SCHEMA_CHANGED",
                        "Paged WFS has no bounded native field dictionary",
                        422,
                    )
                identifiers = [
                    f.get("name")
                    for f in fields
                    if isinstance(f, dict) and f.get("type") == "esriFieldTypeOID"
                ]
                if (
                    len(identifiers) != 1
                    or not isinstance(identifiers[0], str)
                    or not re.fullmatch(
                        r"[A-Za-z_][A-Za-z0-9_.-]{0,99}", identifiers[0]
                    )
                ):
                    raise DomainError(
                        "UNSUPPORTED_API",
                        "Paged WFS needs exactly one declared native OID field",
                        422,
                    )
                current = {
                    k: v
                    for k, v in value.items()
                    if k
                    not in {
                        "features",
                        "exceededTransferLimit",
                        "numberMatched",
                        "numberReturned",
                        "totalFeatures",
                        "timeStamp",
                    }
                }
                if header is None:
                    native_oid = identifiers[0]
                    features = value.get("features")
                    attributes = (
                        features[0].get("attributes", {})
                        if isinstance(features, list)
                        and features
                        and isinstance(features[0], dict)
                        else {}
                    )
                    declared = next(
                        f
                        for f in fields
                        if isinstance(f, dict) and f.get("name") == native_oid
                    )
                    oid = native_oid
                    if oid not in attributes:
                        alias = declared.get("alias")
                        aliases = value.get("fieldAliases", {})
                        if (
                            not isinstance(alias, str)
                            or aliases.get(native_oid) != alias
                            or alias not in attributes
                            or any(
                                isinstance(f, dict)
                                and f.get("name") != native_oid
                                and (f.get("name") == alias or f.get("alias") == alias)
                                for f in fields
                            )
                        ):
                            raise DomainError(
                                "UNSUPPORTED_API",
                                "WFS OID alias is absent or ambiguous",
                                422,
                            )
                        oid = alias
                    header = current
                    # The publisher's returned order is checked, never assumed:
                    # every accepted ID must increase across the complete scan.
                    continue
                if header != current or identifiers[0] != native_oid:
                    raise DomainError(
                        "SOURCE_SCHEMA_CHANGED",
                        "WFS page fields or CRS changed during reading",
                        422,
                    )
                features = value.get("features")
                if (
                    not isinstance(features, list)
                    or not features
                    or len(features) > min(page_size, expected - count)
                ):
                    raise DomainError(
                        "INCOMPLETE_SOURCE",
                        "WFS page is empty, overfull or truncated",
                        422,
                    )
                for key in ("numberMatched", "totalFeatures"):
                    declared = value.get(key)
                    if declared not in (None, "unknown") and (
                        type(declared) not in {int, str}
                        or re.fullmatch(r"[0-9]{1,10}", str(declared)) is None
                        or int(declared) != expected
                    ):
                        raise DomainError(
                            "INCOMPLETE_SOURCE",
                            "Paged JSON count conflicts with native WFS hits",
                            422,
                        )
                if (
                    value.get("exceededTransferLimit") is True
                    and count + len(features) >= expected
                ):
                    raise DomainError(
                        "INCOMPLETE_SOURCE",
                        "Final WFS page still declares truncation",
                        422,
                    )
                digest.update(raw)
                for row in features:
                    identity = (
                        row.get("attributes", {}).get(oid)
                        if isinstance(row, dict)
                        else None
                    )
                    if type(identity) is not int or (
                        previous is not None and identity <= previous
                    ):
                        raise DomainError(
                            "INCOMPLETE_SOURCE",
                            "WFS native IDs repeated or sort order was not honoured",
                            422,
                        )
                    previous = identity
                    encoded = json.dumps(
                        row, ensure_ascii=False, separators=(",", ":"), allow_nan=False
                    ).encode()
                    if target.tell() + len(encoded) + 2 > MAX_BYTES:
                        raise DomainError(
                            "SOURCE_TOO_LARGE",
                            "WFS representation exceeds the existing streamed file bound",
                            422,
                        )
                    if count:
                        target.write(b",")
                    target.write(encoded)
                    count += 1
            target.write(b"]")
        after = await hit_count()
        if after != expected:
            raise DomainError(
                "SOURCE_CHANGED", "WFS matched count changed during paging", 409
            )
        return (
            path,
            headers,
            final,
            {
                "apiFamily": "WFS",
                "scope": "complete_count_reconciled_wfs_scan",
                "representationFormat": "JSON",
                "sourceMatched": expected,
                "sourceContext": header,
                "coordinateReferenceSystem": header.get("spatialReference"),
                "wfsContract": "csdi-wfs-count-1",
                "outputFormat": output_format,
                "pageResponseChainHash": digest.hexdigest(),
                "sourcePages": pages,
                "pageSize": page_size,
                "countEvidence": {
                    "basis": "WFS_2_hits_before_and_after_and_ordered_native_OIDs",
                    "beforeMatched": expected,
                    "afterMatched": after,
                    "nativeOidField": oid,
                    "nativeDictionaryOidField": native_oid,
                    "ordering": "strict_native_OID_order_observed_and_verified_across_pages",
                    "distinctObservedOids": count,
                    "snapshot": "count_reconciled_scan_without_an_atomic_publication_token",
                },
                "datasetCompleteness": "Count-reconciled sorted WFS scan, not an atomic publication snapshot or a count of real-world entities.",
            },
        )
    except BaseException:
        path.unlink(missing_ok=True)
        raise
