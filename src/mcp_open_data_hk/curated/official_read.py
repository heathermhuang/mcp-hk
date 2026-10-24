"""Version-pinned official read view with no implied archive identity crosswalk."""

import contextlib
import re
import time

from .official import ATTRIBUTION, CATALOGUE, TERMS, LIMITATIONS
from .read import ReadError, prefix_end
from .normalize import search_key


class OfficialReader:
    def __init__(self, archive):
        self.archive = archive

    @contextlib.contextmanager
    def request(self):
        from psycopg.rows import dict_row
        from .build import connect
        from .security import safe_reader_role

        if not self.archive.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Read concurrency limit reached")
        try:
            with connect(
                self.archive.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as conn:
                if not safe_reader_role(conn):
                    raise ReadError(
                        "UNSAFE_READER", "Serving requires a dedicated SELECT-only role"
                    )
                unsafe = conn.execute(
                    "SELECT has_schema_privilege('curated','CREATE') AS creates, EXISTS(SELECT 1 FROM pg_tables WHERE schemaname='curated' AND (has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR tableowner=current_user)) AS writes"
                ).fetchone()
                if any(unsafe.values()):
                    raise ReadError(
                        "UNSAFE_READER", "Official reader has write privileges"
                    )
                yield conn
        except Exception as exc:
            from psycopg.errors import LockNotAvailable, QueryCanceled

            if isinstance(exc, (LockNotAvailable, QueryCanceled)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Official query exceeded its bound"
                ) from exc
            raise
        finally:
            self.archive.slots.release()

    def version(self, conn, version=None):
        if version:
            row = conn.execute(
                "SELECT * FROM curated.official_versions WHERE version=%s", (version,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT v.* FROM curated.official_versions v JOIN curated.official_pointer p USING(version)"
            ).fetchone()
        if not row:
            raise ReadError(
                "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                "No accepted official observation version",
            )
        return row

    def result(self, release, data, cursor=None):
        return {
            "version": release["version"],
            "data": data,
            "nextCursor": cursor,
            "provenance": {
                "view": "latest_observed",
                "attribution": ATTRIBUTION,
                "termsUrl": TERMS,
                "sourceUrl": CATALOGUE,
                "currentVerification": False,
                "coverage": release["manifest"],
                "limitations": LIMITATIONS,
            },
        }

    def search(self, name=None, namespace=None, value=None, limit=20, cursor=None):
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ReadError("INVALID_LIMIT", "Limit must be 1 through 100")
        if name is not None:
            key = search_key(name)
            if (
                namespace is not None
                or value is not None
                or not 2 <= len(key) <= 200
                or "\0" in key
            ):
                raise ReadError(
                    "INVALID_QUERY", "Choose a name prefix or exact official identifier"
                )
            filters = {"name": key}
            condition = "((r.name_key >= %s AND r.name_key < %s) OR (r.name2_key >= %s AND r.name2_key < %s))"
            params = (key, prefix_end(key), key, prefix_end(key))
        else:
            if (
                namespace not in {"cr:local:brn", "cr:foreign:brn", "cr:mlr"}
                or not isinstance(value, str)
                or not re.fullmatch(r"[A-Za-z0-9]{1,20}", value)
            ):
                raise ReadError(
                    "INVALID_QUERY",
                    "Use cr:local:brn, cr:foreign:brn or cr:mlr with the exact source value",
                )
            filters = {"namespace": namespace, "value": value}
            condition = "r.entity_id=%s"
            params = (namespace.replace(":brn", "") + ":" + value,)
        state = (
            self.archive.unseal(cursor, "official_search", filters) if cursor else None
        )
        with self.request() as conn:
            release = self.version(conn, state["version"] if state else None)
            rows = conn.execute(
                "SELECT DISTINCT ON(r.entity_id) r.entity_id,r.record FROM curated.official_records r JOIN curated.official_members m USING(capture_id) WHERE m.version=%s AND "
                + condition
                + " AND r.entity_id>%s ORDER BY r.entity_id, r.record->>'coverageEnd' DESC NULLS LAST,r.fact_id LIMIT %s",
                (
                    release["version"],
                    *params,
                    state["last"] if state else "",
                    limit + 1,
                ),
            ).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            token = (
                self.archive.seal(
                    {
                        "op": "official_search",
                        "filters": filters,
                        "version": release["version"],
                        "last": rows[-1]["entity_id"],
                        "expires": (
                            state["expires"] if state else int(time.time()) + 172800
                        ),
                    }
                )
                if more
                else None
            )
            data = [
                {
                    k: row["record"].get(k)
                    for k in (
                        "entity_id",
                        "kind",
                        "name1",
                        "chinese_name",
                        "identifier",
                        "coverageStart",
                        "coverageEnd",
                        "register",
                    )
                }
                for row in rows
            ]
            return self.result(release, data, token)

    def get(self, entity_id, version=None):
        if not re.fullmatch(
            r"cr:(?:local|foreign|mlr):[A-Za-z0-9]{1,20}", str(entity_id)
        ):
            raise ReadError(
                "INVALID_ID", "Use the exact official entity_id returned by search"
            )
        with self.request() as conn:
            release = self.version(conn, version)
            rows = conn.execute(
                "SELECT r.record FROM curated.official_records r JOIN curated.official_members m USING(capture_id) WHERE m.version=%s AND r.entity_id=%s ORDER BY r.record->>'coverageEnd' DESC NULLS LAST,r.fact_id LIMIT 101",
                (release["version"], entity_id),
            ).fetchall()
            if not rows:
                raise ReadError(
                    "NOT_FOUND",
                    "No accepted observation for this exact source identity",
                )
            records = [r["record"] for r in rows[:100]]
            latest = records[0]
            return self.result(
                release,
                {
                    "entity_id": entity_id,
                    "kind": latest["kind"],
                    "name1": latest["name1"],
                    "chinese_name": latest.get("chinese_name"),
                    "identifier": latest["identifier"],
                    "observations": records,
                    "observationCountScope": "at_most_100_in_selected_version",
                    "observationsTruncated": len(rows) > 100,
                },
            )

    def status(self):
        with self.request() as conn:
            release = self.version(conn)
            runs = conn.execute(
                "SELECT run_id,started_at,finished_at,status,receipt FROM curated.official_runs ORDER BY started_at DESC LIMIT 2"
            ).fetchall()
            return self.result(
                release, {"coverage": release["manifest"], "recentRuns": runs}
            )
