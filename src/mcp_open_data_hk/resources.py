"""Reusable resource inspection/query, shared by HTTP and MCP."""

import asyncio
import hashlib
import heapq
import json
import re
import time
import tempfile
import os
import threading
import unicodedata
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlsplit, urlunsplit

from .catalogue_store import CatalogueStore, unpack
from .contracts import DomainError
from . import census_reports
from .resource_protocols import protocol, pinned_feature_type, HKMA_PAGING_CONTRACT
from . import transport, capabilities, resource_selections
from .quality import freshness, semantic_quality
from .observation_quality import (
    REVISION as OBSERVATION_REVISION,
    hko_current,
    qualify as qualify_observations,
    observation_freshness,
)
from .review_config import SOURCE_REVIEW, CONCURRENCY, BATCH_SIZE, RUN_SECONDS
from .source_contracts import annotate as annotate_source_contract, typed_bindings
from .resource_predicates import Predicates
from .spatial_query import qualify as qualify_spatial, Nearby
from .spatial_profiles import profile_for, fingerprint as profile_fingerprint
from .resource_fields import selected, MISSING, inspect_nested
from .resource_fetch import fetch, fetch_file
from .resource_stream import FileRows
from .resource_formats import parse
from .resource_serializations import read as read_serialization
from . import published_files
from .published_requests import (
    request_template,
    annotate_response,
    validate_parameters,
    parameter_choices,
    non_record_interface,
    request_requirements,
    bind_request,
)
from .resource_codec import (
    typed_filters as decode_filters,
    presentation as present,
    MAX_RESPONSE_BYTES,
)

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


class ValidationOnlyRows:
    """Accepted count for private schema review; never a replacement for records."""

    def __init__(self, count):
        self.count = count

    def __len__(self):
        return self.count

    def __iter__(self):
        raise TypeError("Review metadata does not contain source records")


def params_url(url, params):
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, p.path, urlencode(params), ""))


def bracket_parameter(pair):
    key, separator, value = pair.partition("=")
    if separator and re.fullmatch(r"\[[A-Za-z_][A-Za-z0-9_,:. -]*\]", unquote(value)):
        return unquote(key)
    return None


def source_parameters(url):
    url = request_template(url)
    names = {a or b for a, b in re.findall(r"\{([^{}]+)\}|<([^<>]+)>", url)}
    names.update(
        name
        for pair in urlsplit(url).query.split("&")
        if (name := bracket_parameter(pair))
    )
    return sorted(names)


