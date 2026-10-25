"""SELECT-only reader sharing the existing four-slot budget and cursor signer."""

import contextlib
import json
import time
from datetime import datetime, timezone

from psycopg import sql
from psycopg.rows import dict_row

from ..build import connect
from ..normalize import search_key
from ..read import ReadError, prefix_end
from ..security import safe_reader_role
from .contracts import NOTICE, Window, digest, exact, unavailable_status
from .store import current_policy


class HkexReader:
    def __init__(self, shared):
        self.shared = shared

    @contextlib.contextmanager
    def request(self):
        if not self.shared.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Shared query concurrency limit reached")
        try:
            with connect(
                self.shared.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as c:
                if not safe_reader_role(c):
                    raise ReadError(
                        "UNSAFE_READER", "Use a dedicated SELECT-only login"
                    )
                priv = c.execute(
                    "SELECT has_schema_privilege('hkex','CREATE') AS creates,EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='hkex' AND (has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR tableowner=current_user)) AS writes"
                ).fetchone()
                if any(priv.values()):
                    raise ReadError(
                        "UNSAFE_READER", "Reader has source write privileges"
                    )
                yield c
        except Exception as exc:
            from psycopg.errors import LockNotAvailable, QueryCanceled

            if isinstance(exc, (LockNotAvailable, QueryCanceled)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Source query exceeded its bound"
                ) from exc
            raise
        finally:
            self.shared.slots.release()

    def status(self, mode="rest", include_inventory=False):
        try:
            with self.request() as c:
                policy = current_policy(c)
                accepted = c.execute(
                    "SELECT v.version,v.manifest,v.published_at FROM hkex.accepted a JOIN hkex.versions v USING(version) WHERE a.singleton"
                ).fetchone()
                control = c.execute(
                    "SELECT hold_until,hold_code FROM hkex.control WHERE singleton"
                ).fetchone()
                coverage = accepted["manifest"]["coverage"] if accepted else None
                retained = bool(accepted) and datetime.fromisoformat(
                    accepted["manifest"]["retainedUntil"]
                ) > datetime.now(timezone.utc)
                if include_inventory:
                    policy.require(mode, "retain", "history")
                    if not retained:
                        raise ValueError("SOURCE_RETENTION_EXPIRED")
                elif coverage:
                    # Status remains useful without exposing unqualified issuer,
                    # filing, name, security or inventory facts through a side door.
                    window = {
                        key: value
                        for key, value in coverage["window"].items()
                        if key != "issuer_id"
                    }
                    if retained and policy.modes.get(mode) == "allowed":
                        window["issuer_id"] = coverage["window"]["issuer_id"]
                    coverage = {
                        "window": window,
                        "complete": coverage["complete"],
                        "pages": coverage["pages"],
                        "comprehensiveIncremental": False,
                    }
                current_policy(c, digest(policy))
                return {
                    "source": "hkex_di",
                    "state": (
                        "accepted"
                        if retained
                        else "version_expired" if accepted else "pilot_pending"
                    ),
                    "acceptedVersion": accepted["version"] if accepted else None,
                    "modes": policy.modes,
                    "coverage": coverage,
                    "hold": {
                        "until": (
                            control["hold_until"].isoformat()
                            if control["hold_until"]
                            else None
                        ),
                        "code": control["hold_code"],
                    },
                    "notice": NOTICE,
                }
        except ValueError:
            return unavailable_status()
        except Exception as exc:
            from psycopg.errors import (
                UndefinedTable,
                InvalidSchemaName,
                InsufficientPrivilege,
            )

            if isinstance(
                exc, (UndefinedTable, InvalidSchemaName, InsufficientPrivilege)
            ):
                return unavailable_status()
            raise

    def query(self, operation, params, mode="rest"):
        params = {k: v for k, v in params.items() if v is not None}
        limit = params.get("limit", 20)
        if (
            type(limit) is not int
            or not 1 <= limit <= 100
            or mode not in {"rest", "mcp", "browser", "export"}
        ):
            raise ReadError("INVALID_QUERY", "Invalid bounded read contract")
        filters = {
            k: v for k, v in params.items() if k not in {"cursor", "version", "limit"}
        }
        cursor = (
            self.shared.unseal(params["cursor"], "hkex:" + operation, filters)
            if params.get("cursor")
            else None
        )
        version = params.get("version")
        if cursor:
            if version and version != cursor["version"]:
                raise ReadError("INVALID_CURSOR", "Cursor version differs")
            version = cursor["version"]
        with self.request() as c:
            try:
                policy = current_policy(c, modes=(mode, "retain", "history"))
            except ValueError as exc:
                raise ReadError(
                    "HKEX_SOURCE_UNQUALIFIED", "HKEX output is not qualified"
                ) from exc
            if version:
                release = c.execute(
                    "SELECT * FROM hkex.versions WHERE version=%s AND state='published'",
                    (version,),
                ).fetchone()
            else:
                release = c.execute(
                    "SELECT v.* FROM hkex.accepted a JOIN hkex.versions v USING(version) WHERE a.singleton AND v.state='published'"
                ).fetchone()
            if release is None:
                raise ReadError(
                    "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                    "No retained accepted HKEX version",
                )
            # Rights for both the capture policy and the current policy must permit
            # output. A broader later policy cannot retroactively license facts.
            if release["policy_hash"] != digest(policy):
                raise ReadError(
                    "HKEX_SOURCE_UNQUALIFIED", "Version requires policy requalification"
                )
            retained_until = datetime.fromisoformat(
                release["manifest"]["retainedUntil"]
            )
            if datetime.now(timezone.utc) >= retained_until:
                raise ReadError("VERSION_EXPIRED", "HKEX version retention expired")
            after = cursor["last"] if cursor else ""
            if operation == "issuers":
                stock, name = params.get("stockCode"), params.get("q")
                if bool(stock) == bool(name):
                    raise ReadError(
                        "INVALID_QUERY", "Provide exact stockCode or issuer prefix"
                    )
                if stock:
                    if len(stock) != 5 or not stock.isascii() or not stock.isdigit():
                        raise ReadError("INVALID_ID", "Stock codes have five digits")
                    rows = c.execute(
                        "SELECT i.* FROM hkex.issuers i WHERE i.version=%s AND i.id>%s AND EXISTS(SELECT 1 FROM hkex.securities s WHERE s.version=i.version AND s.issuer_id=i.id AND s.stock_code=%s) ORDER BY i.id LIMIT %s",
                        (release["version"], after, stock, limit + 1),
                    ).fetchall()
                else:
                    key = search_key(name)
                    if not 2 <= len(key) <= 200 or any(ord(ch) < 32 for ch in key):
                        raise ReadError(
                            "INVALID_QUERY", "Prefix needs 2–200 characters"
                        )
                    rows = c.execute(
                        "SELECT * FROM hkex.issuers WHERE version=%s AND id>%s AND search_key>=%s AND search_key<%s ORDER BY id LIMIT %s",
                        (release["version"], after, key, prefix_end(key), limit + 1),
                    ).fetchall()
                for row in rows:
                    row.pop("search_key")
                    row.pop("version")
                    row["issuer_id"] = "hkex:issuer:" + row["id"]
                    row["securities"] = c.execute(
                        "SELECT id,stock_code,share_class,name,name_date FROM hkex.securities WHERE version=%s AND issuer_id=%s ORDER BY id",
                        (release["version"], row["id"]),
                    ).fetchall()
                key_field = "id"
            elif operation == "disclosures":
                try:
                    window = Window(
                        issuer_id=params["issuerId"],
                        start=params["start"],
                        end=params["end"],
                        basis=params["basis"],
                        channel=params.get("channel", "dion"),
                    )
                except (KeyError, ValueError) as exc:
                    raise ReadError(
                        "INVALID_QUERY", "Use an exact issuer and bounded date basis"
                    ) from exc
                declared = Window.model_validate(
                    release["manifest"]["coverage"]["window"]
                )
                if (
                    window.issuer_id != declared.issuer_id
                    or window.channel != declared.channel
                    or window.basis != declared.basis
                    or window.start < declared.start
                    or window.end > declared.end
                ):
                    raise ReadError(
                        "COVERAGE_UNAVAILABLE",
                        "Requested window is outside accepted coverage",
                    )
                field = sql.Identifier(window.basis + "_date")
                rows = c.execute(
                    sql.SQL(
                        "SELECT serial,payload FROM hkex.filings WHERE version=%s AND issuer_id=%s AND channel=%s AND {} >=%s AND {} <%s AND serial>%s AND (%s::text IS NULL OR form=%s) ORDER BY serial LIMIT %s"
                    ).format(field, field),
                    (
                        release["version"],
                        window.issuer_id,
                        window.channel,
                        window.start,
                        window.end,
                        after,
                        params.get("form"),
                        params.get("form"),
                        limit + 1,
                    ),
                ).fetchall()
                key_field = "serial"
            elif operation == "disclosure":
                try:
                    serial = exact(params["filingId"])
                except (KeyError, ValueError) as exc:
                    raise ReadError("INVALID_ID", "Use an exact filing serial") from exc
                row = c.execute(
                    "SELECT serial,payload FROM hkex.filings WHERE version=%s AND serial=%s",
                    (release["version"], serial),
                ).fetchone()
                if not row:
                    raise ReadError("NOT_FOUND", "Filing is absent from this version")
                rows, key_field = [row], "serial"
            else:
                raise ReadError("INVALID_QUERY", "Unsupported HKEX operation")
            next_cursor = None
            if len(rows) > limit:
                rows = rows[:limit]
                expires = min(
                    time.time() + policy.cursor_seconds,
                    policy.expires_at.timestamp(),
                    retained_until.timestamp(),
                )
                next_cursor = self.shared.seal(
                    {
                        "op": "hkex:" + operation,
                        "filters": filters,
                        "version": release["version"],
                        "last": rows[-1][key_field],
                        "expires": expires,
                    }
                )
            data = [r["payload"] if "payload" in r else r for r in rows]
            if operation != "issuers":
                for row in data:
                    capture = c.execute(
                        "SELECT m.* FROM hkex.capture_metadata m JOIN hkex.filings f ON f.capture_id=m.id WHERE f.version=%s AND f.serial=%s",
                        (release["version"], row["serial"]),
                    ).fetchone()
                    if not capture:
                        raise ReadError(
                            "PACK_UNAVAILABLE", "Capture lineage unavailable"
                        )
                    row["capture"] = dict(
                        capture, observed_at=capture["observed_at"].isoformat()
                    )
                    row["filing_id"] = "hkex:di:" + row["serial"]
                    row["issuer_source_id"] = "hkex:issuer:" + row["issuer_id"]
                    relations = c.execute(
                        "SELECT older,newer,resolved FROM hkex.revisions WHERE version=%s AND (older=%s OR newer=%s) ORDER BY older,newer",
                        (release["version"], row["serial"], row["serial"]),
                    ).fetchall()
                    row["revision_links"] = relations
                    row["currently_effective_notice"] = row[
                        "state"
                    ] != "withdrawn" and not any(
                        x["older"] == row["serial"] for x in relations
                    )
                    row["interpretation"] = (
                        "Dated notice in a revision chain; not current holdings"
                    )
            result = {
                "source": "hkex_di",
                "version": release["version"],
                "policyHash": release["policy_hash"],
                "coverage": release["manifest"]["coverage"],
                "notice": NOTICE,
                "dictionaries": policy.codes,
                "data": data[0] if operation == "disclosure" else data,
                "nextCursor": next_cursor,
            }
            current_policy(c, digest(policy), (mode, "retain", "history"))
            if len(json.dumps(result, ensure_ascii=False).encode()) > 2 * 1024 * 1024:
                raise ReadError("OUTPUT_LIMIT", "HKEX response exceeds its byte bound")
            return result
