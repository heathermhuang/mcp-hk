"""Read-only Plate.hk adapter. No bulk mirror, marketplace or private contacts."""

import asyncio
import hashlib
import json
import math
from datetime import date
from urllib.parse import urljoin, urlsplit

from .contracts import DomainError
from .http import request_json

DATASETS = {"all", "pvrm", "tvrm_physical", "tvrm_eauction", "tvrm_legacy"}
ROW_FIELDS = {
    "dataset_key",
    "auction_key",
    "auction_date",
    "auction_date_label",
    "date_precision",
    "year_range",
    "is_lny",
    "single_line",
    "double_line",
    "amount_hkd",
    "pdf_url",
    "source_url",
    "source_format",
    "source_type",
    "source_sheet",
    "result_status",
    "result_text",
    "comparison_reason",
}
WARNING = {
    "code": "HISTORICAL_AUCTION_DATA",
    "message": (
        "Plate.hk is an independent index. Historical auction amounts and comparisons "
        "are not current valuations, asking prices, ownership or availability. "
        "Verify with each record's original source. Legacy dates may be year ranges; "
        "E-Auction issue dates identify the opening date."
    ),
    "affectedSourceId": "platehk",
}


def public_row(row):
    """Project only auction fields; never relay arbitrary upstream/private fields."""
    if (
        not isinstance(row, dict)
        or row.get("dataset_key") not in DATASETS - {"all"}
        or not isinstance(row.get("auction_key"), str)
        or not isinstance(row.get("single_line"), str)
        or "amount_hkd" not in row
    ):
        raise ValueError("Invalid auction row")
    amount = row["amount_hkd"]
    if amount is not None and (
        type(amount) not in (int, float) or not math.isfinite(amount) or amount < 0
    ):
        raise ValueError("Invalid historical amount")
    result = {key: value for key, value in row.items() if key in ROW_FIELDS}
    for field in ("pdf_url", "source_url"):
        if row.get(field):
            link = urljoin("https://plate.hk/", row[field])
            u = urlsplit(link)
            if u.scheme != "https" or u.hostname not in {
                "td.gov.hk",
                "www.td.gov.hk",
                "plate.hk",
            }:
                raise ValueError("Unexpected auction source link")
            result[field] = link
    detail = row.get("detail_path")
    if (
        isinstance(detail, str)
        and detail.startswith("/")
        and not detail.startswith("//")
    ):
        url = urljoin("https://plate.hk", detail)
        if urlsplit(url).hostname == "plate.hk":
            result["detailUrl"] = url
    return result


