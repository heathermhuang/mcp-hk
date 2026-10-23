"""Fixed parameterized queries with release-pinned, signed keyset pagination."""

import base64
import contextlib
import hmac
import json
import re
import threading
import time

from .build import connect
from .normalize import search_key
from .schema import schema_name
from .security import safe_reader_role


class ReadError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def prefix_end(key):
    for i in range(len(key) - 1, -1, -1):
        if ord(key[i]) < 0x10FFFF:
            code = ord(key[i]) + 1
            if 0xD800 <= code <= 0xDFFF:
                code = 0xE000
            return key[:i] + chr(code)
    raise ReadError("INVALID_QUERY", "Prefix has no supported upper bound")


class Reader:
    def __init__(self, dsn, cursor_secret):
        if len(cursor_secret) < 32:
            raise ValueError("Cursor secret must contain at least 32 bytes")
        self.dsn, self.secret = dsn, cursor_secret
        self.slots = threading.BoundedSemaphore(4)

    def seal(self, payload):
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        return (
            base64.urlsafe_b64encode(data + hmac.digest(self.secret, data, "sha256"))
            .decode()
            .rstrip("=")
        )

    def unseal(self, token, operation, filters):
        try:
            if len(token) > 2048:
                raise ValueError()
            raw = base64.b64decode(
                token + "=" * (-len(token) % 4), altchars=b"-_", validate=True
            )
            data, signature = raw[:-32], raw[-32:]
            if not hmac.compare_digest(
                signature, hmac.digest(self.secret, data, "sha256")
            ):
                raise ValueError()
            result = json.loads(data)
            if result["op"] != operation or result["filters"] != filters:
                raise ValueError()
            if result["expires"] < time.time():
                raise ReadError("VERSION_EXPIRED", "Cursor expired; restart the query")
            return result
        except ReadError:
            raise
        except (ValueError, KeyError, TypeError) as exc:
            raise ReadError(
                "INVALID_CURSOR", "Cursor does not match this query"
            ) from exc

    @contextlib.contextmanager
    def request(self, version=None):
        from psycopg import sql
        from psycopg.rows import dict_row

        if not self.slots.acquire(timeout=0.25):
            raise ReadError("QUERY_BUSY", "Read concurrency limit reached")
        try:
            with connect(
                self.dsn,
                row_factory=dict_row,
                options="-c search_path=pg_catalog -c default_transaction_read_only=on -c statement_timeout=2000 -c lock_timeout=250 -c idle_in_transaction_session_timeout=5000",
            ) as conn:
                if not safe_reader_role(conn):
                    raise ReadError(
                        "UNSAFE_READER", "Serving requires a dedicated SELECT-only role"
                    )
                if version is None:
                    row = conn.execute(
                        "SELECT v.* FROM curated.dataset_versions v JOIN curated.published_releases p USING(version) WHERE p.pack='enigma_hk'"
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT * FROM curated.dataset_versions WHERE version=%s AND state='published'",
                        (version,),
                    ).fetchone()
                if row is None:
                    raise ReadError(
                        "VERSION_EXPIRED" if version else "PACK_UNAVAILABLE",
                        "No accepted published release",
                    )
                schema = schema_name(row["version"])
                if schema != row["schema_name"]:
                    raise ReadError(
                        "PACK_UNAVAILABLE", "Release schema identity differs"
                    )
                privileges = conn.execute(
                    "SELECT has_schema_privilege(%s,'CREATE') AS create_schema, EXISTS(SELECT 1 FROM pg_tables WHERE schemaname IN ('curated',%s) AND (has_table_privilege(quote_ident(schemaname)||'.'||quote_ident(tablename),'INSERT,UPDATE,DELETE,TRUNCATE,TRIGGER,REFERENCES') OR tableowner=current_user)) AS writes",
                    (schema, schema),
                ).fetchone()
                if privileges["create_schema"] or privileges["writes"]:
                    raise ReadError("UNSAFE_READER", "Reader has write privileges")
                conn.execute(
                    sql.SQL("SET LOCAL search_path TO {},pg_catalog").format(
                        sql.Identifier(schema)
                    )
                )
                yield conn, row
        except Exception as exc:
            from psycopg.errors import LockNotAvailable, QueryCanceled

            if isinstance(exc, (LockNotAvailable, QueryCanceled)):
                raise ReadError(
                    "QUERY_TIMEOUT", "Indexed query exceeded its bound"
                ) from exc
            raise
        finally:
            self.slots.release()

    def result(self, release, data, next_cursor=None):
        result = {
            "version": release["version"],
            "provenance": dict(
                release["manifest"],
                temporalQualification=(release.get("restore_proof") or {}).get(
                    "temporal"
                ),
                asOfSupported=False,
            ),
            "data": data,
            "nextCursor": next_cursor,
        }
        if (
            len(json.dumps(result, default=str, ensure_ascii=False).encode())
            > 2 * 1024 * 1024
        ):
            raise ReadError("OUTPUT_LIMIT", "Result exceeds the response budget")
        return result

    def page(
        self, operation, filters, statement, params, limit=20, cursor=None, version=None
    ):
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= 100
        ):
            raise ReadError("INVALID_LIMIT", "Limit must be 1 through 100")
        state = self.unseal(cursor, operation, filters) if cursor else None
        if state and version is not None and version != state["version"]:
            raise ReadError("INVALID_CURSOR", "Cursor belongs to a different version")
        version = state["version"] if state else version
        with self.request(version) as (conn, release):
            if (
                "entity_id" in filters
                and conn.execute(
                    "SELECT 1 FROM entities WHERE entity_id=%s AND kind='organisation'",
                    (filters["entity_id"],),
                ).fetchone()
                is None
            ):
                raise ReadError(
                    "NOT_FOUND", "Entity absent in this selected archive version"
                )
            last = state["last"] if state else None
            query, values = statement(last, limit + 1, params)
            rows = conn.execute(query, values).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            token = None
            if more:
                token = self.seal(
                    {
                        "op": operation,
                        "filters": filters,
                        "version": release["version"],
                        "last": rows[-1]["page_key"],
                        "expires": (
                            state["expires"] if state else int(time.time()) + 48 * 3600
                        ),
                    }
                )
            for row in rows:
                row.pop("page_key")
            return self.result(release, rows, token)

    def search(self, name=None, namespace=None, value=None, limit=20, cursor=None):
        if name is not None:
            if namespace is not None or value is not None or not isinstance(name, str):
                raise ReadError("INVALID_QUERY", "Choose name or explicit identifier")
            key = search_key(name)
            if (
                not 2 <= len(key) <= 200
                or len(name) > 200
                or any(ord(c) == 0 or 0xD800 <= ord(c) <= 0xDFFF for c in key)
            ):
                raise ReadError(
                    "INVALID_QUERY", "Name prefix must have 2 through 200 characters"
                )
            end = prefix_end(key)
            filters = {"prefix": key}

            def statement(last, size, params):
                after_key, after_id, after_fact = last or [key, 0, ""]
                return (
                    "SELECT n.entity_id,n.display_name,n.language,n.name_kind,e.scope,ARRAY[n.search_key,n.entity_id::text,n.fact_id] AS page_key FROM entity_names n JOIN entities e USING(entity_id) WHERE e.kind='organisation' AND n.search_key >= %s AND n.search_key < %s AND (n.search_key,n.entity_id,n.fact_id) > (%s,%s,%s) ORDER BY n.search_key,n.entity_id,n.fact_id LIMIT %s",
                    (key, end, after_key, int(after_id), after_fact, size),
                )

        else:
            if (
                not isinstance(namespace, str)
                or not isinstance(value, str)
                or not namespace
                or not value
                or len(namespace) > 100
                or len(value) > 200
            ):
                raise ReadError(
                    "INVALID_QUERY",
                    "An explicit identifier namespace and value are required",
                )
            if not re.fullmatch(
                r"(?:webb:person|sfc:ce_reference|webb:incorporation:(?:[0-9]{1,5}|unknown))",
                namespace,
            ) or not re.fullmatch(r"[A-Za-z0-9./-]{1,200}", value):
                raise ReadError(
                    "INVALID_QUERY", "Unsupported identifier namespace or grammar"
                )
            if namespace == "webb:person" and not re.fullmatch(
                r"[1-9][0-9]{0,18}", value
            ):
                raise ReadError(
                    "INVALID_QUERY", "Source person ID must be a positive integer"
                )
            if namespace == "sfc:ce_reference" and not re.fullmatch(
                r"[A-Z]{3}[0-9]{3}", value
            ):
                raise ReadError(
                    "INVALID_QUERY",
                    "CE reference must have three uppercase letters and three digits",
                )
            filters = {"namespace": namespace, "value": value}

            def statement(last, size, params):
                return (
                    "SELECT i.entity_id,i.namespace,i.value,e.name1,e.scope,i.entity_id AS page_key FROM entity_identifiers i JOIN entities e USING(entity_id) WHERE i.namespace=%s AND i.value=%s AND e.kind='organisation' AND i.entity_id>%s ORDER BY i.entity_id LIMIT %s",
                    (namespace, value, last or 0, size),
                )

        return self.page("company_search", filters, statement, (), limit, cursor)

    def get(self, entity_id, version=None):
        if (
            not isinstance(entity_id, int)
            or isinstance(entity_id, bool)
            or not 0 < entity_id < 2**63
        ):
            raise ReadError("INVALID_ID", "Entity ID must be a positive source integer")
        with self.request(version) as (conn, release):
            row = conn.execute(
                "SELECT * FROM entities WHERE entity_id=%s", (entity_id,)
            ).fetchone()
            if row is None:
                raise ReadError(
                    "NOT_FOUND", "Entity absent in this selected archive version"
                )
            row["identifiers"] = conn.execute(
                "SELECT namespace,value,source_column FROM entity_identifiers WHERE entity_id=%s ORDER BY namespace,value",
                (entity_id,),
            ).fetchall()
            return self.result(release, row)

    def related(
        self, entity_id, family, limit=20, cursor=None, as_of=None, version=None
    ):
        if as_of is not None:
            raise ReadError(
                "AS_OF_UNSUPPORTED",
                "Archive intervals are not qualified for exact as-of reconstruction",
            )
        if (
            not isinstance(entity_id, int)
            or isinstance(entity_id, bool)
            or not 0 < entity_id < 2**63
        ):
            raise ReadError("INVALID_ID", "Entity ID must be a positive source integer")
        queries = {
            "names": ("entity_names", "entity_id", "fact_id"),
            "officers": ("officer_appointments", "company_id", "source_id"),
            "licences": ("licences", "company_id", "source_id"),
            "licence_relationships": (
                "licence_relationships",
                "company_id",
                "source_id",
            ),
        }
        if family not in queries:
            raise ReadError("INVALID_QUERY", "Unsupported relationship family")
        table, column, order = queries[family]

        def statement(last, size, params):
            # Identifiers and joins come only from this fixed family mapping.
            extra, joins = "", ""
            if family in {"officers", "licence_relationships"}:
                party_key = "officer_id" if family == "officers" else "person_id"
                extra += ",jsonb_build_object('entityId',p.entity_id,'kind',p.kind,'name1',p.name1,'name2',p.name2,'chineseName',p.chinese_name) AS party"
                joins += f" JOIN entities p ON p.entity_id=t.{party_key}"
            if family == "officers":
                extra += ",role.label AS role_label"
                joins += " JOIN source_references role ON role.family='positions' AND role.code=t.role_id"
            if family in {"licences", "licence_relationships"}:
                extra += ",activity.label AS activity_label"
                joins += " JOIN source_references activity ON activity.family='activity' AND activity.code=t.activity_id"
            return (
                f"SELECT t.*,t.{order} AS page_key{extra} FROM {table} t{joins} WHERE t.{column}=%s AND t.{order}>%s ORDER BY t.{order} LIMIT %s",
                (
                    entity_id,
                    last if last is not None else ("" if order == "fact_id" else 0),
                    size,
                ),
            )

        return self.page(
            family, {"entity_id": entity_id}, statement, (), limit, cursor, version
        )
