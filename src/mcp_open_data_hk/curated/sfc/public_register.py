"""Corporate licence-page adapter, informed by David Webb's released SFC.vb.

Webb's CC-BY notice ships with this package. This is a new implementation of the
public register protocol, not execution of its scripts or a copy of SFC HTML.
Corporate history does not by itself supply a current licensing-status judgment.
"""

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from importlib.resources import files
import asyncio
import json
import time
import re

import httpx

from .contracts import (
    Activity,
    Corporation,
    SourceDate,
    Rejected,
    ce_reference,
    digest,
    encoded,
    source_day_value,
)

ROUTE = "https://apps.sfc.hk/publicregWeb/corp/{ce}/licences"
MAX_BODY = 262144


def source_day(raw):
    if raw in (None, ""):
        return SourceDate(raw=raw)
    return SourceDate(raw=raw, value=source_day_value(raw), precision="day")


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.header = []
        self.scripts = []
        self.in_script = False
        self.spans = []
        self.span_depth = 0
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and (
            self.depth or "licensed-person" in attrs.get("class", "").split()
        ):
            self.depth += 1
        if tag == "span" and self.depth:
            self.span_depth += 1
            self.spans.append("")
        if tag == "script":
            self.in_script = True
            self.scripts.append("")

    def handle_endtag(self, tag):
        if tag == "div" and self.depth:
            self.depth -= 1
        if tag == "span" and self.span_depth:
            self.span_depth -= 1
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.depth:
            self.header.append(data)
            if self.span_depth:
                self.spans[-1] += data
        if self.in_script:
            self.scripts[-1] += data


def parse_page(payload, expected_ce, observed_at):
    """Read the exact source CE, corporate header and JSON licence intervals.

    No eval, JS execution, RI fallback, person expansion or inference from end dates.
    Dates retain source strings. The 1-Apr-2003 SFO boundary is not erased as in the
    legacy collector; it is explicitly a source regime date, not a pre-SFO history.
    """
    ce = ce_reference(expected_ce)
    if not isinstance(payload, bytes) or len(payload) > MAX_BODY:
        raise Rejected("SFC_PAYLOAD_LIMIT")

    def unique(pairs):
        row = {}
        for key, value in pairs:
            if key in row:
                raise ValueError("Duplicate JSON field")
            row[key] = value
        return row

    try:
        page = Page(payload.decode("utf-8-sig"))
        header = " ".join(" ".join(page.header).split())
        parts = [part.strip() for part in page.spans if part.strip()]
        if (
            not header.startswith("Corporation Corporation:")
            or len(parts) not in {2, 3}
            or parts[-1] != "(" + ce + ")"
        ):
            raise ValueError("Corporate identity differs")
        packets = []
        decoder = json.JSONDecoder(object_pairs_hook=unique)
        for script in page.scripts:
            declarations = list(
                re.finditer(r"(?m)^\s*(?:var|let|const)\s+licRecordData\s*=\s*", script)
            )
            if len(declarations) != len(
                list(re.finditer(r"\blicRecordData\s*=", script))
            ):
                raise ValueError("Ambiguous licence assignment")
            for match in re.finditer(
                r"(?m)^\s*(?:var|let|const)\s+licRecordData\s*=\s*", script
            ):
                data, end = decoder.raw_decode(script[match.end() :])
                if not script[match.end() + end :].lstrip().startswith(";"):
                    raise ValueError("Unexpected script expression")
                packets.append(data)
        if (
            len(packets) != 1
            or not isinstance(packets[0], list)
            or not 1 <= len(packets[0]) <= 50
        ):
            raise ValueError("Missing/empty/ambiguous licence packet")
        activities = []
        for row in packets[0]:
            if row["lcType"] != "C":
                raise ValueError("Unsupported institution/licence regime")
            activity = row["regulatedActivity"]
            code = activity["actType"]
            if type(code) is not int or not 1 <= code <= 13:
                raise ValueError("Unknown SFO activity")
            periods = row["effectivePeriodList"]
            if not isinstance(periods, list) or not 1 <= len(periods) <= 50:
                raise ValueError("Missing source intervals")
            for period in periods:
                if period.get("isAmloLcCatDeem") not in (None, False):
                    raise ValueError("AMLO interval in SFO view")
                activities.append(
                    Activity(
                        code=str(code),
                        label=activity["actDesc"],
                        statusCode="not_supplied",
                        statusLabel="No interval status supplied by this source page",
                        start=source_day(period["effectiveDate"]),
                        end=source_day(period["endDate"]),
                    )
                )
        return Corporation(
            ce=ce,
            entityType="corporation",
            regime="SFO",
            licenceType="licensed_corporation",
            nameEn=parts[0],
            nameZhHant=parts[1] if len(parts) == 3 else None,
            statusCode="not_supplied",
            statusLabel="Overall licensing status is not supplied by the licence-history page",
            activities=activities,
            observedAt=observed_at,
        )
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError) as exc:
        raise Rejected("SFC_SCHEMA_CHANGED") from exc


