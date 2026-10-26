"""One operator inspection of a known 302; never follows or clears a hold."""

import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit, parse_qs, urlencode, urlunsplit

import httpx

from .curated.racing.policy import RacingRejected, canonical
from .curated.racing.prototype_store import ResultsStore, MAX_PAGE
from .curated.racing.public_results import result_url, PATHS

LOCATION_PATHS = PATHS | {
    f"/racing/information/{language}/Racing/LocalResults.aspx"
    for language in ("English", "Chinese")
}


def location_metadata(original, raw):
    if not raw:
        return {"location": None, "locationSha256": None}
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if len(raw) > 2000:
        return {"location": None, "locationSha256": digest}
    try:
        p = urlsplit(urljoin(original, raw))
        query = parse_qs(p.query, keep_blank_values=True)
        allowed = {
            "racedate": r"[0-9]{4}/[0-9]{2}/[0-9]{2}|[0-9]{8}",
            "racecourse": r"ST|HV",
            "raceno": r"[1-9]|1[0-9]|20",
            "lang": r"EN|CH|ZH|en-us|zh-hk",
        }
        safe = (
            p.scheme == "https"
            and p.netloc == "racing.hkjc.com"
            and not p.fragment
            and p.path in LOCATION_PATHS
            and len({k.lower() for k in query}) == len(query)
        )
        safe = safe and all(
            k.lower() in allowed
            and len(v) == 1
            and re.fullmatch(allowed[k.lower()], v[0])
            for k, v in query.items()
        )
        location = (
            urlunsplit(
                (
                    p.scheme,
                    p.netloc,
                    p.path,
                    urlencode({k: v[0] for k, v in query.items()}),
                    "",
                )
            )
            if safe
            else None
        )
    except ValueError:
        location = None
    return {"location": location, "locationSha256": digest}


def location_shape(original, raw):
    """Keep public routing structure, never credentials or unknown values."""
    if not raw or len(raw) > 2000:
        return {
            "present": bool(raw),
            "bounded": bool(raw),
            "path": None,
            "queryKeys": [],
            "queryValuesRetained": False,
        }
    try:
        p = urlsplit(urljoin(original, raw or ""))
        same = p.hostname == "racing.hkjc.com"
        parts = []
        known = {
            "",
            "racing",
            "information",
            "english",
            "chinese",
            "en-us",
            "zh-hk",
            "local",
            "info",
            "error",
            "errors",
            "racing-info",
            "content",
            "home",
            "default",
            "index",
            "localresults",
        }
        words = {
            "local",
            "race",
            "races",
            "racing",
            "result",
            "results",
            "info",
            "information",
            "error",
            "errors",
            "not",
            "no",
            "available",
            "unavailable",
            "default",
            "index",
            "home",
            "login",
            "redirect",
            "page",
            "captcha",
            "challenge",
            "access",
            "denied",
            "exception",
            "un",
            "card",
            "list",
            "detail",
            "details",
            "history",
            "new",
            "old",
            "data",
            "programme",
            "program",
            "exists",
            "exist",
            "found",
            "none",
            "missing",
            "empty",
            "bad",
            "request",
            "invalid",
            "avail",
        }
        if same and p.username is None and p.password is None:
            for part in p.path.split("/"):
                filename = re.fullmatch(
                    r"([A-Za-z_-]{1,50})\.(?:aspx|asp|html?)", part, re.I
                )
                tokens = (
                    re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])", filename[1])
                    if filename
                    else []
                )
                static = bool(tokens) and all(t.lower() in words for t in tokens)
                parts.append(part if part.lower() in known or static else "[redacted]")
        names = {
            "racedate",
            "racecourse",
            "raceno",
            "lang",
            "locale",
            "src",
            "redirect",
            "redirected",
            "url",
            "returnurl",
            "err",
            "error",
            "type",
            "kind",
            "id",
            "token",
            "session",
            "code",
            "msg",
            "message",
            "action",
            "season",
            "year",
            "month",
            "date",
        }
        keys = sorted(
            {
                key.lower() if key.lower() in names else "[redacted]"
                for key in parse_qs(p.query, keep_blank_values=True)
            }
        )[:20]
        return {
            "present": True,
            "scheme": p.scheme if p.scheme in {"http", "https"} else "unqualified",
            "sameProviderHost": same,
            "credentialsInAuthority": p.username is not None or p.password is not None,
            "path": "/".join(parts) if parts else None,
            "queryKeys": keys,
            "queryValuesRetained": False,
        }
    except ValueError:
        return {
            "scheme": "unqualified",
            "sameProviderHost": False,
            "path": None,
            "queryKeys": [],
            "queryValuesRetained": False,
        }


