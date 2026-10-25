"""Bounded owner-operated retention cleanup. No source network or growth schedule."""

import json
import os

from .db import connect


def expire_raw(dsn):
    """Erase at most 1000 expired bodies, retaining identity/hash/policy/job receipts."""
    with connect(dsn) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(7242526)")
        result = conn.execute(
            "WITH due AS (SELECT capture_id FROM racing.capture_buffer WHERE body IS NOT NULL AND expires_at<=now() ORDER BY expires_at,capture_id LIMIT 1000 FOR UPDATE SKIP LOCKED) UPDATE racing.capture_buffer b SET body=NULL FROM due WHERE b.capture_id=due.capture_id RETURNING b.capture_id"
        ).fetchall()
        return {"erasedBodies": len(result), "limit": 1000, "metadataRetained": True}


def main():
    # Dedicated source writer only; no caller SQL, host, URL or file path.
    print(json.dumps(expire_raw(os.environ["RACING_WRITER_DSN"])))


if __name__ == "__main__":
    main()