def transform_hash():
    folder = files(__package__)
    return digest(
        folder.joinpath("public_register.py").read_bytes()
        + folder.joinpath("contracts.py").read_bytes()
    )


async def read_page(url, transport):
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=False,
        trust_env=False,
        transport=transport,
        headers={
            "User-Agent": "mcp.hk-corporate-verification/1",
            "Accept-Encoding": "identity",
        },
    ) as client:
        async with client.stream("GET", url, params={"locale": "en"}) as response:
            if response.status_code != 200:
                return response.status_code, dict(response.headers), b""
            media = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
            if (
                media != "text/html"
                or response.headers.get("Content-Encoding", "identity").lower()
                != "identity"
            ):
                raise Rejected("SFC_SOURCE_CONTENT_TYPE")
            body = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    raise Rejected("SFC_PAYLOAD_LIMIT")
            return response.status_code, dict(response.headers), bytes(body)


class Collector:
    """Bounded operator collector, never called by public read requests.

    Operator configuration supplies exact cohort, source/retention scope and limits;
    this technical configuration is not a subscription or paid-feed integration.
    Each network read has an overall 20-second deadline including its full body.
    """

    def __init__(self, state, policy, transport=None):
        self.state, self.policy, self.transport = state, policy, transport

    def collect(self, scheduled_for, cohort, provenance="manual", source_release=None):
        if self.policy.route != ROUTE:
            raise Rejected("SFC_ROUTE_CHANGED")
        self.policy.require("automation", "retention", "backup")
        payloads, lineage = {}, {}
        deadline = time.monotonic() + 600
        with self.state.session():
            run, new = self.state.start(
                scheduled_for, cohort, self.policy.sha256, provenance, source_release
            )
            if not new:
                return {"runId": run, "state": "already_processed", "networkReads": 0}
            try:
                for raw_ce in cohort:
                    ce = ce_reference(raw_ce)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise Rejected("SFC_RUN_TIMEOUT")
                    attempt = self.state.reserve(run, ce, "detail", MAX_BODY)
                    try:
                        url = ROUTE.replace("{ce}", ce)

                        async def fetch():
                            return await asyncio.wait_for(
                                read_page(url, self.transport),
                                timeout=min(20, remaining),
                            )

                        try:
                            code, headers, body = asyncio.run(fetch())
                        except asyncio.TimeoutError as exc:
                            raise Rejected("SFC_SOURCE_TIMEOUT") from exc
                        if code in (403, 429):
                            until = datetime.max.replace(tzinfo=timezone.utc)
                            if code == 429:
                                value = headers.get("retry-after", "")
                                try:
                                    until = (
                                        (
                                            datetime.now(timezone.utc)
                                            + timedelta(seconds=max(1, int(value)))
                                        )
                                        if value.isdecimal()
                                        else parsedate_to_datetime(value)
                                    )
                                    if until.tzinfo is None or until <= datetime.now(
                                        timezone.utc
                                    ):
                                        raise ValueError()
                                except (ValueError, TypeError, OverflowError):
                                    until = datetime.now(timezone.utc) + timedelta(
                                        hours=1
                                    )
                            self.state.settle(
                                attempt,
                                "rejected",
                                hold_until=until,
                                hold_reason=(
                                    "forbidden" if code == 403 else "rate_limited"
                                ),
                            )
                            attempt = None
                            raise Rejected("SFC_SOURCE_HOLD")
                        if code == 304:
                            self.state.settle(attempt, "not_modified")
                            attempt = None
                            raise Rejected("SFC_UNCHANGED_NO_NEW_FACT")
                        if code != 200:
                            raise Rejected("SFC_SOURCE_RESPONSE")
                        observed = datetime.now(timezone.utc)
                        fact = parse_page(body, ce, observed)
                        self.state.settle(attempt, "ok")
                        payloads[ce] = (encoded(fact), attempt)
                        attempt = None
                        lineage[ce] = {
                            "sourceUrl": url,
                            "rawSha256": digest(body),
                            "sourceTransformSha256": transform_hash(),
                            "retrievedAt": observed.isoformat(),
                            "rawRetained": False,
                            "scope": "SFO_corporate_licence_intervals_only",
                        }
                    except Exception as exc:
                        uncertain = (
                            isinstance(exc, httpx.HTTPError)
                            or isinstance(exc, Rejected)
                            and str(exc) == "SFC_SOURCE_TIMEOUT"
                        )
                        if attempt is not None and not uncertain:
                            self.state.settle(attempt, "failed")
                        raise
                if time.monotonic() > deadline:
                    raise Rejected("SFC_RUN_TIMEOUT")
                version, sha = self.state.stage(run, payloads, source_metadata=lineage)
                return {
                    "runId": run,
                    "state": "validated",
                    "version": version,
                    "factsSha256": sha,
                    "cohortCount": len(payloads),
                }
            except (Rejected, httpx.HTTPError) as exc:
                self.state.finish(run, "partial")
                raise Rejected(
                    str(exc) if isinstance(exc, Rejected) else "SFC_SOURCE_UNAVAILABLE"
                ) from exc
            except Exception:
                self.state.finish(run, "failed")
                raise
