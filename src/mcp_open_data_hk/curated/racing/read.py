"""Bounded read-only racing queries; uses the archive reader's shared query slots."""

import contextlib
import time

from .db import connect
from ..read import ReadError
from ..security import safe_reader_role
from .policy import RacingRejected
from .store import policy


class RacingReader:
    def __init__(self, reader):
        self.reader = reader

    @contextlib.contextmanager
    def request(self, family, mode, version=None):
        if not self.reader.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Shared query slots busy")
        try:
            with connect(
                self.reader.dsn,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as conn:
                if not safe_reader_role(conn):
                    raise ReadError(
                        "UNSAFE_READER", "Dedicated SELECT-only role required"
                    )
                unsafe = conn.execute(
                    "SELECT has_schema_privilege('racing','CREATE') AS creates, EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='racing' AND (has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR tableowner=current_user)) AS writes"
                ).fetchone()
                if any(unsafe.values()):
                    raise ReadError(
                        "UNSAFE_READER", "Reader has racing write privileges"
                    )
                release = conn.execute(
                    "SELECT v.* FROM racing.versions v WHERE v.version=COALESCE(%s,(SELECT version FROM racing.accepted WHERE pack='hkjc_racing')) AND state='published'",
                    (version,),
                ).fetchone()
                if release is None:
                    raise ReadError(
                        "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                        "No accepted racing version",
                    )
                # Synthetic bundles are never public data, even under a permissive test policy.
                if release["manifest"].get("synthetic"):
                    raise ReadError(
                        "PACK_UNAVAILABLE",
                        "Synthetic racing fixture is not public source data",
                    )
                grant = policy(conn, release["policy_digest"], family, mode)
                yield conn, release, grant
                policy(conn, release["policy_digest"], family, mode)
        except RacingRejected as exc:
            raise ReadError(
                "SOURCE_MODE_UNQUALIFIED", "Racing output is held by source policy"
            ) from exc
        except Exception as exc:
            from psycopg.errors import QueryCanceled, LockNotAvailable

            if isinstance(exc, (QueryCanceled, LockNotAvailable)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Racing query exceeded its bound"
                ) from exc
            raise
        finally:
            self.reader.slots.release()

    def page(
        self, operation, *, mode="rest", limit=20, cursor=None, version=None, **filters
    ):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadError("INVALID_LIMIT", "Limit must be 1 through 100")
        families = {
            "races": "races",
            "results": "results",
            "profile": "profiles",
            "observations": "odds",
        }
        if operation not in families or mode not in {"rest", "mcp", "browser"}:
            raise ReadError("INVALID_QUERY", "Unsupported racing query")
        if operation == "observations":
            if filters.get("kind") not in {"odds", "pool_investments", "changes"}:
                raise ReadError(
                    "INVALID_QUERY", "Choose the qualified observation family"
                )
            families[operation] = filters["kind"]
        binding = {"source": "hkjc", **filters}
        state = (
            self.reader.unseal(cursor, "racing:" + operation, binding)
            if cursor
            else None
        )
        if state and version and state["version"] != version:
            raise ReadError("INVALID_CURSOR", "Cursor version differs")
        selected = state["version"] if state else version
        with self.request(families[operation], mode, selected) as (
            conn,
            release,
            grant,
        ):
            now = int(time.time())
            # Cursor retention can never exceed the qualified retained history.
            expires = (
                state["expires"]
                if state
                else now + min(48 * 3600, grant["retentionSeconds"])
            )
            if now - release["created_at"].timestamp() > grant["retentionSeconds"]:
                raise ReadError(
                    "VERSION_EXPIRED", "Racing source retention window elapsed"
                )
            last = state["last"] if state else ""
            params = (release["version"],)
            if operation == "races":
                if set(filters) - {"day", "venue", "season"}:
                    raise ReadError("INVALID_QUERY", "Unknown race filter")
                query = "SELECT r.*, r.race_id AS page_key FROM racing.races r JOIN racing.meetings m USING(version,meeting_id) WHERE r.version=%s"
                for field, column in (
                    ("day", "m.local_date"),
                    ("venue", "m.venue"),
                    ("season", "m.season"),
                ):
                    if filters.get(field):
                        query += f" AND {column}=%s"
                        params += (filters[field],)
                query += " AND r.race_id>%s ORDER BY r.race_id LIMIT %s"
            elif operation == "results":
                if set(filters) != {"race_id"}:
                    raise ReadError("INVALID_QUERY", "Exact race ID required")
                query = "SELECT f.*, f.fact_id||':'||f.revision AS page_key FROM racing.results f WHERE version=%s AND race_id=%s AND f.fact_id||':'||f.revision>%s ORDER BY page_key LIMIT %s"
                params += (filters["race_id"],)
            elif operation == "profile":
                if set(filters) != {"participant_id"}:
                    raise ReadError("INVALID_QUERY", "Exact participant ID required")
                query = "SELECT p.*, p.capture_id AS page_key FROM racing.profile_observations p WHERE version=%s AND participant_id=%s AND capture_id>%s ORDER BY capture_id LIMIT %s"
                params += (filters["participant_id"],)
            else:
                if set(filters) != {"race_id", "market", "start", "end", "kind"}:
                    raise ReadError(
                        "INVALID_QUERY", "Exact bounded series window required"
                    )
                from .policy import utc

                start, end = utc(filters["start"]), utc(filters["end"])
                if not 0 < (end - start).total_seconds() <= 86400:
                    raise ReadError(
                        "INVALID_QUERY", "Series window must be within one day"
                    )
                query = "SELECT o.*, o.series_id||':'||lpad(o.sequence::text,20,'0')||':'||o.selection AS page_key FROM racing.observations o WHERE version=%s AND race_id=%s AND market=%s AND kind=%s AND observed_at>=%s AND observed_at<%s AND o.series_id||':'||lpad(o.sequence::text,20,'0')||':'||o.selection>%s ORDER BY page_key LIMIT %s"
                params += (filters["race_id"], filters["market"], start, end)
            rows = conn.execute(query, (*params, last, limit + 1)).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            token = (
                self.reader.seal(
                    {
                        "op": "racing:" + operation,
                        "filters": binding,
                        "version": release["version"],
                        "last": rows[-1]["page_key"],
                        "expires": expires,
                    }
                )
                if more
                else None
            )
            for row in rows:
                row.pop("page_key")
                row.pop("version")
            for row in rows:
                policy(
                    conn,
                    release["policy_digest"],
                    families[operation],
                    mode,
                    fields=row.keys(),
                )
            # Explicit JSON scalars preserve Decimal units across HTTP serialization.
            from decimal import Decimal
            from datetime import date, datetime

            def scalar(value):
                if isinstance(value, Decimal):
                    return str(value)
                if isinstance(value, (date, datetime)):
                    return value.isoformat()
                if isinstance(value, dict):
                    return {key: scalar(item) for key, item in value.items()}
                if isinstance(value, list):
                    return [scalar(item) for item in value]
                return value

            public_release = dict(
                release,
                manifest={
                    key: value
                    for key, value in release["manifest"].items()
                    if key
                    in {
                        "sourceCutoff",
                        "families",
                        "coverage",
                        "transformSha256",
                        "attribution",
                    }
                },
            )
            return self.reader.result(public_release, scalar(rows), token)


def grant_reader(dsn, role):
    from psycopg import sql

    with connect(dsn) as conn:
        if not safe_reader_role(conn, role):
            raise RacingRejected("UNSAFE_READER")
        conn.execute(
            sql.SQL("GRANT USAGE ON SCHEMA racing TO {}").format(sql.Identifier(role))
        )
        # No capture locations, job, budget or confidential policy payload access through SQL queries.
        for table in (
            "versions",
            "accepted",
            "policies",
            "meetings",
            "races",
            "participants",
            "runners",
            "results",
            "profile_observations",
            "sectionals",
            "dividends",
            "family_facts",
            "observations",
            "coverage",
        ):
            conn.execute(
                sql.SQL("GRANT SELECT ON racing.{} TO {}").format(
                    sql.Identifier(table), sql.Identifier(role)
                )
            )
