"""Reusable resource inspection/query, shared by HTTP and MCP."""

import asyncio
import hashlib
import json
import re
import time
import tempfile
import os
from pathlib import Path
from urllib.parse import parse_qs, quote, urlencode, urlsplit, urlunsplit

from .catalogue_store import CatalogueStore
from .contracts import DomainError
from .resource_fields import selected, MISSING, inspect_nested
from .resource_fetch import fetch, fetch_file
from .resource_stream import FileRows
from .resource_formats import parse

SUPPORTED = {
    "CSV",
    "JSON",
    "GEOJSON",
    "XLS",
    "XLSX",
    "XLSM",
    "XML",
    "RSS",
    "GML",
    "KML",
    "PDF",
    "API",
    "ARCGIS",
    "WFS",
    "ZIP",
    "GTFS",
    "KMZ",
}


def params_url(url, params):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(params), ""))


def template_url(url, parameters):
    if any(c in urlsplit(url).netloc for c in ("{", "}", "<", ">")):
        raise DomainError("UNSAFE_SOURCE", "Source host cannot be parameterised", 422)
    tokens = re.findall(r"\{([^{}]+)\}|<([^<>]+)>", url)
    names = {a or b for a, b in tokens}
    if any(
        any(
            s in name.lower()
            for s in ("token", "secret", "password", "api_key", "apikey")
        )
        for name in names
    ):
        raise DomainError(
            "ACCESS_RESTRICTED",
            "Credentialed API templates require a separate authenticated integration",
            422,
        )
    if (
        not isinstance(parameters, dict)
        or set(parameters) != names
        or len(parameters) > 10
    ):
        raise DomainError(
            "PARAMETERS_REQUIRED",
            "Provide exactly these source parameters: " + ", ".join(sorted(names)),
            400,
        )
    for name, value in parameters.items():
        if not isinstance(value, str) or not value or len(value) > 200:
            raise DomainError(
                "INVALID_QUERY",
                "Source parameters must be nonempty strings up to 200 characters",
                400,
            )
        url = url.replace("{" + name + "}", quote(value, safe="")).replace(
            "<" + name + ">", quote(value, safe="")
        )
    return url


async def read_json(url, params=None):
    body, headers, final, status = await fetch(
        params_url(url, params) if params else url
    )
    if status != 200:
        raise DomainError("INVALID_SOURCE", "Expected source response", 502)
    value = json.loads(body)
    if isinstance(value, dict) and value.get("error"):
        raise DomainError("SOURCE_API_ERROR", "Upstream API rejected the request", 502)
    return value, body, headers, final


async def hkma_records(url):
    p = urlsplit(url)
    params = {k: v[-1] for k, v in parse_qs(p.query).items()}
    params.pop("fields", None)
    params.update(pagesize=1000, offset=0)
    records = []
    expected = None
    hashes = []
    size = 0
    page_hashes = set()
    for _ in range(100):
        value, body, headers, final = await read_json(params_url(url, params))
        if value.get("header", {}).get("success") is not True:
            raise DomainError("SOURCE_API_ERROR", "HKMA rejected the API query", 502)
        result = value.get("result", {})
        total = result.get("datasize")
        batch = result.get("records")
        if (
            not isinstance(total, int)
            or not isinstance(batch, list)
            or (expected is not None and expected != total)
        ):
            raise DomainError(
                "INCOMPLETE_SOURCE", "HKMA count changed or response was malformed", 422
            )
        expected = total
        if expected > 100000:
            raise DomainError("SOURCE_TOO_LARGE", "HKMA result exceeds row budget", 422)
        if len(batch) > 1000 or (not batch and len(records) < expected):
            raise DomainError(
                "INCOMPLETE_SOURCE", "HKMA pagination ended before total", 422
            )
        signature = hashlib.sha256(
            json.dumps(batch, sort_keys=True).encode()
        ).hexdigest()
        if batch and signature in page_hashes:
            raise DomainError("INCOMPLETE_SOURCE", "HKMA returned a repeated page", 422)
        page_hashes.add(signature)
        hashes.append(hashlib.sha256(body).hexdigest())
        records.extend(batch)
        size += len(body)
        if size > 8_000_000:
            raise DomainError(
                "SOURCE_TOO_LARGE",
                "HKMA pages exceed bounded representation budget",
                422,
            )
        if len(records) == expected:
            break
        if len(records) > expected:
            raise DomainError(
                "INCOMPLETE_SOURCE", "HKMA returned more rows than total", 422
            )
        params["offset"] = len(records)
    if len(records) != expected:
        raise DomainError("INCOMPLETE_SOURCE", "HKMA pages incomplete", 422)
    return (
        json.dumps(records, ensure_ascii=False).encode(),
        headers,
        final,
        {
            "apiFamily": "HKMA",
            "scope": "complete_api_pages_live",
            "sourceMatched": expected,
            "pageSourceHashes": hashes,
            "consistency": "Upstream pages are live; no upstream snapshot token is available.",
        },
    )


