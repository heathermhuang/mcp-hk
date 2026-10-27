"""One exact, separately approved legacy hold inspection; never normal admission.

No CLI or timer invokes this module. Approval must be an operator-reviewed receipt
for this exact action. The existing hold is required and is never cleared, even
when the inspected response succeeds. Failed/unknown requests remain charged.
"""

import hashlib
import re
import time
from datetime import datetime, timezone
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from . import store

SERIAL = "DA20030606000076"
PATH = "/di/NSForm3A.aspx?fn=" + SERIAL
ORIGIN = "https://di.hkex.com.hk"
ORIGINAL_LEDGER = 142
ORIGINAL_SHA = "feb33875e697163f087051e45a534265d68b972109e95735c01d460f9e73943f"
MAX_BODY = 400 * 1024


def redirect_metadata(location):
    """Unknown paths/values never enter a receipt; hashes permit later comparison."""
    if location is None:
        return {"present": False}
    if not isinstance(location, str) or len(location) > 2048:
        return {"present": True, "state": "unqualified_length"}
    value = urlsplit(urljoin(ORIGIN + PATH, location))
    query = parse_qs(value.query, keep_blank_values=True)
    allowed_paths = {"/di/NSForm3A.aspx", "/di/NSForm3B.aspx", "/di/NSAllFormList.aspx"}
    allowed_keys = {"fn", "sid", "sc", "lang"}
    safe = (
        value.scheme == "https"
        and value.netloc == "di.hkex.com.hk"
        and not value.fragment
        and value.path in allowed_paths
        and not set(query) - allowed_keys
        and query.get("fn") == [SERIAL]
        and all(len(v) == 1 for v in query.values())
        and all(
            re.fullmatch(
                {
                    "fn": re.escape(SERIAL),
                    "sid": r"[0-9]{1,12}",
                    "sc": r"[0-9]{5}",
                    "lang": r"EN|ZH",
                }[k],
                v[0],
            )
            for k, v in query.items()
        )
    )
    return {
        "present": True,
        "sha256": hashlib.sha256(location.encode()).hexdigest(),
        "https": value.scheme == "https",
        "sameProviderAuthority": value.netloc == "di.hkex.com.hk",
        "credentialsInAuthority": bool(value.username or value.password),
        "pathSha256": hashlib.sha256(value.path.encode()).hexdigest(),
        "qualifiedPath": value.path if value.path in allowed_paths else None,
        "knownQueryKeys": sorted(set(query) & allowed_keys),
        "unknownQueryKeyCount": len(set(query) - allowed_keys),
        "sanitizedLocation": location if safe else None,
        "redirectFollowed": False,
    }