def inspect_redirect(store, original_attempt, client=None, shape=False):
    if (
        type(original_attempt) is not int
        or original_attempt < 1
        or os.environ.get("MCP_HK_EDGE_MODE") != "true"
    ):
        raise RacingRejected("RACING_INSPECTION_DURABLE_ADMISSION_REQUIRED")
    with store.collector_lock():
        with store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT a.*,r.remote_id FROM racing_attempts a JOIN racing_remote_requests r ON r.local_id=a.id WHERE a.id=?",
                (original_attempt,),
            ).fetchone()
            if (
                not old
                or old["state"] != "held"
                or old["error"] != "DEVELOPMENT_HTTP_302"
            ):
                raise RacingRejected("RACING_INSPECTION_NOT_ELIGIBLE")
            url = result_url(old["url"])
            kind = "routing_shape" if shape else "location"
            if shape:
                previous = [
                    json.loads(r[0])
                    for r in db.execute(
                        "SELECT payload FROM racing_redirect_inspections WHERE original_attempt=?",
                        (original_attempt,),
                    )
                ]
                if not any(
                    r.get("inspectionKind", "location") == "location"
                    and r.get("state") == "received"
                    and r.get("responseStatus") == 302
                    and r.get("settlementConfirmed") is True
                    and r.get("location") is None
                    and r.get("locationSha256")
                    and not r.get("locationShape")
                    and not r.get("truncated", False)
                    for r in previous
                ):
                    raise RacingRejected("RACING_INSPECTION_PRIOR_PROOF_REQUIRED")
            if db.execute(
                "SELECT 1 FROM racing_redirect_inspections WHERE original_attempt=? AND COALESCE(json_extract(payload,'$.inspectionKind'),'location')=? AND json_extract(payload,'$.state')<>'admission_denied' LIMIT 1",
                (original_attempt, kind),
            ).fetchone():
                raise RacingRejected("RACING_INSPECTION_ALREADY_RECORDED")
            remote = uuid.uuid4().hex
            attempt = db.execute(
                "INSERT INTO racing_attempts(at,url,state,error) VALUES(?,?,'reserved','REDIRECT_INSPECTION')",
                (time.time(), url),
            ).lastrowid
            db.execute(
                "INSERT INTO racing_remote_requests VALUES(?,?)", (attempt, remote)
            )
            result = {
                "state": "reserved",
                "inspectionKind": kind,
                "originalAttempt": original_attempt,
                "inspectionAttempt": attempt,
                "sourceUrl": url,
                "originalHoldRetained": True,
                "providerRequests": 0,
                "observedAt": datetime.now(timezone.utc).isoformat(),
                "rawHtmlRetained": False,
            }
            db.execute(
                "INSERT INTO racing_redirect_inspections VALUES(?,?,?)",
                (attempt, original_attempt, canonical(result).decode()),
            )

        def persist():
            with store.connect() as db:
                original = db.execute(
                    "SELECT state,error FROM racing_attempts WHERE id=?",
                    (original_attempt,),
                ).fetchone()
                assert (
                    original["state"] == old["state"]
                    and original["error"] == old["error"]
                )
                db.execute(
                    "UPDATE racing_redirect_inspections SET payload=? WHERE inspection_attempt=?",
                    (canonical(result).decode(), attempt),
                )
            return result

        try:
            admission = store.admission(
                {
                    "action": "inspect_redirect_shape" if shape else "inspect_redirect",
                    "referenceId": old["remote_id"],
                    "id": remote,
                }
            )
        except (OSError, ValueError):
            ResultsStore.settled(
                store,
                attempt,
                "unknown",
                MAX_PAGE,
                "RACING_INSPECTION_ADMISSION_UNKNOWN",
            )
            result.update(
                state="admission_unknown", code="RACING_INSPECTION_ADMISSION_UNKNOWN"
            )
            return persist()
        if admission.get("allowed") is not True:
            ResultsStore.settled(
                store, attempt, "admission_denied", 0, "RACING_INSPECTION_NOT_ADMITTED"
            )
            result.update(
                state="admission_denied",
                code=admission.get("code", "RACING_INSPECTION_NOT_ADMITTED"),
            )
            return persist()
        body = bytearray()
        started = time.monotonic()
        result.update(state="dispatched", providerRequests=1)
        persist()
        try:
            with (
                client
                or httpx.Client(
                    timeout=15, trust_env=False, follow_redirects=False
                ) as transport
            ):
                with transport.stream(
                    "GET",
                    url,
                    headers={
                        "User-Agent": "mcp.hk-racing/1.0",
                        "Accept-Encoding": "identity",
                    },
                    follow_redirects=False,
                ) as response:
                    truncated = False
                    result.update(
                        responseStatus=response.status_code,
                        **location_metadata(url, response.headers.get("location")),
                        locationShape=location_shape(
                            url, response.headers.get("location")
                        ),
                    )
                    for chunk in response.iter_bytes(chunk_size=8192):
                        if time.monotonic() - started > 20:
                            raise httpx.ReadTimeout("Inspection wall-time bound")
                        body.extend(chunk[: MAX_PAGE - len(body)])
                        if len(body) >= MAX_PAGE:
                            truncated = True
                            break
                    state = (
                        "held"
                        if response.status_code in {401, 403, 429, 503}
                        else "success"
                    )
                    code = (
                        "SOURCE_HTTP_" + str(response.status_code)
                        if state == "held"
                        else "REDIRECT_INSPECTION_COMPLETE"
                    )
                    result.update(
                        state="received",
                        bodySha256=hashlib.sha256(body).hexdigest(),
                        bytes=len(body),
                        truncated=truncated,
                        settlementConfirmed=False,
                    )
                    store.settled(attempt, state, len(body), code)
                    result["settlementConfirmed"] = state == "success"
                    result["accountingState"] = "held" if state == "held" else "settled"
        except (httpx.HTTPError, OSError, ValueError):
            ResultsStore.settled(
                store, attempt, "unknown", MAX_PAGE, "RACING_INSPECTION_UNCONFIRMED"
            )
            result.update(
                state="unknown",
                code="RACING_INSPECTION_UNCONFIRMED",
                settlementConfirmed=False,
            )
        return persist()