def page_number(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("Invalid count or page")
    return value


def parse_search(payload):
    total = page_number(payload["total"])
    page = page_number(payload["page"], 1)
    size = page_number(payload["page_size"], 1)
    rows = [public_row(row) for row in payload["rows"]]
    if payload["dataset"] not in DATASETS or len(rows) > size or len(rows) > total:
        raise ValueError("Invalid search page")
    return {
        "query": payload["q"],
        "dataset": payload["dataset"],
        "mode": payload["mode"] or "contains",
        "sort": payload["sort"],
        "page": page,
        "pageSize": size,
        "items": rows,
        "total": total,
        "nextPage": page + 1 if page * size < total else None,
        "paginationConsistency": "live_source_pages_not_snapshot_pinned",
    }


def parse_comparables(payload):
    page = page_number(payload["page"], 1)
    size = page_number(payload["page_size"], 1)
    rows = [public_row(row) for row in payload["rows"]]
    if len(rows) > size:
        raise ValueError("Invalid comparison page")
    data = {
        "query": payload["query"],
        "method": payload["method"],
        "target": public_row(payload["target"]) if payload.get("target") else None,
        "totalHistory": page_number(payload["total_history"]),
        "page": page,
        "pageSize": size,
        "items": rows,
        "paginationConsistency": "live_source_pages_not_snapshot_pinned",
    }
    if "sample_size" in payload:
        sample = page_number(payload["sample_size"])
        stats = payload.get("statistics")
        if stats is not None:
            values = [stats[k] for k in ("p25", "median", "p75")]
            if (
                sample < 5
                or any(
                    type(v) not in (int, float) or not math.isfinite(v) or v < 0
                    for v in values
                )
                or values != sorted(values)
            ):
                raise ValueError("Unqualified comparison statistics")
        data.update(
            cohort=payload.get("cohort"),
            sampleSize=sample,
            window=payload.get("window"),
            dateFrom=payload.get("date_from"),
            dateTo=payload.get("date_to"),
            statistics=(
                {k: stats[k] for k in ("p25", "median", "p75")} if stats else None
            ),
            nextPage=page + 1 if page * size < sample else None,
        )
    # Other structural examples do not publish a full-cohort count.
    else:
        data["nextPage"] = None
    return data


def parse_datasets(payload):
    generated = payload["generated_at"]
    date.fromisoformat(generated)
    definitions = payload["datasets"]
    if not DATASETS <= definitions.keys():
        raise ValueError("Incomplete dataset coverage")
    return {
        "provider": "Plate.hk",
        "providerType": "independent",
        "generatedAt": generated,
        "items": [
            {
                "id": key,
                "recordCount": page_number(definitions[key]["total_rows"]),
                "issueCount": page_number(definitions[key]["issue_count"]),
                "latestIssue": definitions[key]["latest_issue"],
                "includedInAll": key != "all",
                "sourceUrl": f"https://plate.hk/api/v1/{key}/issues.manifest.json",
            }
            for key in sorted(DATASETS)
        ],
        "notes": [
            "The all dataset is the aggregate, not an additional disjoint collection.",
            "Coverage reflects Plate.hk's published index, not every possible auction or unsold mark.",
            "Code is MIT; source data retains its original terms and attribution.",
        ],
    }


class PlateHK:
    def __init__(self, service):
        self.service = service
        self.slots = asyncio.Semaphore(3)

    async def query(self, kind, params=None):
        path, parser = {
            "search": ("/api/search", parse_search),
            "comparables": ("/api/comparables", parse_comparables),
            "datasets": ("/api/v1/index.json", parse_datasets),
        }[kind]
        key = (
            "platehk:"
            + hashlib.sha256(
                json.dumps([kind, params], sort_keys=True).encode()
            ).hexdigest()
        )
        cached = self.service.store.cache_get(key, ttl=300)
        if cached:
            data, retrieved = cached
        else:
            try:
                # Recheck after waiting; successful identical reads share a 5-minute cache.
                async with self.slots:
                    cached = self.service.store.cache_get(key, ttl=300)
                    if cached:
                        data, retrieved = cached
                    else:
                        self.service.store.consume_budget("platehk", 5000)
                        data = parser(
                            await request_json("https://plate.hk" + path, params)
                        )
                        retrieved = self.service.store.cache_put(
                            key, data, source="platehk"
                        )
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                self.service.store.check("platehk", "SOURCE_SCHEMA_CHANGED")
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED",
                    "Plate.hk returned an unexpected data schema",
                ) from None
            except DomainError as exc:
                if exc.code != "INVALID_QUERY":
                    self.service.store.check("platehk", exc.code)
                raise
        envelope = self.service.envelope(
            data,
            "platehk",
            retrieved=retrieved,
            total=data.get("total", data.get("sampleSize")),
            truncated=data.get("nextPage") is not None,
        )
        envelope["provenance"][0].update(
            provider="Plate.hk",
            providerType="independent",
            accessMode="live_api",
            upstreamUrl="https://plate.hk" + path,
            cacheTtlSeconds=300,
        )
        envelope["warnings"].append(WARNING.copy())
        return envelope

    async def search(self, query):
        if not query.q.strip():
            raise DomainError("INVALID_QUERY", "Provide a plate query", 400)
        params = {
            "q": query.q,
            "dataset": query.dataset,
            "sort": query.sort,
            "page": query.page,
            "page_size": query.pageSize,
        }
        if query.mode != "contains":
            params["mode"] = query.mode
        return await self.query("search", params)

    async def comparables(self, query):
        if not query.q.strip():
            raise DomainError("INVALID_QUERY", "Provide a plate query", 400)
        return await self.query(
            "comparables",
            {
                "q": query.q,
                "page": query.page,
                "page_size": query.pageSize,
            },
        )
