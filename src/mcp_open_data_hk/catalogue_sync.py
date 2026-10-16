"""Deterministic, resumable native catalogue harvesting and official-list reconciliation."""

import asyncio
import hashlib
import json
import re
import time
import uuid
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from defusedxml import ElementTree as ET

from .catalogue_store import CatalogueStore
from .contracts import DomainError
import httpx

CKAN = "https://data.gov.hk/en-data/api/3/action/"
OFFICIAL_LIST = "https://resource.data.one.gov.hk/opendata/open-data-list/open-data-dataset-list-en.json"
CSW = "https://portal.csdi.gov.hk/geoportal/csw?service=CSW&version=2.0.2&request=GetRecords&typeNames=csw:Record&outputSchema=http://www.opengis.net/cat/csw/2.0.2&resultType=results&elementSetName=full"
TERMS = "https://data.gov.hk/en/terms-and-conditions"
CSDI_TERMS = "https://portal.csdi.gov.hk/csdi-webpage/doc/TNC"


async def fetch(url, headers=None, maximum=8_000_000):
    """Only operator-owned official catalogue endpoints; no resource destinations."""
    p = urlsplit(url)
    if (
        p.scheme != "https"
        or p.hostname
        not in {"data.gov.hk", "resource.data.one.gov.hk", "portal.csdi.gov.hk"}
        or p.username
        or p.port
    ):
        raise ValueError("Untrusted catalogue endpoint")
    async with httpx.AsyncClient(
        timeout=30,
        trust_env=False,
        follow_redirects=False,
        headers={"User-Agent": "mcp.hk-catalogue/0.4 (+https://mcp.hk)"},
    ) as client:
        async with client.stream("GET", url, headers=headers) as response:
            if response.status_code == 304:
                return b"", dict(response.headers), url, 304
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > maximum:
                    raise DomainError(
                        "SOURCE_TOO_LARGE", "Catalogue exceeds byte budget", 422
                    )
            return bytes(body), dict(response.headers), url, response.status_code


def provider_type(name):
    # Conservative name-based classification; unresolved bodies stay unclassified.
    if name.endswith((" Department", " Bureau")) or name in {
        "Digital Policy Office",
        "Hong Kong Observatory",
        "Treasury",
        "Hongkong Post",
        "Companies Registry",
        "Land Registry",
        "Registration and Electoral Office",
        "Chief Executive's Office",
        "Chief Secretary for Administration's Office",
        "Financial Secretary's Office",
        "Invest Hong Kong",
        "District Councils",
    }:
        return "government"
    if any(x in name for x in ("Limited", "Company", "Corporation")):
        return "independent_or_public_corporation"
    return "unclassified"


def canonical_url(url):
    p = urlsplit(url.strip())
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, p.query, ""))


def normalise_dataset(d):
    provider = (d.get("organization") or {}).get("title") or "Unknown"
    return {
        "id": d["name"],
        "catalogue": "DATA.GOV.HK",
        "nativeId": d.get("id"),
        "title": d.get("title"),
        "description": d.get("notes"),
        "provider": provider,
        "providerType": provider_type(provider),
        "providerClassificationEvidence": "Conservative provider-name rules; unresolved statutory/public bodies are unclassified.",
        "sourceUrl": "https://data.gov.hk/en-data/dataset/" + d["name"],
        "dictionary": d.get("data_dictionary"),
        "updateCadence": d.get("update_frequency"),
        "metadataModified": d.get("metadata_modified"),
        "licence": {
            "id": d.get("license_id"),
            "title": d.get("license_title"),
            "termsUrl": TERMS,
        },
        "referencePeriod": None,
    }


def normalise_resources(d):
    groups = {}
    for r in d.get("resources", []):
        url = canonical_url(r.get("url") or "")
        if not url:
            url = "missing:" + str(r.get("id"))
        key = hashlib.sha256((d["name"] + "\n" + url).encode()).hexdigest()[:32]
        if key not in groups:
            groups[key] = {
                "id": key,
                "datasetId": d["name"],
                "url": url,
                "format": str(r.get("format") or "UNKNOWN").upper(),
                "catalogue": "DATA.GOV.HK",
                "aliases": [],
                "sourceUrl": "https://data.gov.hk/en-data/dataset/" + d["name"],
                "publicationDate": r.get("datePublished"),
                "sourceModified": r.get("dateModified"),
                "isApi": r.get("is_api") == "Y",
                "termsUrl": TERMS,
            }
        groups[key]["aliases"].append(
            {k: r.get(k) for k in ("id", "shared_id", "name", "inLanguage", "format")}
        )
    return sorted(groups.values(), key=lambda r: r["id"])


