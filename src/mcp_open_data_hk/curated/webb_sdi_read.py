"""Indexed reads of the actually released Webb directors' disclosure archive."""

import contextlib
import json
import re
import time
from datetime import date

from psycopg.rows import dict_row

from .build import connect
from .normalize import search_key
from .read import ReadError, prefix_end
from .security import safe_reader_role
from .webb_sdi_source import ARCHIVE_SHA

POSITIONS = {"1": "long", "2": "short", "3": "lending_pool"}

NOTICE = "Historical Webb Form 3A archive, not complete/current HKEX coverage, current holdings or an executed-trade feed. Source FLOAT/DOUBLE numeric representations are preserved; original exact decimal input is not recoverable. Filing/publication dates are not recorded."


def identifier(value, prefix):
    if isinstance(value, str) and value.startswith(prefix):
        value = value[len(prefix) :]
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,9}", value):
        raise ReadError("INVALID_ID", "Use an exact returned Webb archive identifier")
    return int(value)


class WebbSdiReader:
    def __init__(self, shared):
        self.shared = shared

    @contextlib.contextmanager
    def request(self):
        if not self.shared.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Shared read concurrency reached")
        try:
            with connect(
                self.shared.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as c:
                if not safe_reader_role(c):
                    raise ReadError("UNSAFE_READER", "Use a dedicated SELECT-only role")
                priv = c.execute(
                    "SELECT has_schema_privilege('webb_sdi','CREATE') AS creates,EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='webb_sdi' AND (has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR tableowner=current_user)) AS writes"
                ).fetchone()
                if any(priv.values()):
                    raise ReadError(
                        "UNSAFE_READER", "Archive reader has write privileges"
                    )
                yield c
        except Exception as exc:
            from psycopg.errors import LockNotAvailable, QueryCanceled

            if isinstance(exc, (LockNotAvailable, QueryCanceled)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Indexed archive read exceeded its bound"
                ) from exc
            raise
        finally:
            self.shared.slots.release()

    def status(self):
        try:
            with self.request() as c:
                row = c.execute(
                    "SELECT v.version,v.manifest FROM webb_sdi.accepted a JOIN webb_sdi.versions v USING(version) WHERE a.singleton AND v.state='published'"
                ).fetchone()
                if row:
                    return {
                        "source": "webb_sdi_archive",
                        "state": "available",
                        "version": row["version"],
                        "coverage": row["manifest"],
                        "notice": NOTICE,
                    }
        except Exception as exc:
            from psycopg.errors import (
                InvalidSchemaName,
                UndefinedTable,
                InsufficientPrivilege,
            )

            if not isinstance(
                exc, (InvalidSchemaName, UndefinedTable, InsufficientPrivilege)
            ):
                raise
        return {
            "source": "webb_sdi_archive",
            "state": "not_published",
            "version": None,
            "coverage": None,
            "notice": NOTICE,
        }

    def query(self, operation, params):
        params = {k: v for k, v in params.items() if v is not None}
        limit = params.get("limit", 20)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadError("INVALID_LIMIT", "Use limit 1–100")
        filters = {
            k: v for k, v in params.items() if k not in {"cursor", "version", "limit"}
        }
        cursor = (
            self.shared.unseal(params["cursor"], "webb_sdi:" + operation, filters)
            if params.get("cursor")
            else None
        )
        version = params.get("version")
        if cursor:
            if version and version != cursor["version"]:
                raise ReadError("INVALID_CURSOR", "Cursor version differs")
            version = cursor["version"]
        with self.request() as c:
            if version:
                release = c.execute(
                    "SELECT * FROM webb_sdi.versions WHERE version=%s AND state='published'",
                    (version,),
                ).fetchone()
            else:
                release = c.execute(
                    "SELECT v.* FROM webb_sdi.accepted a JOIN webb_sdi.versions v USING(version) WHERE a.singleton AND v.state='published'"
                ).fetchone()
            if not release:
                raise ReadError(
                    "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                    "No accepted historical disclosure version",
                )
            if release["manifest"]["archiveSha256"] != ARCHIVE_SHA:
                raise ReadError("PACK_UNAVAILABLE", "Archive source identity differs")
            selected = release["version"]
            more = None
            if operation == "issuers":
                code, name = params.get("stockCode"), params.get("q")
                if bool(code) == bool(name):
                    raise ReadError(
                        "INVALID_QUERY", "Use exact stock code or issuer-name prefix"
                    )
                after = cursor["last"] if cursor else 0
                if code:
                    if not re.fullmatch(r"[0-9]{1,5}", code):
                        raise ReadError("INVALID_ID", "Use a digit stock code")
                    statement = "SELECT issuer_id,min(issuer_name) AS name,min(event_date)::text AS first_event,max(event_date)::text AS last_event,count(*) AS archive_filings,array_agg(DISTINCT stock_code ORDER BY stock_code) AS stock_codes FROM webb_sdi.filings WHERE version=%s AND stock_code=%s AND issuer_id>%s GROUP BY issuer_id ORDER BY issuer_id LIMIT %s"
                    rows = c.execute(
                        statement, (selected, code.zfill(5), after, limit + 1)
                    ).fetchall()
                else:
                    key = search_key(name)
                    if not 2 <= len(key) <= 200 or any(ord(ch) < 32 for ch in key):
                        raise ReadError(
                            "INVALID_QUERY", "Use a literal prefix of 2–200 characters"
                        )
                    rows = c.execute(
                        "WITH matches AS (SELECT DISTINCT issuer_id FROM webb_sdi.filings WHERE version=%s AND issuer_search_key>=%s AND issuer_search_key<%s AND issuer_id>%s ORDER BY issuer_id LIMIT %s) SELECT f.issuer_id,min(f.issuer_name) AS name,min(f.event_date)::text AS first_event,max(f.event_date)::text AS last_event,count(*) AS archive_filings,array_agg(DISTINCT f.stock_code ORDER BY f.stock_code) AS stock_codes FROM matches m JOIN webb_sdi.filings f ON f.issuer_id=m.issuer_id AND f.version=%s GROUP BY f.issuer_id ORDER BY f.issuer_id",
                        (selected, key, prefix_end(key), after, limit + 1, selected),
                    ).fetchall()
                if len(rows) > limit:
                    rows = rows[:limit]
                    more = rows[-1]["issuer_id"]
                data = [
                    dict(
                        r,
                        issuer_id="webb:person:" + str(r["issuer_id"]),
                        source="webb_sdi_archive",
                        identityQualification="Webb source issue-to-issuer mapping; stock code is not a permanent issuer identity",
                    )
                    for r in rows
                ]
            elif operation == "disclosures":
                issuer = identifier(params.get("issuerId"), "webb:person:")
                start, end = params.get("start"), params.get("end")
                if bool(start) != bool(end):
                    raise ReadError(
                        "INVALID_QUERY", "Provide both event-date endpoints or neither"
                    )
                if start:
                    try:
                        begin, finish = date.fromisoformat(start), date.fromisoformat(
                            end
                        )
                        if not 1 <= (finish - begin).days <= 31:
                            raise ValueError()
                    except (ValueError, TypeError) as exc:
                        raise ReadError(
                            "INVALID_QUERY",
                            "Use an event window of 1–31 calendar days; end exclusive",
                        ) from exc
                else:
                    begin = finish = None
                last = cursor["last"] if cursor else ["9999-12-31", 9223372036854775807]
                rows = c.execute(
                    "SELECT * FROM webb_sdi.filings WHERE version=%s AND issuer_id=%s AND (%s::date IS NULL OR event_date>=%s) AND (%s::date IS NULL OR event_date<%s) AND (COALESCE(event_date,'0001-01-01'::date),id)<(%s::date,%s) ORDER BY COALESCE(event_date,'0001-01-01'::date) DESC,id DESC LIMIT %s",
                    (
                        selected,
                        issuer,
                        begin,
                        begin,
                        finish,
                        finish,
                        last[0],
                        last[1],
                        limit + 1,
                    ),
                ).fetchall()
                if len(rows) > limit:
                    rows = rows[:limit]
                    more = [str(rows[-1]["event_date"] or date.min), rows[-1]["id"]]
                data = [self.filing(c, selected, r) for r in rows]
            elif operation == "disclosure":
                fid = identifier(params.get("filingId"), "webb:sdi:")
                row = c.execute(
                    "SELECT * FROM webb_sdi.filings WHERE version=%s AND id=%s",
                    (selected, fid),
                ).fetchone()
                if not row:
                    raise ReadError(
                        "NOT_FOUND", "Disclosure absent from this archive version"
                    )
                data = self.filing(c, selected, row)
            else:
                raise ReadError("INVALID_QUERY", "Unknown archive operation")
            sealed = (
                self.shared.seal(
                    {
                        "op": "webb_sdi:" + operation,
                        "filters": filters,
                        "version": selected,
                        "last": more,
                        "expires": time.time() + 48 * 3600,
                    }
                )
                if more is not None
                else None
            )
            result = {
                "source": "webb_sdi_archive",
                "version": selected,
                "coverage": release["manifest"],
                "data": data,
                "nextCursor": sealed,
                "notice": NOTICE,
            }
            if len(json.dumps(result, ensure_ascii=False).encode()) > 2 * 1024 * 1024:
                raise ReadError("OUTPUT_LIMIT", "Archive response exceeds 2 MiB")
            return result

    def filing(self, c, version, row):
        r = row["source"]
        related = []
        for relation, key in [
            ("amends", "serNoAmend"),
            ("superseded_by", "serNoSuper"),
        ]:
            if r[key]:
                found = c.execute(
                    "SELECT id FROM webb_sdi.filings WHERE version=%s AND serial=%s",
                    (version, r[key]),
                ).fetchone()
                related.append(
                    {
                        "relation": relation,
                        "serial": r[key],
                        "filing_id": "webb:sdi:" + str(found["id"]) if found else None,
                        "resolved": bool(found),
                    }
                )
        caps = c.execute(
            "SELECT x.code AS capacity_code,d.label AS capacity_label,x.position_code,x.shares FROM webb_sdi.capacities x LEFT JOIN webb_sdi.dictionaries d ON d.version=x.version AND d.family='capacity' AND d.code=x.code WHERE x.version=%s AND x.filing_id=%s ORDER BY x.code,x.position_code",
            (version, row["id"]),
        ).fetchall()
        events = c.execute(
            "SELECT x.source,d.label AS reason_label FROM webb_sdi.events x LEFT JOIN webb_sdi.dictionaries d ON d.version=x.version AND d.family='sdireason' AND d.code=x.source->>'reason' WHERE x.version=%s AND x.filing_id=%s ORDER BY x.position_code",
            (version, row["id"]),
        ).fetchall()
        caps = [
            dict(cap, position=POSITIONS.get(cap["position_code"], "unknown"))
            for cap in caps
        ]
        return {
            "id": "webb:sdi:" + str(row["id"]),
            "source_id": str(row["id"]),
            "serial": row["serial"],
            "legacy_filing_key": row["legacy_filing"],
            "form_code": r["form"],
            "form_label": (
                "Form 3A (Webb collector)"
                if r["form"] == "3"
                else "Unqualified source form " + str(r["form"])
            ),
            "issuer_id": "webb:person:" + str(row["issuer_id"]),
            "security_id": "webb:issue:" + str(row["issue_id"]),
            "stock_code": row["stock_code"],
            "source_stock_code": r["stockCode"],
            "issuer_name": r["stockName"],
            "discloser": {
                "name1": r["name1"],
                "name2": r["name2"],
                "chinese_name": r["cName"],
            },
            "event_date": r["relDate"],
            "awareness_date": r["awDate"],
            "signed_date": r["signDate"],
            "source_modified": r["modified"],
            "filed_date": None,
            "published_date": None,
            "before": {
                "long_shares": r["longShs1"],
                "long_percent": r["longStk1"],
                "short_shares": r["shortShs1"],
                "short_percent": r["shortStk1"],
            },
            "after": {
                "long_shares": r["longShs2"],
                "long_percent": r["longStk2"],
                "short_shares": r["shortShs2"],
                "short_percent": r["shortStk2"],
            },
            "capacities": caps,
            "events": [
                dict(
                    e["source"],
                    reason_label=e["reason_label"],
                    position=POSITIONS.get(e["source"]["posType"], "unknown"),
                )
                for e in events
            ],
            "revision_links": related,
            "interpretation": (
                "Marked superseded in this archive"
                if r["serNoSuper"]
                else "No superseding serial recorded; current effectiveness/withdrawal not established"
            ),
            "source_fields": r,
        }