def reserve(c, run, approval):
    """Share the daily request/byte ceilings and writer lock with ordinary jobs."""
    if (
        approval.get("action") != "inspect_exact_legacy_response_once"
        or approval.get("serial") != SERIAL
        or approval.get("originalLedgerId") != ORIGINAL_LEDGER
        or approval.get("retainHold") is not True
        or approval.get("followRedirects") is not False
        or not re.fullmatch(r"[a-f0-9]{64}", approval.get("evidenceSha256", ""))
        or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,200}", approval.get("evidenceRef", ""))
    ):
        raise ValueError("EXPLICIT_EXACT_HOLD_EXCEPTION_REQUIRED")
    marker = "LEGACY_INSPECTION:" + approval["evidenceSha256"]
    with c.transaction():
        control = c.execute(
            "SELECT * FROM hkex_daily.control WHERE singleton FOR UPDATE"
        ).fetchone()
        if (
            control["hold_code"] != "SOURCE_ACCESS_HOLD"
            or control["hold_until"] is not None
        ):
            raise ValueError("EXACT_ORIGINAL_ACCESS_HOLD_REQUIRED")
        original = c.execute(
            "SELECT * FROM hkex_daily.requests WHERE id=%s", (ORIGINAL_LEDGER,)
        ).fetchone()
        if not original or any(
            original[k] != v
            for k, v in {
                "path": PATH,
                "status": 302,
                "sha256": ORIGINAL_SHA,
                "state": "received",
                "received_bytes": 159,
            }.items()
        ):
            raise ValueError("EXACT_ORIGINAL_RESPONSE_REQUIRED")
        if c.execute(
            "SELECT 1 FROM hkex_daily.runs WHERE code=%s", (marker,)
        ).fetchone():
            raise ValueError("HOLD_INSPECTION_ALREADY_RESERVED")
        if c.execute(
            "SELECT 1 FROM hkex_daily.requests WHERE state='unknown'"
        ).fetchone():
            raise ValueError("SOURCE_REQUEST_RECONCILIATION_REQUIRED")
        # Read the same aggregate allowance, including failures and reservations.
        budget = c.execute(
            "SELECT count(*) AS reads,coalesce(sum(coalesce(received_bytes,reserved_bytes)),0) AS bytes FROM hkex_daily.requests WHERE reserved_at>=date_trunc('day',now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
        ).fetchone()
        if (
            budget["reads"] >= store.READS_DAY
            or budget["bytes"] + MAX_BODY > store.BYTES_DAY
        ):
            raise ValueError("SOURCE_BUDGET_EXHAUSTED")
        if (
            control["last_read_at"]
            and (datetime.now(timezone.utc) - control["last_read_at"]).total_seconds()
            < store.MIN_INTERVAL
        ):
            raise ValueError("SOURCE_CADENCE_HOLD")
        c.execute(
            "INSERT INTO hkex_daily.runs(id,scheduled_for,provenance,state,code) VALUES(%s,now(),'manual','running',%s)",
            (run, marker),
        )
        key = c.execute(
            "INSERT INTO hkex_daily.requests(run_id,path,state,reserved_bytes) VALUES(%s,%s,'unknown',%s) RETURNING id",
            (run, PATH, MAX_BODY),
        ).fetchone()["id"]
        c.execute("UPDATE hkex_daily.control SET last_read_at=now() WHERE singleton")
    return key


def inspect(c, run, approval, *, transport=None):
    key = reserve(c, run, approval)
    body, started = bytearray(), time.monotonic()
    with httpx.Client(
        timeout=20, trust_env=False, follow_redirects=False, transport=transport
    ) as client:
        with client.stream(
            "GET",
            ORIGIN + PATH,
            headers={
                "User-Agent": "mcp.hk exact hold inspection (+https://mcp.hk)",
                "Accept": "text/html",
                "Accept-Encoding": "identity",
            },
        ) as response:
            for block in response.iter_bytes(32768):
                if time.monotonic() - started > 20 or len(body) + len(block) > MAX_BODY:
                    raise ValueError("SOURCE_INSPECTION_BOUND")
                body.extend(block)
            metadata = redirect_metadata(response.headers.get("location"))
            status = response.status_code
    digest = hashlib.sha256(body).hexdigest()
    with c.transaction():
        c.execute(
            "UPDATE hkex_daily.requests SET state='received',status=%s,received_bytes=%s,sha256=%s WHERE id=%s AND state='unknown'",
            (status, len(body), digest, key),
        )
        c.execute(
            "UPDATE hkex_daily.runs SET state='technical_complete',finished_at=now(),request_count=1,received_bytes=%s WHERE id=%s",
            (len(body), run),
        )
        hold = c.execute(
            "SELECT hold_code,hold_until FROM hkex_daily.control WHERE singleton"
        ).fetchone()
        if hold["hold_code"] != "SOURCE_ACCESS_HOLD" or hold["hold_until"] is not None:
            raise ValueError("SOURCE_HOLD_CHANGED_INSPECTION_UNCONFIRMED")
    return {
        "ledgerId": key,
        "serial": SERIAL,
        "status": status,
        "bytes": len(body),
        "sha256": digest,
        "redirect": metadata,
        "holdRetained": True,
        "rawHtmlRetained": False,
        "retried": False,
        "approvalEvidenceSha256": approval["evidenceSha256"],
    }