class Harvester:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.slots = asyncio.Semaphore(6)

    async def read(self, url, key, maximum=8_000_000):
        path = self.folder / (key + ".json")
        validators = self.folder / (key + ".headers")
        old = (
            json.loads(validators.read_text())
            if validators.exists() and path.exists()
            else {}
        )
        headers = {}
        if old.get("etag"):
            headers["If-None-Match"] = old["etag"]
        if old.get("last-modified"):
            headers["If-Modified-Since"] = old["last-modified"]
        async with self.slots:
            body, meta, _, status = await fetch(url, headers, maximum)
        if status == 304:
            return path.read_bytes()
        temp = path.with_suffix(".pending")
        temp.write_bytes(body)
        temp.replace(path)
        validators.write_text(
            json.dumps({k: meta[k] for k in ("etag", "last-modified") if k in meta})
        )
        return body

    async def datagov(self):
        official = json.loads(
            await self.read(OFFICIAL_LIST, "official-list", 32_000_000)
        )
        ids = json.loads(await self.read(CKAN + "package_list", "native-list"))[
            "result"
        ]
        if (
            not ids
            or len(ids) != len(set(ids))
            or any(not re.fullmatch("[a-zA-Z0-9_-]+", i) for i in ids)
        ):
            raise ValueError("Invalid native dataset enumeration")
        official_ids = {r["Dataset ID"] for r in official["Data"]}

        # The quarterly list may precede live removals/additions. Preserve differences.
        async def one(i):
            path = self.folder / (i + ".json")
            # A locally prepared complete harvest can seed initial sync; subsequent
            # runs revalidate each dataset conditionally.
            if path.exists() and not path.with_suffix(".headers").exists():
                raw = json.loads(path.read_text())
                path.with_suffix(".headers").write_text("{}")
                d = raw.get("result", raw)
            else:
                raw = json.loads(await self.read(CKAN + "package_show?id=" + i, i))
                if not raw.get("success"):
                    raise ValueError("Dataset lookup failed: " + i)
                d = raw["result"]
            if d["name"] != i:
                raise ValueError("Dataset identity mismatch")
            return d

        raw = await asyncio.gather(*(one(i) for i in sorted(ids)))
        final_ids = json.loads((await fetch(CKAN + "package_list"))[0])["result"]
        if set(final_ids) != set(ids):
            raise ValueError("Catalogue changed during harvest; rerun from cache")
        datasets = [normalise_dataset(d) for d in raw]
        resources = [r for d in raw for r in normalise_resources(d)]
        receipt = {
            "nativeDatasets": len(ids),
            "nativeResourceAliases": sum(len(d.get("resources", [])) for d in raw),
            "officialDatasetCount": len(official_ids),
            "officialResourceDescriptions": len(official["Data"]),
            "officialAsOf": official.get("As of Date"),
            "officialListUrl": OFFICIAL_LIST,
            "missingFromNative": sorted(official_ids - set(ids)),
            "addedSinceOfficialList": sorted(set(ids) - official_ids),
            "resourceDescriptionReconciliation": "Quarterly descriptions have no URLs or resource IDs; do not equate them to canonical URL resources.",
        }
        return datasets, resources, receipt

    async def csdi(self):
        ns = {
            "csw": "http://www.opengis.net/cat/csw/2.0.2",
            "dc": "http://purl.org/dc/elements/1.1/",
            "dct": "http://purl.org/dc/terms/",
        }
        # CSW default relevance ordering is unstable across pages. A single bounded
        # response avoids duplicate/missing identities. Refuse a capped response.
        root = ET.fromstring(
            await self.read(
                CSW + "&startPosition=1&maxRecords=10000", "csw-complete", 32_000_000
            )
        )
        results = root.find("csw:SearchResults", ns)
        if results is None:
            raise ValueError("CSDI results missing")
        expected = int(results.attrib["numberOfRecordsMatched"])
        records = results.findall("csw:Record", ns)
        if (
            len(records) != expected
            or int(results.attrib["numberOfRecordsReturned"]) != expected
        ):
            raise ValueError("CSDI response capped; complete enumeration required")
        datasets = []
        resources = []

        async def one(record):
            def get(field):
                return record.findtext(field, default="", namespaces=ns)

            native = get("dc:identifier")
            if not re.fullmatch(r"[a-zA-Z0-9_.:-]{1,200}", native):
                raise ValueError("Invalid CSDI identity")
            did = "csdi:" + native
            refs = record.findall("dct:references", ns)
            metadata = next(
                (r.text for r in refs if r.attrib.get("scheme") == "alternate.xml"),
                None,
            )
            if not metadata or not metadata.startswith("https://portal.csdi.gov.hk/"):
                raise ValueError("CSDI lacks expected metadata URL")
            xml = ET.fromstring(await self.read(metadata, "iso-" + native))

            def local(e):
                return e.tag.rsplit("}", 1)[-1]

            def contents(e, name):
                return next(
                    (
                        "".join(n.itertext()).strip()
                        for n in e.iter()
                        if local(n) == name
                    ),
                    "",
                )

            online = [e for e in xml.iter() if local(e) == "CI_OnlineResource"]
            found = {}
            for e in online:
                url = contents(e, "URL")
                if not url.startswith(("http://", "https://")):
                    continue
                url = canonical_url(url)
                profile = contents(e, "applicationProfile").upper()
                fmt = profile.replace("FILE_API_", "")
                if "FEATURESERVER" in url.upper() or "MAPSERVER" in url.upper():
                    fmt = "ARCGIS"
                if "WFS" in profile:
                    fmt = "WFS"
                if "WMS" in profile:
                    fmt = "WMS"
                rid = hashlib.sha256((did + "\n" + url).encode()).hexdigest()[:32]
                found[rid] = {
                    "id": rid,
                    "datasetId": did,
                    "url": url,
                    "format": fmt or "UNKNOWN",
                    "catalogue": "CSDI",
                    "aliases": [{"name": contents(e, "name"), "format": profile}],
                    "sourceUrl": metadata.removesuffix("/xml") + "/html",
                    "publicationDate": get("dct:created"),
                    "sourceModified": get("dct:modified"),
                    "isApi": fmt in {"ARCGIS", "WFS", "WMS"},
                    "termsUrl": CSDI_TERMS,
                }
            return {
                "id": did,
                "nativeId": native,
                "catalogue": "CSDI",
                "title": get("dc:title"),
                "titleZhHant": get("dc:title_tc"),
                "description": get("dct:abstract"),
                "provider": get("dc:creator"),
                "providerType": provider_type(get("dc:creator")),
                "sourceUrl": metadata.removesuffix("/xml") + "/html",
                "metadataModified": get("dct:modified"),
                "updateCadence": contents(xml, "maintenanceAndUpdateFrequency") or None,
                "licence": {"termsUrl": CSDI_TERMS},
                "referencePeriod": None,
            }, list(found.values())

        values = await asyncio.gather(*(one(r) for r in records))
        for d, rs in values:
            datasets.append(d)
            resources.extend(rs)
        if len({d["id"] for d in datasets}) != expected:
            raise ValueError("CSDI duplicate identities")
        return datasets, resources, {"nativeDatasets": expected, "catalogueUrl": CSW}