async def census_table(url):
    p = urlsplit(url)
    query = parse_qs(p.query)
    table_id = query.get("id", [""])[0]
    if not re.fullmatch(r"[0-9]{3}-[0-9]{5}[A-Z]?", table_id):
        raise DomainError(
            "API_ADAPTER_REQUIRED", "Census table identifier is not supported", 422
        )
    lang = (
        "tc"
        if p.path.startswith("/tc/")
        else "sc" if p.path.startswith("/sc/") else "en"
    )
    endpoint = "https://www.censtatd.gov.hk/api/get.php?" + urlencode(
        {"id": table_id, "lang": lang, "full_series": "1"}
    )
    value, body, headers, final = await read_json(endpoint)
    data = value.get("dataSet")
    header = value.get("header", {})
    if (
        header.get("status", {}).get("code") != 0
        or not isinstance(data, list)
        or header.get("count", {}).get("noOfRecords") != len(data)
    ):
        raise DomainError(
            "INCOMPLETE_SOURCE", "Census API table count/schema did not reconcile", 422
        )
    return (
        body,
        headers,
        final,
        {
            "apiFamily": "C&SD tables",
            "accessMethod": "official_json_equivalent_for_download_page",
            "originalResourceUrl": url,
            "scope": "complete_api_table",
            "sourceMatched": len(data),
        },
    )