def template_url(url, parameters):
    bound = bind_request(url, parameters)
    if bound is not None:
        return bound
    specification = url
    url = request_template(url)
    if any(c in urlsplit(url).netloc for c in ("{", "}", "<", ">")):
        raise DomainError("UNSAFE_SOURCE", "Source host cannot be parameterised", 422)
    names = set(source_parameters(url))
    if any(
        any(
            s in name.lower().replace("-", "_")
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
    validate_parameters(specification, parameters)
    for name, value in parameters.items():
        url = url.replace("{" + name + "}", quote(value, safe="")).replace(
            "<" + name + ">", quote(value, safe="")
        )
    parts = urlsplit(url)
    query = []
    for pair in parts.query.split("&"):
        name = bracket_parameter(pair)
        query.append(
            pair.partition("=")[0] + "=" + quote(parameters[name], safe="")
            if name
            else pair
        )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, "&".join(query), parts.fragment)
    )


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
    records, hashes, page_counts = [], [], []
    size, requests = 0, 0
    started = time.monotonic()
    page_hashes = set()

    async def page(offset):
        nonlocal size, requests
        if requests >= 100:
            raise DomainError(
                "SOURCE_TOO_LARGE", "HKMA read exceeds request budget", 422
            )
        requests += 1
        remaining = 120 - (time.monotonic() - started)
        if remaining <= 0:
            raise DomainError(
                "SOURCE_TIMEOUT", "Complete HKMA read exceeded its deadline", 504
            )
        try:
            value, body, headers, final = await asyncio.wait_for(
                read_json(params_url(url, {**params, "offset": offset})), remaining
            )
        except asyncio.TimeoutError:
            raise DomainError(
                "SOURCE_TIMEOUT", "Complete HKMA read exceeded its deadline", 504
            ) from None
        size += len(body)
        if size > 8_000_000:
            raise DomainError(
                "SOURCE_TOO_LARGE",
                "HKMA pages exceed bounded representation budget",
                422,
            )
        if value.get("header", {}).get("success") is not True:
            raise DomainError("SOURCE_API_ERROR", "HKMA rejected the API query", 502)
        result = value.get("result", {})
        count, batch = result.get("datasize"), result.get("records")
        if (
            type(count) is not int
            or not isinstance(batch, list)
            or count != len(batch)
            or not 0 <= count <= params["pagesize"]
        ):
            raise DomainError(
                "INCOMPLETE_SOURCE", "HKMA page count/schema did not reconcile", 422
            )
        hashes.append(hashlib.sha256(body).hexdigest())
        signature = hashlib.sha256(
            json.dumps(batch, sort_keys=True).encode()
        ).hexdigest()
        return batch, signature, headers, final

    first, last, terminal = None, None, None
    first_headers, first_source = None, None
    while True:
        offset = len(records)
        batch, signature, headers, final = await page(offset)
        if batch and signature in page_hashes:
            raise DomainError("INCOMPLETE_SOURCE", "HKMA returned a repeated page", 422)
        page_hashes.add(signature)
        if first is None:
            first = signature
            first_headers, first_source = headers, final
        page_counts.append(len(batch))
        if not batch:
            terminal = offset
            break
        last = offset, signature
        records.extend(batch)
        if len(records) > 100000:
            raise DomainError("SOURCE_TOO_LARGE", "HKMA result exceeds row budget", 422)
        # A terminal response plus two boundary rechecks must still fit the
        # existing 100-request ceiling; never accept a capped traversal.
        if requests + 3 > 100:
            raise DomainError(
                "SOURCE_TOO_LARGE", "HKMA read exceeds request budget", 422
            )

    for offset, expected in dict([(0, first)] + ([last] if last else [])).items():
        _, signature, _, _ = await page(offset)
        if signature != expected:
            raise DomainError(
                "SOURCE_CHANGED", "HKMA boundary page changed during reading", 409
            )
    # Validators from one response cannot validate the compiled live view.
    composite_headers = {"content-type": "application/json"}
    if first_headers.get("_mcp_source_transport"):
        composite_headers["_mcp_source_transport"] = first_headers[
            "_mcp_source_transport"
        ]
    return (
        json.dumps(records, ensure_ascii=False).encode(),
        composite_headers,
        first_source,
        {
            "apiFamily": "HKMA",
            "hkmaPaginationContract": HKMA_PAGING_CONTRACT,
            "scope": "complete_api_pages_live",
            "sourceMatched": len(records),
            "pageSourceHashes": hashes,
            "countEvidence": {
                "basis": "native_per_page_counts_and_explicit_empty_terminal_page",
                "pageCounts": page_counts,
                "terminalOffset": terminal,
                "terminalRows": 0,
                "boundaryPagesRevalidated": True,
                "boundaryOffsets": sorted(
                    dict([(0, first)] + ([last] if last else []))
                ),
                "independentGlobalTotal": None,
                "providerRequests": requests,
            },
            "consistency": "Upstream pages are live; boundary rechecks do not establish an atomic snapshot or stable entity identity.",
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
    if isinstance(ids, list) and len(ids) > 1_000_000:
        raise DomainError(
            "SOURCE_TOO_LARGE",
            "ArcGIS ID set exceeds the existing row budget",
            422,
        )
    if (
        not isinstance(ids, list)
        or any(type(i) is not int for i in ids)
        or len(ids) != len(set(ids))
    ):
        raise DomainError("SOURCE_SCHEMA_CHANGED", "ArcGIS ID set is invalid", 422)
    fd, name = tempfile.mkstemp(prefix="mcp-hk-arcgis-", suffix=".json")
    os.close(fd)
    path = Path(name)
    count = 0
    chain = hashlib.sha256()
    started = time.monotonic()
    try:
        with path.open("wb") as output:
            output.write(b"[")
            offset, requests = 0, 0
            declared_limit = metadata.get("maxRecordCount")
            batch_size = (
                min(500, declared_limit)
                if type(declared_limit) is int and declared_limit > 0
                else 100
            )
            while offset < len(ids):
                if time.monotonic() - started > 120:
                    raise DomainError(
                        "SOURCE_TIMEOUT",
                        "Complete ArcGIS read exceeded its deadline",
                        504,
                    )
                selected = ids[offset : offset + batch_size]
                params = {
                    "f": "json",
                    "objectIds": ",".join(str(i) for i in selected),
                    "outFields": "*",
                    "returnGeometry": "true",
                }
                # Respect conservative GET query limits as well as the provider's
                # declared record limit; no new public source budget is granted.
                while (
                    len(selected) > 1
                    and len(params_url(root + "/query", params)) > 2000
                ):
                    batch_size = max(1, len(selected) - max(1, len(selected) // 10))
                    selected = ids[offset : offset + batch_size]
                    params["objectIds"] = ",".join(str(i) for i in selected)
                requests += 1
                try:
                    value, body, _, _ = await asyncio.wait_for(
                        read_json(root + "/query", params),
                        max(0, 120 - (time.monotonic() - started)),
                    )
                except asyncio.TimeoutError:
                    raise DomainError(
                        "SOURCE_TIMEOUT",
                        "Complete ArcGIS read exceeded its deadline",
                        504,
                    ) from None
                except DomainError as exc:
                    if exc.code != "SOURCE_TOO_LARGE" or len(selected) == 1:
                        raise
                    batch_size = max(1, len(selected) // 2)
                    continue
                batch = value.get("features", [])
                returned = (
                    [
                        r.get("attributes", {}).get(oid)
                        for r in batch
                        if isinstance(r, dict)
                    ]
                    if isinstance(batch, list)
                    else []
                )
                exact = (
                    len(returned) == len(selected)
                    and all(type(i) is int for i in returned)
                    and set(returned) == set(selected)
                )
                if value.get("exceededTransferLimit"):
                    if len(selected) > 1:
                        batch_size = max(1, len(selected) // 2)
                        continue
                    exact = False
                if not exact:
                    raise DomainError(
                        "INCOMPLETE_SOURCE",
                        "ArcGIS page did not contain every requested identity",
                        502,
                    )
                chain.update(hashlib.sha256(body).digest())
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
                offset += len(selected)
            output.write(b"]")
        try:
            again, _, _, _ = await asyncio.wait_for(
                read_json(
                    root + "/query",
                    {"f": "json", "where": "1=1", "returnIdsOnly": "true"},
                ),
                max(0, 120 - (time.monotonic() - started)),
            )
        except asyncio.TimeoutError:
            raise DomainError(
                "SOURCE_TIMEOUT", "Complete ArcGIS read exceeded its deadline", 504
            ) from None
        final_ids = again.get("objectIds")
        if (
            not isinstance(final_ids, list)
            or len(final_ids) != len(ids)
            or any(type(i) is not int for i in final_ids)
            or set(final_ids) != set(ids)
        ):
            raise DomainError(
                "SOURCE_CHANGED", "ArcGIS ID set changed during reading", 409
            )
        extra = {
            "apiFamily": "ArcGIS",
            "scope": "complete_layer_id_set",
            "sourceFields": metadata.get("fields"),
            "sourceMatched": len(ids),
            "pageResponseChainHash": chain.hexdigest(),
            "sourceBatchRequests": requests,
            "sourceBatchSize": batch_size,
            "advertisedMaxRecordCount": declared_limit,
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
    csdi = urlsplit(url).hostname == "portal.csdi.gov.hk" and urlsplit(
        url
    ).path.lower().endswith("/wfsserver")
    # ArcGIS WFS endpoints advertise GEOJSON rather than application/json.
    # Negotiate their published format and prove the complete native count.
    negotiated = urlsplit(url).path.lower().endswith("/wfsserver")
    count_contract = "csdi-wfs-count-1" if csdi else "wfs-2-count-1"
    output_format, before_count = "application/json", None
    if negotiated:
        from defusedxml import ElementTree as ET

        metadata, _, _, _ = await fetch(
            params_url(
                endpoint,
                {"service": "WFS", "version": "2.0.0", "request": "GetCapabilities"},
            )
        )
        root = ET.fromstring(metadata)
        formats = [
            v.text
            for operation in root.iter("{http://www.opengis.net/ows/1.1}Operation")
            if operation.get("name") == "GetFeature"
            for parameter in operation
            if parameter.tag == "{http://www.opengis.net/ows/1.1}Parameter"
            and parameter.get("name") == "outputFormat"
            for v in parameter.iter()
            if v.tag == "{http://www.opengis.net/ows/1.1}Value"
        ]
        output_format = next(
            (
                value
                for wanted in ("application/geo+json", "geojson", "application/json")
                for value in formats
                if value and value.lower() == wanted
            ),
            None,
        )
        if (
            root.tag != "{http://www.opengis.net/wfs/2.0}WFS_Capabilities"
            or not output_format
        ):
            raise DomainError(
                "UNSUPPORTED_API",
                "WFS endpoint does not advertise a supported WFS 2 JSON format",
                422,
            )

        async def hit_count():
            body, _, _, _ = await fetch(
                params_url(
                    endpoint,
                    {
                        "service": "WFS",
                        "version": "2.0.0",
                        "request": "GetFeature",
                        "typeNames": type_name,
                        "resultType": "hits",
                    },
                )
            )
            collection = ET.fromstring(body)
            value = collection.get("numberMatched", "")
            if (
                collection.tag != "{http://www.opengis.net/wfs/2.0}FeatureCollection"
                or collection.get("numberReturned") != "0"
                or re.fullmatch(r"[0-9]{1,10}", value) is None
            ):
                raise DomainError(
                    "INCOMPLETE_SOURCE",
                    "WFS hits did not prove an exact feature count",
                    422,
                )
            return int(value)

        before_count = await hit_count()
        if before_count > 100000:
            raise DomainError(
                "SOURCE_TOO_LARGE",
                "WFS feature type exceeds the existing complete-response row bound",
                422,
            )
        esri_format = next(
            (value for value in formats if value and value.lower() == "esrigeojson"),
            None,
        )
        if before_count > 10000 and esri_format:
            from .wfs_paging import read_pages

            return await read_pages(
                endpoint, type_name, before_count, esri_format, read_json, hit_count
            )
    feature_params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": type_name,
        "outputFormat": output_format,
        "count": 100000,
    }
    try:
        value, body, headers, final = await read_json(endpoint, feature_params)
    except DomainError as exc:
        if not negotiated or exc.code != "SOURCE_TOO_LARGE":
            raise
        path, headers, final, _ = await fetch_file(
            params_url(endpoint, feature_params), maximum=128_000_000
        )
        try:
            after_count = await hit_count()
            if before_count != after_count:
                raise DomainError(
                    "SOURCE_CHANGED", "WFS matched count changed during reading", 409
                )
            return (
                path,
                headers,
                final,
                {
                    "apiFamily": "WFS",
                    "scope": "complete_streamed_feature_type",
                    "sourceMatched": before_count,
                    "streamExpectedMatched": before_count,
                    "wfsContract": count_contract,
                    "outputFormat": output_format,
                    "countEvidence": {
                        "basis": "WFS_2_hits_before_and_after",
                        "beforeMatched": before_count,
                        "afterMatched": after_count,
                        "jsonDeclaredMatched": None,
                        "snapshot": "count_reconciled_not_atomic_publication",
                        "featureIdentity": "not_inferred_when_geojson_omits_native_feature_ids",
                    },
                },
            )
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    features = value.get("features")
    matched = value.get("numberMatched", value.get("totalFeatures"))
    count_evidence = {}
    if negotiated:
        after_count = await hit_count()
        if before_count != after_count:
            raise DomainError(
                "SOURCE_CHANGED", "WFS matched count changed during reading", 409
            )
        if matched not in (None, "unknown") and (
            type(matched) not in {int, str}
            or re.fullmatch(r"[0-9]{1,10}", str(matched)) is None
            or int(matched) != before_count
        ):
            raise DomainError(
                "INCOMPLETE_SOURCE", "WFS JSON count conflicts with native hits", 422
            )
        count_evidence = {
            "wfsContract": count_contract,
            "outputFormat": output_format,
            "countEvidence": {
                "basis": "WFS_2_hits_before_and_after",
                "beforeMatched": before_count,
                "afterMatched": after_count,
                "jsonDeclaredMatched": matched,
                "snapshot": "count_reconciled_not_atomic_publication",
                "featureIdentity": "not_inferred_when_geojson_omits_native_feature_ids",
            },
        }
        matched = before_count
    if (
        not isinstance(features, list)
        or type(matched) not in {int, str}
        or re.fullmatch(r"[0-9]{1,10}", str(matched)) is None
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
            **count_evidence,
        },
    )


def validate_wfs_stream_count(path, actual, expected):
    """Blocking file work stays in a reader worker, before any acceptance write."""
    import ijson

    if actual != expected:
        raise DomainError(
            "INCOMPLETE_SOURCE", "WFS streamed feature count mismatch", 422
        )
    declared = None
    for field in ("numberMatched", "totalFeatures"):
        with path.open("rb") as source:
            value = next(ijson.items(source, field), None)
        if value not in (None, "unknown"):
            if (
                type(value) not in {int, str}
                or re.fullmatch(r"[0-9]{1,10}", str(value)) is None
                or int(value) != expected
            ):
                raise DomainError(
                    "INCOMPLETE_SOURCE",
                    "WFS JSON count conflicts with native hits",
                    422,
                )
            declared = value
    return declared


class Resources:
    def __init__(self, store):
        self.catalogue = CatalogueStore(store)
        self.slots = asyncio.Semaphore(2)
        self.active_scans = 0
        self.scan_limit = 2
        self.scan_seconds = 5.0
        self.review_slots = asyncio.Semaphore(CONCURRENCY)
        self.locks = {}
        self.catalogue.refresh_transport_policies()

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
        source_selection = {
            "recordPath": record_path,
            "sheet": sheet,
            "layer": layer,
            "parameterNames": sorted(parameters or {}),
        }
        resource = self.catalogue.resource(resource_id)
        if non_record_interface(resource["url"]):
            raise DomainError(
                "NON_RECORD_REPRESENTATION",
                "This specification describes map tiles/styles, not a record interface",
                422,
            )
        access_protocol = protocol(resource)
        pinned_type = pinned_feature_type(resource)
        if pinned_type:
            if record_path and record_path != pinned_type:
                raise DomainError(
                    "INVALID_RECORD_PATH",
                    "This source URL pins a different feature type",
                    400,
                )
            record_path = pinned_type
            source_selection["recordPath"] = pinned_type
        if access_protocol in {"WFS", "WMS"} and layer is not None:
            raise DomainError(
                "INVALID_QUERY",
                "An OGC source does not accept a REST layer selector",
                400,
            )
        if access_protocol == "WMS":
            raise DomainError(
                "INVALID_QUERY", "WMS imagery is not a record reader", 422
            )
        profile = transport.profile(resource)
        if census_reports.location(resource["url"]) and (sheet or layer is not None):
            raise DomainError(
                "INVALID_QUERY",
                "Reports require an explicit recordPath, not a workbook sheet or map layer",
                400,
            )
        if profile and profile.arrivals and (record_path or sheet or layer is not None):
            raise DomainError(
                "INVALID_QUERY",
                "Arrival feeds expose fixed rows; omit recordPath, sheet and layer",
                400,
            )
        point_profile = profile_for(resource)
        if (
            (
                sheet
                and resource["format"]
                not in {"XLS", "XLSX", "XLSM", "ZIP", "GTFS", "KMZ"}
                and not published_files.selected(resource["url"], record_path)
            )
            or (
                record_path
                and resource["format"] == "CSV"
                and not census_reports.location(resource["url"])
                and access_protocol != "WFS"
                and not published_files.selected(resource["url"], record_path)
            )
            or (
                layer is not None
                and resource["format"] != "ARCGIS"
                and not any(
                    x in resource["url"].lower() for x in ("featureserver", "mapserver")
                )
            )
        ):
            raise DomainError(
                "INVALID_QUERY", "Selector does not apply to this representation", 400
            )
        query_api = request_template(resource["url"]) != resource["url"]
        ttl = (
            profile.ttl
            if profile
            else (300 if resource.get("isApi") or query_api else 86400)
        )
        force_transport_read = bool(profile and profile.arrivals and require_fresh)
        if profile:
            require_fresh = require_fresh or profile.arrivals
        key = hashlib.sha256(
            json.dumps(
                ["structured-reader-3", resource_id, record_path, sheet, layer]
                + (
                    [
                        (
                            "csdi-wfs-count-1"
                            if urlsplit(resource["url"]).hostname
                            == "portal.csdi.gov.hk"
                            else "wfs-2-count-1"
                        )
                    ]
                    if access_protocol == "WFS"
                    and urlsplit(resource["url"]).path.lower().endswith("/wfsserver")
                    else []
                )
                + ([OBSERVATION_REVISION] if hko_current(resource) else [])
                + (
                    [HKMA_PAGING_CONTRACT]
                    if urlsplit(resource["url"]).hostname == "api.hkma.gov.hk"
                    else []
                )
                + (["rss-feed-root-1"] if resource.get("format") == "RSS" else [])
                + ([transport.REVISION] if profile else [])
                + ([profile_fingerprint(point_profile)] if point_profile else [])
                + ([parameters] if parameters else []),
                sort_keys=True,
            ).encode()
        ).hexdigest()
        previous_key = key if resource.get("format") == "CSV" else None
        if previous_key:
            key = hashlib.sha256(("csv-reader-2:" + previous_key).encode()).hexdigest()
        # Per-resource lock coalesces cache misses; locks contain no pending source I/O.
        if len(self.locks) > 1000:
            self.locks = {k: v for k, v in self.locks.items() if v.locked()}
        lock = self.locks.setdefault(key, asyncio.Lock())
        async with lock:
            cached = await asyncio.to_thread(self.catalogue.cached, key)
            check = self.catalogue.check(resource_id, key)
            review_validation = (
                SOURCE_REVIEW.get()
                and check.get("status") in {"queryable", "document"}
                and check.get("schema_json")
                and check.get("hash")
                and check.get("schema_hash")
                and isinstance(check.get("rows"), int)
            )
            if (
                cached
                and not SOURCE_REVIEW.get()
                and check.get("status") in {"queryable", "document"}
                and check.get("hash") == cached["hash"]
                and check.get("validated")
                and time.time() - check["validated"] < ttl
                and (
                    not profile
                    or not profile.arrivals
                    or (
                        not force_transport_read
                        and cached["value"]["schema"]
                        .get("transport", {})
                        .get("freshUntil", 0)
                        > time.time()
                    )
                )
            ):
                return resource, cached["value"], check, False
            if (
                cached
                and check.get("status") not in {"queryable", "document"}
                and time.time() - check.get("checked", 0)
                < (2 if profile and profile.arrivals else 300)
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
                payload = None
                if profile:
                    url, payload = transport.request(profile, parameters or {})
                elif (
                    source_parameters(url)
                    or any(c in url for c in ("{", "}", "<", ">"))
                    or parameters
                ):
                    url = template_url(url, parameters or {})
                extra = {}
                async with self.review_slots if SOURCE_REVIEW.get() else self.slots:
                    if published_files.profile(resource["url"]):
                        url, fmt, file_context = await published_files.request(
                            resource["url"], record_path, fetch
                        )
                        extra.update(file_context)
                        if layer is not None or (sheet and fmt != "XLSX"):
                            raise DomainError(
                                "INVALID_QUERY",
                                "Selector does not apply to the selected published file",
                                400,
                            )
                        record_path = ""
                    if access_protocol not in {"WFS", "WMS"} and (
                        "featureserver" in url.lower()
                        or "mapserver" in url.lower()
                        or fmt == "ARCGIS"
                    ):
                        body, headers, final, extra = await arcgis(url, layer)
                        fmt = "JSON"
                    elif census_reports.location(url):
                        result = await census_reports.report(url, record_path, fetch)
                        if isinstance(result, dict):
                            raise DomainError(
                                "RECORD_PATH_REQUIRED",
                                "Inspect the report schema and select one table/variable/presentation",
                                400,
                            )
                        body, headers, final, extra = result
                        fmt = "JSON"
                        record_path = "records"
                        sheet = ""
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
                    elif access_protocol == "WFS":
                        body, headers, final, extra = await wfs(url, record_path)
                        if resource["format"] != "WFS":
                            extra["accessMethod"] = (
                                "complete_wfs_json_for_inventoried_feature_type"
                            )
                            extra["originalResourceUrl"] = resource["url"]
                        fmt = extra.get("representationFormat", "GEOJSON")
                        record_path = ""
                    else:
                        conditional = {}
                        # Only revalidate the exact cached representation.
                        if (cached or review_validation) and check.get("etag"):
                            conditional["If-None-Match"] = check["etag"]
                        if (cached or review_validation) and check.get("modified"):
                            conditional["If-Modified-Since"] = check["modified"]
                        try:
                            if profile and profile.arrivals:
                                conditional = {"Cache-Control": "no-cache"}
                            if payload is not None:
                                conditional["Content-Type"] = "application/json"
                                body, headers, final, status = await fetch(
                                    url,
                                    conditional,
                                    payload=json.dumps(payload).encode(),
                                )
                            else:
                                body, headers, final, status = await fetch(
                                    url, conditional
                                )
                        except DomainError as exc:
                            if exc.code != "SOURCE_TOO_LARGE" or fmt not in {
                                "CSV",
                                "JSON",
                                "GEOJSON",
                                "API",
                                "GTFS",
                            }:
                                raise
                            body, headers, final, status = await fetch_file(url)
                        if status == 304 and profile and profile.arrivals:
                            raise DomainError(
                                "SOURCE_RESPONSE_ERROR",
                                "Arrival source did not return a fresh payload",
                                502,
                            )
                        if status == 304:
                            if review_validation:
                                check = await asyncio.to_thread(
                                    self.catalogue.revalidate,
                                    resource_id,
                                    key,
                                    check,
                                    headers,
                                )
                                return (
                                    resource,
                                    {
                                        "rows": ValidationOnlyRows(check["rows"]),
                                        "schema": unpack(check["schema_json"]),
                                    },
                                    check,
                                    False,
                                )
                            if not cached:
                                raise DomainError(
                                    "INVALID_SOURCE", "304 without cached records", 502
                                )
                            value = cached["value"]
                            check = await asyncio.to_thread(
                                self.catalogue.accept,
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
                                previous_key=previous_key,
                            )
                            return resource, value, check, False
                    if profile and not isinstance(body, Path):
                        body, extra = transport.validate(
                            body, profile, parameters or {}, headers
                        )
                        if profile.arrivals:
                            record_path = ""
                            fmt = "JSON"
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
                        if extra.get("streamExpectedMatched") is not None:
                            try:
                                declared = await asyncio.to_thread(
                                    validate_wfs_stream_count,
                                    body,
                                    len(rows),
                                    extra["streamExpectedMatched"],
                                )
                            except BaseException:
                                await asyncio.to_thread(rows.close)
                                raise
                            extra["countEvidence"]["jsonDeclaredMatched"] = declared
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
                        serialized = await asyncio.to_thread(
                            read_serialization,
                            resource,
                            body,
                            record_path,
                            sheet,
                            layer,
                        )
                        if serialized is None:
                            rows, schema = await asyncio.to_thread(
                                parse, body, fmt, record_path, sheet
                            )
                        else:
                            rows, schema = serialized

                    annotate_source_contract(resource, rows, schema)
                    qualify_observations(resource, rows, schema)
                    schema.update(extra)
                    annotate_response(resource["url"], schema, parameters)
                    schema["sourceTransport"] = headers.get(
                        "_mcp_source_transport", "direct"
                    )
                    schema["readerRevision"] = "structured-reader-3"
                    schema["sourceResponseComplete"] = True
                    schema["sourceSelection"] = source_selection
                    schema["cacheTTLSeconds"] = ttl
                    schema.setdefault(
                        "scope",
                        "source_response" if resource.get("isApi") else "complete_file",
                    )
                    schema.setdefault(
                        "datasetCompleteness",
                        ("Not inferred from a file or a single API response."),
                    )
                    await asyncio.to_thread(qualify_spatial, resource, rows, schema)
                    schema["resolvedSourceUrl"] = final
                    digest = (
                        rows.records_digest
                        if isinstance(rows, FileRows)
                        else extra.get("sourceContentHash")
                        or hashlib.sha256(body).hexdigest()
                    )
                    if fmt == "CSV" and not isinstance(rows, FileRows):
                        schema["sourceContentHash"] = digest
                        schema["versionScope"] = "reader_and_source_response"
                        digest = hashlib.sha256(
                            ("csv-reader-2:" + digest).encode()
                        ).hexdigest()
                    check = await asyncio.to_thread(
                        self.catalogue.accept,
                        resource_id,
                        key,
                        rows,
                        schema,
                        digest,
                        headers,
                        fmt == "PDF",
                        previous_key=previous_key,
                    )
                return resource, {"rows": rows, "schema": schema}, check, False
            except Exception as exc:
                code = (
                    exc.code if isinstance(exc, DomainError) else "SOURCE_PARSE_ERROR"
                )
                if (
                    published_files.profile(resource["url"])
                    and code in resource_selections.SELECTION_ERRORS
                ):
                    raise
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
                                if code in resource_selections.SELECTION_ERRORS
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
                await asyncio.to_thread(
                    self.catalogue.failure, resource_id, code, status, key
                )
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
        bindings = typed_bindings(value["schema"])
        if bindings:
            value["schema"]["typedFieldBindings"] = bindings
        observation = observation_freshness(value["schema"])
        live = value["schema"].get("transport")
        if live and live.get("sourceTimestamp"):
            live["sourceAgeSeconds"] = max(
                0, time.time() - transport.timestamp(live["sourceTimestamp"])
            )
            live["cacheAgeSeconds"] = max(
                0, time.time() - check.get("checked", time.time())
            )
        dataset = self.catalogue.dataset(resource["datasetId"])
        return {
            "resource": resource,
            "dataset": dataset,
            "schema": value["schema"],
            "capabilities": capabilities.project(
                resource, check, [check], value["schema"]
            ),
            "quality": semantic_quality(value["schema"]),
            "observationFreshness": observation,
            "validationFreshness": freshness(
                dataset,
                resource,
                check.get("validated"),
                live.get("cacheTTLSeconds") if live else None,
            ),
            "provenance": [
                {
                    "sourceUrl": value["schema"].get("resolvedSourceUrl")
                    or resource["url"],
                    "originalResourceUrl": resource["url"],
                    "catalogueUrl": resource["sourceUrl"],
                    "attribution": dataset["provider"]
                    + (
                        " / Common Spatial Data Infrastructure (CSDI) Portal"
                        if resource["catalogue"] == "CSDI"
                        else " / DATA.GOV.HK"
                    ),
                    "termsUrl": resource["termsUrl"],
                    "retrievedAt": check.get("retrieved"),
                    "observedAt": observation["observedAt"] if observation else None,
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
            )
            + [
                {
                    "code": "SOURCE_OBSERVATION_STALE",
                    "message": "The source observations exceed the two-hour target. A successful download does not make these observations current.",
                }
                for _ in [observation]
                if observation and observation["stale"]
            ]
            + [
                {"code": "TRANSPORT_SERVICE_ADVISORY", "message": message}
                for message in value["schema"]
                .get("transport", {})
                .get("advisories", [])
            ],
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
            result = await self._schema(
                resource_id, record_path, sheet, layer, require_fresh, parameters
            )
            return await self._selection_response(
                resource_id, result, parameters, record_path
            )
        except DomainError as exc:
            if exc.code == "RECORD_PATH_REQUIRED" and hasattr(exc, "record_paths"):
                return await self._selection_response(
                    resource_id,
                    {
                        "resource": self.catalogue.resource(resource_id),
                        "selectionRequired": "recordPath",
                        "schema": {
                            "format": "JSON",
                            "availableRecordPaths": exc.record_paths,
                            "unselectableRecordPathCount": exc.unselectable_paths,
                            "scope": "discovered_source_arrays_not_accepted_records",
                        },
                        "recordCount": None,
                        "structuredQueryable": False,
                    },
                    parameters,
                    record_path,
                )
            if exc.code == "SHEET_REQUIRED" and getattr(exc, "sheets", None):
                return await self._selection_response(
                    resource_id,
                    {
                        "resource": self.catalogue.resource(resource_id),
                        "selectionRequired": "sheet",
                        "sheets": exc.sheets,
                        "sheetCount": exc.sheet_count,
                        "recordCount": None,
                        "structuredQueryable": False,
                    },
                    parameters,
                    record_path,
                )
            if (
                exc.code not in resource_selections.SELECTION_ERRORS
                and (self.catalogue.check(resource_id).get("checked") or 0) < started
            ):
                await asyncio.to_thread(
                    self.catalogue.failure,
                    resource_id,
                    exc.code,
                    "restricted" if exc.code == "ACCESS_RESTRICTED" else "unavailable",
                )
            raise
        except Exception:
            await asyncio.to_thread(
                self.catalogue.failure,
                resource_id,
                "SOURCE_PARSE_ERROR",
                "needs_adapter",
            )
            raise DomainError(
                "SOURCE_PARSE_ERROR",
                "Source schema inspection failed; receipt recorded",
                422,
            ) from None

    async def _selection_response(
        self, resource_id, result, parameters=None, record_path=""
    ):
        groups = resource_selections.describe(resource_id, result)
        file_scoped = published_files.selected(
            result.get("resource", {}).get("url", ""), record_path
        )
        if file_scoped:
            groups = [
                group
                for group in groups
                if group["kind"] != "record_path"
                or any(option["value"] for option in group["options"])
            ]
        scoped = (
            bool(parameters)
            or result.get("selectionRequired") == "parameters"
            or file_scoped
        )
        if scoped:
            # These choices belong to this caller's explicit request. Never
            # publish parameter values or borrow choices from another context.
            for group in groups:
                if file_scoped:
                    group["scopedToRecordPath"] = record_path
                else:
                    group["scopedToParameterNames"] = sorted(parameters or {})
                for option in group["options"]:
                    if parameters:
                        option["nextAction"]["arguments"]["parameters"] = dict(
                            parameters
                        )
                    if file_scoped:
                        option["nextAction"]["arguments"]["recordPath"] = record_path
            result["selections"] = groups
        elif groups:
            await asyncio.to_thread(self.catalogue.record_options, resource_id, groups)
        if not scoped:
            result["selections"] = await asyncio.to_thread(
                self.catalogue.selection_options, resource_id
            )
        if "capabilities" not in result:
            result["capabilities"] = await asyncio.to_thread(
                self.catalogue.capability, resource_id
            )
        return result

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
        if published_files.profile(resource["url"]) and not record_path:
            if sheet or layer is not None or parameters:
                raise DomainError(
                    "INVALID_QUERY",
                    "Select a published file before its workbook sheet",
                    400,
                )
            async with self.review_slots if SOURCE_REVIEW.get() else self.slots:
                result = await published_files.schema(resource["url"], fetch)
            return {"resource": resource, **result}
        if parameters and not transport.profile(resource):
            # Discovery shortcuts must not silently ignore undeclared arguments.
            template_url(resource["url"], parameters)
        interface = non_record_interface(resource["url"])
        if interface:
            if record_path or sheet or layer is not None:
                raise DomainError(
                    "INVALID_QUERY", "Map specifications have no record selectors", 400
                )
            return {
                "resource": resource,
                "sourceInterface": interface,
                "recordCount": None,
                "structuredQueryable": False,
            }
        if census_reports.location(resource["url"]) and (sheet or layer is not None):
            raise DomainError(
                "INVALID_QUERY",
                "Reports require an explicit recordPath, not a workbook sheet or map layer",
                400,
            )
        if census_reports.location(resource["url"]) and (
            not record_path or len(record_path.split("/")) == 1
        ):
            async with self.slots:
                discovered = await census_reports.report(
                    resource["url"], record_path, fetch
                )
            return {"resource": resource, **discovered}
        profile = transport.profile(resource)
        required = profile.required if profile else source_parameters(resource["url"])
        if required and not parameters:
            try:
                if profile:
                    transport.request(profile, {})
                else:
                    template_url(resource["url"], {})
            except DomainError as exc:
                if exc.code != "PARAMETERS_REQUIRED":
                    raise
            check = self.catalogue.check(resource_id)
            # Parameter discovery is not a new source observation. Preserve an
            # upstream failure until another actual request succeeds or fails.
            if not check or check.get("status") in {"pending", "needs_selection"}:
                await asyncio.to_thread(
                    self.catalogue.failure,
                    resource_id,
                    "PARAMETERS_REQUIRED",
                    "needs_selection",
                )
            return {
                "resource": resource,
                "selectionRequired": "parameters",
                "parameters": required,
                **(
                    {"sourceRequest": request_requirements(resource["url"])}
                    if request_requirements(resource["url"])
                    else {}
                ),
                **(
                    {"parameterChoices": parameter_choices(resource["url"])}
                    if parameter_choices(resource["url"])
                    else {}
                ),
                **({"transport": profile.describe()} if profile else {}),
                "recordCount": None,
                "structuredQueryable": False,
            }
        if (
            protocol(resource) == "WFS"
            and not record_path
            and not pinned_feature_type(resource)
        ):
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
                for feature in root.iter()
                if feature.tag.rsplit("}", 1)[-1] == "FeatureType"
                for e in feature
                if e.tag.rsplit("}", 1)[-1] == "Name" and e.text
            ]
            await asyncio.to_thread(
                self.catalogue.failure,
                resource_id,
                "TYPE_NAME_REQUIRED",
                "needs_selection",
            )
            return {
                "resource": resource,
                "selectionRequired": "recordPath",
                "featureTypes": names,
                "structuredQueryable": False,
                "recordCount": None,
            }
        if protocol(resource) not in {"WFS", "WMS"} and (
            (
                "featureserver" in resource["url"].lower()
                or "mapserver" in resource["url"].lower()
            )
            and not resource["url"].rstrip("/").rsplit("/", 1)[-1].isdigit()
            and layer is None
        ):
            value, _, _, _ = await read_json(resource["url"], {"f": "json"})
            if not self.catalogue.check(resource_id).get("validated"):
                await asyncio.to_thread(
                    self.catalogue.failure,
                    resource_id,
                    "LAYER_REQUIRED",
                    "needs_selection",
                )
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
            if require_fresh and (observation_freshness(value["schema"]) or {}).get(
                "stale"
            ):
                raise DomainError(
                    "SOURCE_OBSERVATION_STALE",
                    "Source observations exceed the freshness target",
                    503,
                )
            return {
                **(
                    await asyncio.to_thread(
                        self.envelope, resource, value, check, stale
                    )
                ),
                "recordCount": len(value["rows"]),
            }
        finally:
            if isinstance(value["rows"], FileRows):
                value["rows"].close()

    async def query(self, *args, **kwargs):
        # No waiting queue. Hold admission until the actual worker has completed,
        # even when the HTTP task is cancelled while to_thread is still running.
        if self.active_scans >= self.scan_limit:
            raise DomainError(
                "RESOURCE_BUSY", "Resource readers are busy; retry shortly", 503, 2
            )
        self.active_scans += 1
        stop = threading.Event()
        task = asyncio.create_task(self._query(*args, **kwargs, stop=stop))

        def completed(done):
            self.active_scans -= 1
            if not done.cancelled():
                done.exception()  # Consume errors after an abandoned caller.

        task.add_done_callback(completed)
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            raise

    async def _query(
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
        typed_filters=None,
        presentation=False,
        contains=None,
        predicates=None,
        order_by=None,
        nearby=None,
        stop=None,
    ):
        filters = decode_filters(typed_filters or [], filters)
        if (
            (contains is not None and not isinstance(contains, dict))
            or len(contains or {}) > 10
            or any(
                not isinstance(k, str)
                or len(k) > 300
                or not isinstance(v, str)
                or not v.strip()
                or len(v) > 1000
                for k, v in (contains or {}).items()
            )
        ):
            raise DomainError(
                "INVALID_FILTER",
                "contains requires up to 10 nonempty partial-text filters",
                400,
            )
        text_filters = {
            k: unicodedata.normalize("NFKC", v).casefold()
            for k, v in (contains or {}).items()
        }
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
            if require_fresh and (observation_freshness(value["schema"]) or {}).get(
                "stale"
            ):
                raise DomainError(
                    "SOURCE_OBSERVATION_STALE",
                    "Source observations exceed the freshness target",
                    503,
                )
            deadline = time.monotonic() + self.scan_seconds

            def check_budget():
                if stop.is_set() or time.monotonic() >= deadline:
                    raise DomainError(
                        "RESOURCE_SCAN_DEADLINE",
                        "Scan stopped; narrow the selected source or retry",
                        503,
                        2,
                    )

            check_budget()
            if version and version != check.get("hash"):
                raise DomainError(
                    "RESOURCE_VERSION_CHANGED",
                    "Resource changed; restart pagination",
                    409,
                )
            if "queryFields" not in value["schema"]:
                value["schema"]["queryFields"] = inspect_nested(
                    value["rows"], check_budget
                )
            names = {
                f["name"]
                for f in value["schema"]["fields"] + value["schema"]["queryFields"]
            }
            if (set(filters or {}) | set(fields or []) | set(text_filters)) - names:
                raise DomainError(
                    "UNKNOWN_FIELD", "Inspect schema for exact source field names", 400
                )
            typed = Predicates(
                predicates or [], order_by or [], value["schema"], names, offset, limit
            )
            if nearby is not None and (stale or check.get("status") != "queryable"):
                raise DomainError(
                    check.get("reason") or "STALE_SOURCE",
                    "Nearby binding is held after a source failure; previous records remain available separately",
                    503,
                )
            spatial = (
                Nearby(resource, value["schema"], nearby, offset, limit)
                if nearby is not None
                else None
            )
            if spatial and order_by:
                raise DomainError(
                    "INVALID_QUERY",
                    "Nearby results already order by distance; omit orderBy",
                    400,
                )
            ordered = bool(order_by or spatial)
            if ordered and offset and not version:
                raise DomainError(
                    "RESOURCE_VERSION_REQUIRED",
                    "Pin the accepted version for later ordered pages",
                    400,
                )
            # Unfiltered previews already have an accepted exact row count.
            # Do not rescan the full source merely to rediscover that count.
            unfiltered = (
                not filters
                and not text_filters
                and not predicates
                and not order_by
                and not spatial
            )
            total = len(value["rows"]) if unfiltered else 0
            items = []

            def matches(row):
                return (
                    all(
                        (actual := selected(row, k)) is not MISSING
                        and type(actual) is type(v)
                        and actual == v
                        for k, v in (filters or {}).items()
                    )
                    and all(
                        isinstance((actual := selected(row, k)), str)
                        and needle in unicodedata.normalize("NFKC", actual).casefold()
                        for k, needle in text_filters.items()
                    )
                    and typed.matches(row)
                    and (not spatial or spatial.includes(row))
                )

            def projected(row):
                return (
                    {
                        k: selected(row, k)
                        for k in fields
                        if selected(row, k) is not MISSING
                    }
                    if fields
                    else row
                )

            spatial_page = []
            if ordered:

                def matching_keys():
                    nonlocal total
                    for index, row in enumerate(value["rows"]):
                        if index % 256 == 0:
                            check_budget()
                        if matches(row):
                            total += 1
                            yield (
                                (spatial.distance(row), index)
                                if spatial
                                else typed.key(row, index)
                            )

                ranked = heapq.nsmallest(offset + limit, matching_keys())[offset:]
                indices = {
                    (key[1] if spatial else key.index): position
                    for position, key in enumerate(ranked)
                }
                if spatial:
                    spatial_page = [
                        {"sourceOrdinal": key[1], "distanceM": key[0]} for key in ranked
                    ]
                page = {}
                for index, row in enumerate(value["rows"]):
                    if index % 256 == 0:
                        check_budget()
                    if index in indices:
                        page[indices[index]] = projected(row)
                    if len(page) == len(indices):
                        break
                items = [page[i] for i in range(len(page))]
            else:
                for index, row in enumerate(value["rows"]):
                    if index % 256 == 0:
                        check_budget()
                    if unfiltered and index >= offset + limit:
                        break
                    if unfiltered or matches(row):
                        position = index if unfiltered else total
                        if offset <= position < offset + limit:
                            items.append(projected(row))
                        if not unfiltered:
                            total += 1
            check_budget()
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
            result = {
                **self.envelope(resource, value, check, stale),
                "data": {"items": items},
                "meta": {
                    "total": total,
                    "offset": offset,
                    "nextOffset": (
                        offset + limit
                        if offset + limit < (min(total, 1000) if ordered else total)
                        else None
                    ),
                    "orderedWindow": (
                        {"limit": 1000, "truncated": total > 1000} if ordered else None
                    ),
                    "version": check.get("hash"),
                    "pagination": "Pass version on every subsequent page; changed content returns 409.",
                    "structuredQueryable": not document,
                    "typedPredicates": {
                        "excludedRows": typed.excluded,
                        "excludedRowsScope": "After equality/text filters; first invalid typed predicate per rejected row.",
                        "interval": "[start,end)",
                        "orderTieBreaker": "source_ordinal",
                        "nullOrder": "last",
                    },
                },
            }
            if spatial:
                result["meta"]["nearby"] = {
                    "matches": spatial_page,
                    "distanceMethod": "great_circle_straight_line_metres",
                    "boundary": "distance <= radiusM",
                    "coverage": spatial.binding["coverage"],
                    "profileId": spatial.binding["profileId"],
                    "profileFingerprint": spatial.binding["profileFingerprint"],
                    "countsAre": "source_rows_not_unique_facilities",
                    "uniqueFacilityCount": None,
                    "allSourceRowsLocatable": not (
                        spatial.binding["coverage"]["missingCoordinates"]
                        or spatial.binding["coverage"]["invalidCoordinates"]
                    ),
                    "matchingTotalScope": "Matching source rows with valid coordinates; excluded rows may fall inside the radius.",
                }
            if presentation:
                result["presentation"] = present(items, fields)
            if (
                len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode())
                > MAX_RESPONSE_BYTES
            ):
                raise DomainError(
                    "RESPONSE_TOO_LARGE", "Choose fewer columns or a smaller page", 422
                )
            return result

        def work():
            try:
                return build_result()
            finally:
                if isinstance(value["rows"], FileRows):
                    value["rows"].close()

        return await asyncio.to_thread(work)

    async def audit(self, batch=BATCH_SIZE, max_seconds=RUN_SECONDS):
        from .refresh_queue import RefreshQueue

        queue = await asyncio.to_thread(RefreshQueue, self.catalogue)
        return await queue.run(self, batch, max_seconds)
