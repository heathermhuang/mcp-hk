"""Reusable resource inspection/query, shared by HTTP and MCP."""

import asyncio
import hashlib
import json
import re
import time
from urllib.parse import quote, urlencode, urlsplit, urlunsplit

from .catalogue_store import CatalogueStore
from .contracts import DomainError
from .resource_fetch import fetch
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
    if not isinstance(ids, list) or len(ids) != len(set(ids)) or len(ids) > 100000:
        raise DomainError(
            "SOURCE_TOO_LARGE",
            "ArcGIS ID set is invalid or exceeds the row budget",
            422,
        )
    rows = []
    size = 0
    for offset in range(0, len(ids), 100):
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
        size += len(body)
        if size > 8_000_000:
            raise DomainError(
                "SOURCE_TOO_LARGE",
                "ArcGIS complete layer exceeds the response budget",
                422,
            )
        if (
            value.get("exceededTransferLimit")
            or {r.get("attributes", {}).get(oid) for r in batch} != set(selected)
            or len(batch) != len(selected)
        ):
            raise DomainError(
                "INCOMPLETE_SOURCE",
                "ArcGIS page did not contain every requested identity",
                502,
            )
        rows.extend(batch)
    again, _, _, _ = await read_json(
        root + "/query", {"f": "json", "where": "1=1", "returnIdsOnly": "true"}
    )
    if set(again.get("objectIds", [])) != set(ids):
        raise DomainError("SOURCE_CHANGED", "ArcGIS ID set changed during reading", 409)
    body = json.dumps(rows, sort_keys=True).encode()
    return (
        body,
        {"content-type": "application/json"},
        root,
        {
            "apiFamily": "ArcGIS",
            "scope": "complete_layer_id_set",
            "sourceFields": metadata.get("fields"),
            "coordinateReferenceSystem": metadata.get("extent", {}).get(
                "spatialReference"
            ),
        },
    )


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
                        body, headers, final, status = await fetch(url, conditional)
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
                    if fmt == "API":
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
                    digest = hashlib.sha256(body).hexdigest()
                    check = self.catalogue.accept(
                        resource_id, key, rows, schema, digest, headers, fmt == "PDF"
                    )
                return resource, {"rows": rows, "schema": schema}, check, False
            except Exception as exc:
                code = getattr(exc, "code", "SOURCE_PARSE_ERROR")
                status = (
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
                            }
                            else (
                                "capacity_limited"
                                if code in {"SOURCE_TOO_LARGE", "SOURCE_TOO_COMPLEX"}
                                else (
                                    "schema_drift"
                                    if code == "SCHEMA_DRIFT"
                                    else "unavailable"
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
                    "contentHash": check.get("hash"),
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
        try:
            return await self._schema(
                resource_id, record_path, sheet, layer, require_fresh, parameters
            )
        except DomainError:
            raise
        except Exception:
            self.catalogue.failure(resource_id, "SOURCE_PARSE_ERROR", "unavailable")
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
        return {
            **self.envelope(resource, value, check, stale),
            "recordCount": len(value["rows"]),
        }

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
        if version and version != check.get("hash"):
            raise DomainError(
                "RESOURCE_VERSION_CHANGED", "Resource changed; restart pagination", 409
            )
        names = {f["name"] for f in value["schema"]["fields"]}
        if (set(filters or {}) | set(fields or [])) - names:
            raise DomainError(
                "UNKNOWN_FIELD", "Inspect schema for exact source field names", 400
            )
        rows = [
            r
            for r in value["rows"]
            if all(
                k in r and type(r[k]) is type(v) and r[k] == v
                for k, v in (filters or {}).items()
            )
        ]
        items = rows[offset : offset + limit]
        if fields:
            items = [{k: r[k] for k in fields if k in r} for r in items]
        document = value["schema"].get("scope") == "document_pages"
        if document:
            items = [
                (
                    {**r, "sourcePageUrl": resource["url"] + "#page=" + str(r["page"])}
                    if "page" in r
                    else r
                )
                for r in items
            ]
        return {
            **self.envelope(resource, value, check, stale),
            "data": {"items": items},
            "meta": {
                "total": len(rows),
                "offset": offset,
                "nextOffset": offset + limit if offset + limit < len(rows) else None,
                "version": check.get("hash"),
                "pagination": "Pass version on every subsequent page; changed content returns 409.",
                "structuredQueryable": not document,
            },
        }

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