async def sync(store, folder=None):
    catalogue = CatalogueStore(store)
    run = uuid.uuid4().hex
    with store.connect() as db:
        db.execute(
            "INSERT INTO catalogue_runs VALUES (?,?,NULL,?,NULL)",
            (run, time.time(), "running"),
        )
    try:
        h = Harvester(folder or Path(store.path).parent / "catalogue-audit")
        ds, rs, receipt = await h.datagov()
        cds, crs, csdi_receipt = await h.csdi()
        shared = set(r["url"] for r in rs) & set(r["url"] for r in crs)
        by_provider = Counter(d["providerType"] for d in ds + cds)
        receipt = {
            "DATA.GOV.HK": receipt,
            "CSDI": csdi_receipt,
            "crossCatalogueExactUrlOverlap": len(shared),
            "crossCatalogueIdentityPolicy": "Native dataset counts are separate; exact resource URLs indicate overlap, title similarity is not identity.",
            "datasetsByProviderType": dict(by_provider),
            "completedAt": time.time(),
        }
        generation = catalogue.publish(
            sorted(ds + cds, key=lambda d: d["id"]),
            sorted(rs + crs, key=lambda r: r["id"]),
            receipt,
        )
        with store.connect() as db:
            db.execute(
                "UPDATE catalogue_runs SET finished=?,status=?,receipt=? WHERE id=?",
                (
                    time.time(),
                    "success",
                    json.dumps({"generation": generation, **receipt}),
                    run,
                ),
            )
        return catalogue.coverage()
    except Exception as exc:
        with store.connect() as db:
            db.execute(
                "UPDATE catalogue_runs SET finished=?,status=?,receipt=? WHERE id=?",
                (
                    time.time(),
                    "failed",
                    json.dumps({"error": getattr(exc, "code", type(exc).__name__)}),
                    run,
                ),
            )
        raise