async def arcgis(url, layer):
    p = urlsplit(url)
    root = urlunsplit(
        (p.scheme, p.netloc, p.path.rstrip("/").removesuffix("/query"), "", "")
    )
    if not root.rsplit("/", 1)[-1].isdigit():
        if layer is None:
            metadata, _, _, _ = await read_json(root, {"f": "json"})
            raise DomainError(
                "LAYER_REQUIRED",
                "Choose a layer ID from: "
                + json.dumps(metadata.get("layers", []))[:1000],
                400,
            )
        root += "/" + str(layer)
    metadata, _, _, _ = await read_json(root, {"f": "json"})
    oid = metadata.get("objectIdField") or next(
        (
            f["name"]
            for f in metadata.get("fields", [])
            if f.get("type") == "esriFieldTypeOID"
        ),
        None,
    )
    if not oid:
        raise DomainError(
            "UNSUPPORTED_API", "ArcGIS layer lacks an object ID field", 422
        )
    identities, _, _, _ = await read_json(
        root + "/query", {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
    )
    ids = identities.get("objectIds")
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or len(ids) > 1_000_000:
        raise DomainError(
            "SOURCE_TOO_LARGE",
            "ArcGIS ID set is invalid or exceeds the row budget",
            422,
        )
    fd, name = tempfile.mkstemp(prefix="mcp-hk-arcgis-", suffix=".json")
    os.close(fd)
    path = Path(name)
    count = 0
    chain = hashlib.sha256()
    started = time.monotonic()
    try:
        with path.open("wb") as output:
            output.write(b"[")
            for offset in range(0, len(ids), 100):
                if time.monotonic() - started > 120:
                    raise DomainError(
                        "SOURCE_TIMEOUT",
                        "Complete ArcGIS read exceeded its deadline",
                        504,
                    )
                selected = ids[offset : offset + 100]
                value, body, _, _ = await read_json(
                    root + "/query",
                    {
                        "f": "json",
                        "objectIds": ",".join(str(i) for i in selected),
                        "outFields": "*",
                        "returnGeometry": "true",
                    },
                )
                batch = value.get("features", [])
                chain.update(hashlib.sha256(body).digest())
                if (
                    value.get("exceededTransferLimit")
                    or {r.get("attributes", {}).get(oid) for r in batch}
                    != set(selected)
                    or len(batch) != len(selected)
                ):
                    raise DomainError(
                        "INCOMPLETE_SOURCE",
                        "ArcGIS page did not contain every requested identity",
                        502,
                    )
                for record in batch:
                    if count:
                        output.write(b",")
                    output.write(json.dumps(record, ensure_ascii=False).encode())
                    count += 1
                if output.tell() > 128_000_000:
                    raise DomainError(
                        "SOURCE_TOO_LARGE",
                        "ArcGIS layer exceeds the streamed file budget",
                        422,
                    )
            output.write(b"]")
        again, _, _, _ = await read_json(
            root + "/query", {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
        )
        if set(again.get("objectIds", [])) != set(ids):
            raise DomainError(
                "SOURCE_CHANGED", "ArcGIS ID set changed during reading", 409
            )
        extra = {
            "apiFamily": "ArcGIS",
            "scope": "complete_layer_id_set",
            "sourceFields": metadata.get("fields"),
            "sourceMatched": len(ids),
            "pageResponseChainHash": chain.hexdigest(),
            "coordinateReferenceSystem": metadata.get("extent", {}).get(
                "spatialReference"
            ),
        }
        if path.stat().st_size <= 8_000_000:
            body = path.read_bytes()
            path.unlink()
        else:
            body = path
        return body, {"content-type": "application/json"}, root, extra
    except BaseException:
        path.unlink(missing_ok=True)
        raise


async def wfs(url, type_name):
    if not type_name:
        raise DomainError(
            "TYPE_NAME_REQUIRED",
            "Select a WFS feature type from the source GetCapabilities using recordPath",
            400,
        )
    if len(type_name) > 200 or any(
        c
        not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_:.".lower()
        + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        for c in type_name
    ):
        raise DomainError("INVALID_RECORD_PATH", "Invalid WFS type name", 400)
    endpoint = urlsplit(url)._replace(query="").geturl()
    value, body, headers, final = await read_json(
        endpoint,
        {
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": type_name,
            "outputFormat": "application/json",
            "count": 100000,
        },
    )
    features = value.get("features")
    matched = value.get("numberMatched", value.get("totalFeatures"))
    if (
        not isinstance(features, list)
        or not isinstance(matched, (int, str))
        or str(matched) == "unknown"
        or int(matched) != len(features)
    ):
        raise DomainError(
            "INCOMPLETE_SOURCE",
            "WFS response does not prove complete feature coverage",
            422,
        )
    return (
        body,
        headers,
        final,
        {
            "apiFamily": "WFS",
            "scope": "complete_feature_type",
            "sourceMatched": int(matched),
        },
    )


class Resources:
    def __init__(self, store):
        self.catalogue = CatalogueStore(store)
        self.slots = asyncio.Semaphore(2)
        self.locks = {}

    async def load(
        self,
        resource_id,
        record_path="",
        sheet="",
        layer=None,
        require_fresh=False,
        parameters=None,
    ):
        if (
            len(record_path) > 300
            or len(sheet) > 100
            or (layer is not None and not 0 <= layer <= 10000)
        ):
            raise DomainError("INVALID_QUERY", "Invalid source selector", 400)
        resource = self.catalogue.resource(resource_id)
        key = hashlib.sha256(
            json.dumps(
                [resource_id, record_path, sheet, layer]
                + ([parameters] if parameters else []),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        # Per-resource lock coalesces cache misses; locks contain no pending source I/O.
        if len(self.locks) > 1000:
            self.locks = {k: v for k, v in self.locks.items() if v.locked()}
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = self.catalogue.cached(key)
            check = self.catalogue.check(resource_id, key)
            if (
                cached
                and check.get("status") in {"queryable", "document"}
                and check.get("hash") == cached["hash"]
                and check.get("validated")
                and time.time() - check["validated"]
                < (300 if resource.get("isApi") else 86400)
            ):
                return resource, cached["value"], check, False
            if (
                cached
                and check.get("status") not in {"queryable", "document"}
                and time.time() - check.get("checked", 0) < 300
            ):
                if require_fresh:
                    raise DomainError(
                        check.get("reason") or "SOURCE_UNAVAILABLE",
                        "Recent source failure; retry after the cooldown",
                        503,
                    )
                return resource, cached["value"], check, True
            try:
                fmt = resource["format"]
                if fmt not in SUPPORTED:
                    raise DomainError(
                        "UNSUPPORTED_FORMAT", "Reader not implemented for " + fmt, 422
                    )
                url = resource["url"]
                if any(c in url for c in ("{", "}", "<", ">")) or parameters:
                    url = template_url(url, parameters or {})
                extra = {}
                async with self.slots:
                    if (
                        "featureserver" in url.lower()
                        or "mapserver" in url.lower()
                        or fmt == "ARCGIS"
                    ):
                        body, headers, final, extra = await arcgis(url, layer)
                        fmt = "JSON"
                    elif urlsplit(url).hostname == "api.hkma.gov.hk":
                        body, headers, final, extra = await hkma_records(url)
                        fmt = "JSON"
                        record_path = ""
                    elif (
                        urlsplit(url).hostname == "www.censtatd.gov.hk"
                        and urlsplit(url).path.endswith("/web_table.html")
                        and fmt in {"CSV", "XLSX", "XLS"}
                    ):
                        body, headers, final, extra = await census_table(url)
                        fmt = "JSON"
                        record_path = record_path or "dataSet"
                    elif fmt == "WFS":
                        body, headers, final, extra = await wfs(url, record_path)
                        fmt = "GEOJSON"
                        record_path = ""
                    else:
                        conditional = {}
                        # Only revalidate the exact cached representation.
                        if cached and check.get("etag"):
                            conditional["If-None-Match"] = check["etag"]
                        if cached and check.get("modified"):
                            conditional["If-Modified-Since"] = check["modified"]
                        try:
                            body, headers, final, status = await fetch(url, conditional)
                        except DomainError as exc:
                            if exc.code != "SOURCE_TOO_LARGE" or fmt not in {
                                "CSV",
                                "JSON",
                                "GEOJSON",
                                "API",
                            }:
                                raise
                            body, headers, final, status = await fetch_file(url)
                        if status == 304:
                            if not cached:
                                raise DomainError(
                                    "INVALID_SOURCE", "304 without cached records", 502
                                )
                            value = cached["value"]
                            check = self.catalogue.accept(
                                resource_id,
                                key,
                                value["rows"],
                                value["schema"],
                                cached["hash"],
                                {
                                    **{
                                        "etag": check.get("etag"),
                                        "last-modified": check.get("modified"),
                                    },
                                    **headers,
                                },
                                fmt == "PDF",
                            )
                            return resource, value, check, False
                    content_type = headers.get("content-type", "").lower()
                    if fmt == "API" and not isinstance(body, Path):
                        if "json" in content_type or body.lstrip().startswith(
                            (b"{", b"[")
                        ):
                            fmt = "JSON"
                        elif "xml" in content_type:
                            fmt = "XML"
                        else:
                            raise DomainError(
                                "API_ADAPTER_REQUIRED",
                                "API is a specification/interactive endpoint; a record adapter is required",
                                422,
                            )
                    # CSDI URLs sometimes publish a JSON document behind an API label.
                    if isinstance(body, Path):
                        rows = await asyncio.to_thread(FileRows, body, fmt, record_path)
                        schema = rows.schema
                        if extra.get("streamCountPath"):
                            import ijson

                            with body.open("rb") as source:
                                expected = next(
                                    ijson.items(source, extra["streamCountPath"]), None
                                )
                            if expected != len(rows):
                                raise DomainError(
                                    "INCOMPLETE_SOURCE",
                                    "Census streamed record count mismatch",
                                    422,
                                )
                    else:
                        rows, schema = await asyncio.to_thread(
                            parse, body, fmt, record_path, sheet
                        )

                    schema.update(extra)
                    schema["sourceResponseComplete"] = True
                    schema["cacheTTLSeconds"] = 300 if resource.get("isApi") else 86400
                    schema.setdefault(
                        "scope",
                        "source_response" if resource.get("isApi") else "complete_file",
                    )
                    schema.setdefault(
                        "datasetCompleteness",
                        ("Not inferred from a file or a single API response."),
                    )
                    schema["resolvedSourceUrl"] = final
                    digest = (
                        rows.records_digest
                        if isinstance(rows, FileRows)
                        else hashlib.sha256(body).hexdigest()
                    )
                    check = self.catalogue.accept(
                        resource_id, key, rows, schema, digest, headers, fmt == "PDF"
                    )
                return resource, {"rows": rows, "schema": schema}, check, False
            except Exception as exc:
                code = (
                    exc.code if isinstance(exc, DomainError) else "SOURCE_PARSE_ERROR"
                )
                status = (
                    "needs_adapter"
                    if code in {"SOURCE_PARSE_ERROR", "SOURCE_SCHEMA_CHANGED"}
                    else (
                        "unsupported"
                        if code
                        in {
                            "UNSUPPORTED_FORMAT",
                            "API_ADAPTER_REQUIRED",
                            "PARAMETER_ADAPTER_REQUIRED",
                            "UNSUPPORTED_API",
                            "UNSUPPORTED_ENCODING",
                        }
                        else (
                            "restricted"
                            if code == "ACCESS_RESTRICTED"
                            else (
                                "needs_selection"
                                if code
                                in {
                                    "SHEET_REQUIRED",
                                    "LAYER_REQUIRED",
                                    "INVALID_SHEET",
                                    "INVALID_RECORD_PATH",
                                    "TYPE_NAME_REQUIRED",
                                    "PARAMETERS_REQUIRED",
                                    "RECORD_PATH_REQUIRED",
                                }
                                else (
                                    "capacity_limited"
                                    if code
                                    in {"SOURCE_TOO_LARGE", "SOURCE_TOO_COMPLEX"}
                                    else (
                                        "schema_drift"
                                        if code == "SCHEMA_DRIFT"
                                        else "unavailable"
                                    )
                                )
                            )
                        )
                    )
                )
                self.catalogue.failure(resource_id, code, status, key)
                if cached and not require_fresh:
                    return (
                        resource,
                        cached["value"],
                        self.catalogue.check(resource_id, key),
                        True,
                    )
                if isinstance(exc, DomainError):
                    raise
                raise DomainError(
                    "SOURCE_PARSE_ERROR",
                    "Source cannot be safely parsed; failure receipt recorded",
                    422,
                ) from None

    def envelope(self, resource, value, check, stale=False):
        dataset = self.catalogue.dataset(resource["datasetId"])
        return {
            "resource": resource,
            "dataset": dataset,
            "schema": value["schema"],
            "provenance": [
                {
                    "sourceUrl": resource["url"],
                    "catalogueUrl": resource["sourceUrl"],
                    "attribution": dataset["provider"]
                    + (
                        " / Common Spatial Data Infrastructure (CSDI) Portal"
                        if resource["catalogue"] == "CSDI"
                        else " / DATA.GOV.HK"
                    ),
                    "termsUrl": resource["termsUrl"],
                    "retrievedAt": check.get("retrieved"),
                    "lastCheckedAt": check.get("checked"),
                    "lastValidatedAt": check.get("validated"),
                    "publicationDate": resource.get("publicationDate"),
                    "referencePeriod": dataset.get("referencePeriod"),
                    "contentHash": value["schema"].get("sourceContentHash")
                    or check.get("hash"),
                    "stale": stale,
                }
            ],
            "warnings": (
                [
                    {
                        "code": "STALE_ACCEPTED_RESOURCE",
                        "message": "Source check failed; serving the previous accepted representation.",
                    }
                ]
                if stale
                else []
            ),
        }

    async def schema(
        self,
        resource_id,
        record_path="",
        sheet="",
        layer=None,
        require_fresh=False,
        parameters=None,
    ):
        self.catalogue.resource(resource_id)
        started = time.time()
        try:
            return await self._schema(
                resource_id, record_path, sheet, layer, require_fresh, parameters
            )
        except DomainError as exc:
            if self.catalogue.check(resource_id).get("checked", 0) < started:
                self.catalogue.failure(
                    resource_id,
                    exc.code,
                    "restricted" if exc.code == "ACCESS_RESTRICTED" else "unavailable",
                )
            raise
        except Exception:
            self.catalogue.failure(resource_id, "SOURCE_PARSE_ERROR", "needs_adapter")
            raise DomainError(
                "SOURCE_PARSE_ERROR",
                "Source schema inspection failed; receipt recorded",
                422,
            ) from None

    async def _schema(
        self,
        resource_id,
        record_path="",
        sheet="",
        layer=None,
        require_fresh=False,
        parameters=None,
    ):
        resource = self.catalogue.resource(resource_id)
        if any(c in resource["url"] for c in ("{", "}", "<", ">")) and not parameters:
            try:
                template_url(resource["url"], {})
            except DomainError as exc:
                if exc.code != "PARAMETERS_REQUIRED":
                    raise
            if not self.catalogue.check(resource_id).get("validated"):
                self.catalogue.failure(
                    resource_id, "PARAMETERS_REQUIRED", "needs_selection"
                )
            return {
                "resource": resource,
                "selectionRequired": "parameters",
                "parameters": sorted(
                    {
                        a or b
                        for a, b in re.findall(
                            r"\{([^{}]+)\}|<([^<>]+)>", resource["url"]
                        )
                    }
                ),
                "recordCount": None,
                "structuredQueryable": False,
            }
        if resource["format"] == "WFS" and not record_path:
            from defusedxml import ElementTree as ET

            body, _, _, _ = await fetch(
                params_url(
                    resource["url"],
                    {
                        "service": "WFS",
                        "request": "GetCapabilities",
                        "version": "2.0.0",
                    },
                )
            )
            root = ET.fromstring(body)
            names = [
                e.text
                for e in root.iter()
                if e.tag.rsplit("}", 1)[-1] == "Name" and e.text
            ]
            self.catalogue.failure(resource_id, "TYPE_NAME_REQUIRED", "needs_selection")
            return {
                "resource": resource,
                "selectionRequired": "recordPath",
                "featureTypes": names,
                "structuredQueryable": False,
                "recordCount": None,
            }
        if (
            (
                "featureserver" in resource["url"].lower()
                or "mapserver" in resource["url"].lower()
            )
            and not resource["url"].rstrip("/").rsplit("/", 1)[-1].isdigit()
            and layer is None
        ):
            value, _, _, _ = await read_json(resource["url"], {"f": "json"})
            if not self.catalogue.check(resource_id).get("validated"):
                self.catalogue.failure(resource_id, "LAYER_REQUIRED", "needs_selection")
            return {
                "resource": resource,
                "selectionRequired": "layer",
                "layers": value.get("layers", []) + value.get("tables", []),
                "structuredQueryable": False,
                "recordCount": None,
            }
        resource, value, check, stale = await self.load(
            resource_id, record_path, sheet, layer, require_fresh, parameters
        )
        try:
            return {
                **self.envelope(resource, value, check, stale),
                "recordCount": len(value["rows"]),
            }
        finally:
            if isinstance(value["rows"], FileRows):
                value["rows"].close()

    async def query(
        self,
        resource_id,
        filters=None,
        fields=None,
        limit=20,
        offset=0,
        record_path="",
        sheet="",
        layer=None,
        require_fresh=False,
        version=None,
        parameters=None,
    ):
        if (
            not 1 <= limit <= 100
            or not 0 <= offset <= 100000
            or len(filters or {}) > 10
            or len(fields or []) > 100
        ):
            raise DomainError(
                "INVALID_QUERY", "Query exceeds filter, projection or page limits", 400
            )
        if not isinstance(filters or {}, dict) or any(
            not isinstance(v, (str, int, float, bool, type(None)))
            for v in (filters or {}).values()
        ):
            raise DomainError(
                "INVALID_FILTER", "Equality filters require scalar source values", 400
            )
        resource, value, check, stale = await self.load(
            resource_id, record_path, sheet, layer, require_fresh, parameters
        )

        def build_result():
            if version and version != check.get("hash"):
                raise DomainError(
                    "RESOURCE_VERSION_CHANGED",
                    "Resource changed; restart pagination",
                    409,
                )
            if "queryFields" not in value["schema"]:
                value["schema"]["queryFields"] = inspect_nested(value["rows"])
            names = {
                f["name"]
                for f in value["schema"]["fields"] + value["schema"]["queryFields"]
            }
            if (set(filters or {}) | set(fields or [])) - names:
                raise DomainError(
                    "UNKNOWN_FIELD", "Inspect schema for exact source field names", 400
                )
            total = 0
            items = []
            for r in value["rows"]:
                if all(
                    selected(r, k) is not MISSING
                    and type(selected(r, k)) is type(v)
                    and selected(r, k) == v
                    for k, v in (filters or {}).items()
                ):
                    if offset <= total < offset + limit:
                        items.append(
                            {
                                k: selected(r, k)
                                for k in fields
                                if selected(r, k) is not MISSING
                            }
                            if fields
                            else r
                        )
                    total += 1
            if len(json.dumps(items, ensure_ascii=False).encode()) > 512_000:
                raise DomainError(
                    "RESPONSE_TOO_LARGE",
                    "Select a narrower recordPath, fewer fields or a smaller page",
                    422,
                )
            document = value["schema"].get("scope") == "document_pages"
            if document:
                items = [
                    (
                        {
                            **r,
                            "sourcePageUrl": resource["url"]
                            + "#page="
                            + str(r["page"]),
                        }
                        if "page" in r
                        else r
                    )
                    for r in items
                ]
            return {
                **self.envelope(resource, value, check, stale),
                "data": {"items": items},
                "meta": {
                    "total": total,
                    "offset": offset,
                    "nextOffset": offset + limit if offset + limit < total else None,
                    "version": check.get("hash"),
                    "pagination": "Pass version on every subsequent page; changed content returns 409.",
                    "structuredQueryable": not document,
                },
            }

        try:
            return await asyncio.to_thread(build_result)
        finally:
            if isinstance(value["rows"], FileRows):
                value["rows"].close()

    async def audit(self, batch=20):
        if not 1 <= batch <= 100:
            raise ValueError("Audit batch must be 1..100")
        generation = self.catalogue.head()
        with self.catalogue.store.connect() as db:
            prior = db.execute(
                "SELECT * FROM resource_audit_cursor WHERE id=1"
            ).fetchone()
            cursor = (
                prior["cursor"] if prior and prior["generation"] == generation else ""
            )
            ids = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM inventory_resources WHERE generation=? AND id>? ORDER BY id LIMIT ?",
                    (generation, cursor, batch),
                )
            ]
        for rid in ids:
            resource = self.catalogue.resource(rid)
            check = self.catalogue.check(rid)
            # Do not repeat unchanged structural failures; metadata change produces a new audit generation.
            if check.get("status") in {
                "unsupported",
                "schema_drift",
                "capacity_limited",
                "needs_selection",
            }:
                continue
            if check.get("validated") and time.time() - check["validated"] < (
                300 if resource.get("isApi") else 86400
            ):
                continue
            try:
                await self.schema(rid, require_fresh=True)
            except DomainError:
                pass
        with self.catalogue.store.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO resource_audit_cursor VALUES (1,?,?)",
                (generation, ids[-1] if ids else ""),
            )
        return {
            "generation": generation,
            "processed": len(ids),
            "cursor": ids[-1] if ids else None,
            "cycleComplete": not ids,
        }
