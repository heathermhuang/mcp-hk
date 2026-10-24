"""SQLite generations: publish only a complete validated snapshot."""

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from .contracts import DomainError


class Store:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS snapshots (
                    id TEXT PRIMARY KEY, pack TEXT NOT NULL, hash TEXT NOT NULL,
                    retrieved REAL NOT NULL, checked REAL NOT NULL, count INTEGER NOT NULL, retired REAL);
                CREATE TABLE IF NOT EXISTS active_packs (pack TEXT PRIMARY KEY, snapshot TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS records (
                    snapshot TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY (snapshot, id));
                CREATE TABLE IF NOT EXISTS source_checks (
                    pack TEXT PRIMARY KEY, success REAL, failure REAL, error TEXT);
                CREATE TABLE IF NOT EXISTS address_cache (
                    key TEXT PRIMARY KEY, payload TEXT NOT NULL, retrieved REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS ingestion_runs (
                    id TEXT PRIMARY KEY, pack TEXT NOT NULL, started REAL NOT NULL,
                    finished REAL, status TEXT NOT NULL, snapshot TEXT, error TEXT,
                    capture TEXT);
                CREATE TABLE IF NOT EXISTS budgets (
                    source TEXT NOT NULL, day INTEGER NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(source, day));
            """
            )
            if "capture" not in {
                r[1] for r in db.execute("PRAGMA table_info(ingestion_runs)")
            }:
                db.execute("ALTER TABLE ingestion_runs ADD COLUMN capture TEXT")
            if "retired" not in {
                r[1] for r in db.execute("PRAGMA table_info(snapshots)")
            }:
                db.execute("ALTER TABLE snapshots ADD COLUMN retired REAL")
                db.execute(
                    "UPDATE snapshots SET retired=? WHERE id NOT IN (SELECT snapshot FROM active_packs)",
                    (time.time(),),
                )

    def prune(self):
        cutoff = time.time() - 48 * 3600
        with self.connect() as db:
            protected = {r[0] for r in db.execute("SELECT snapshot FROM active_packs")}
            for pack in ("restaurants", "population"):
                protected.update(
                    r[0]
                    for r in db.execute(
                        "SELECT id FROM snapshots WHERE pack=? ORDER BY retrieved DESC LIMIT 2",
                        (pack,),
                    )
                )
            obsolete = [
                r[0]
                for r in db.execute(
                    "SELECT id FROM snapshots WHERE retired<?", (cutoff,)
                )
                if r[0] not in protected
            ]
            for snapshot in obsolete:
                db.execute("DELETE FROM records WHERE snapshot=?", (snapshot,))
                db.execute("DELETE FROM snapshots WHERE id=?", (snapshot,))
            db.execute(
                "DELETE FROM address_cache WHERE retrieved<?", (time.time() - 86400,)
            )
            db.execute(
                "DELETE FROM budgets WHERE day<?", (int(time.time() // 86400) - 2,)
            )
            captures = set()
            for pack in ("restaurants", "population"):
                captures.update(
                    r[0]
                    for r in db.execute(
                        "SELECT capture FROM ingestion_runs WHERE pack=? AND capture IS NOT NULL ORDER BY started DESC LIMIT 2",
                        (pack,),
                    )
                )
            captures.update(
                r[0]
                for r in db.execute(
                    "SELECT capture FROM ingestion_runs WHERE started>? AND capture IS NOT NULL",
                    (cutoff,),
                )
            )
            for snapshot in protected:
                captures.update(
                    r[0]
                    for r in db.execute(
                        "SELECT capture FROM ingestion_runs WHERE snapshot=? AND capture IS NOT NULL",
                        (snapshot,),
                    )
                )
        folder = Path(self.path).parent / "captures"
        if captures and folder.exists():
            for path in folder.glob("*.json"):
                if path.stem not in captures:
                    path.unlink()

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        # No serving/maintenance query needs ATTACH or runtime native extensions.
        db.set_authorizer(
            lambda action, first, second, *_: (
                sqlite3.SQLITE_DENY
                if action in {sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH}
                or action == sqlite3.SQLITE_FUNCTION
                and second == "load_extension"
                else sqlite3.SQLITE_OK
            )
        )
        try:
            with db:
                yield db
        finally:
            db.close()

    def active(self, pack: str):
        with self.connect() as db:
            row = db.execute(
                "SELECT snapshot FROM active_packs WHERE pack=?", (pack,)
            ).fetchone()
        return row[0] if row else None

    def snapshot(self, pack: str, snapshot_id: str | None = None):
        with self.connect() as db:
            if snapshot_id:
                row = db.execute(
                    "SELECT * FROM snapshots WHERE id=? AND pack=?", (snapshot_id, pack)
                ).fetchone()
            else:
                row = db.execute(
                    "SELECT s.* FROM snapshots s JOIN active_packs a ON a.snapshot=s.id WHERE a.pack=?",
                    (pack,),
                ).fetchone()
            if not row:
                code = "SNAPSHOT_EXPIRED" if snapshot_id else "DATA_NOT_LOADED"
                raise DomainError(
                    code,
                    (
                        "Restart pagination"
                        if snapshot_id
                        else f"Refresh the {pack} pack before querying it"
                    ),
                    409 if snapshot_id else 503,
                )
            records = db.execute(
                "SELECT payload FROM records WHERE snapshot=? ORDER BY id", (row["id"],)
            ).fetchall()
        return dict(row), [json.loads(r[0]) for r in records]

    def check(self, pack: str, error: str | None = None):
        now = time.time()
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO source_checks(pack) VALUES (?)", (pack,))
            if error:
                db.execute(
                    "UPDATE source_checks SET failure=?,error=? WHERE pack=?",
                    (now, error, pack),
                )
            else:
                db.execute(
                    "UPDATE source_checks SET success=?,error=NULL WHERE pack=?",
                    (now, pack),
                )

    def publish(self, pack: str, rows: list[dict], expected: str | None):
        if not rows or len({r["id"] for r in rows}) != len(rows):
            raise DomainError(
                "INVALID_SNAPSHOT",
                "Snapshot is empty or has duplicate source identities",
            )
        encoded = json.dumps(
            sorted(rows, key=lambda r: r["id"]), ensure_ascii=False, sort_keys=True
        )
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        now, snapshot_id = time.time(), uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute(
                "SELECT snapshot FROM active_packs WHERE pack=?", (pack,)
            ).fetchone()
            current = active[0] if active else None
            if current != expected:
                raise DomainError(
                    "CONCURRENT_IMPORT",
                    "Another import published first; rerun from its checkpoint",
                    409,
                )
            if current:
                previous = db.execute(
                    "SELECT * FROM snapshots WHERE id=?", (current,)
                ).fetchone()
                if previous["hash"] == digest:
                    db.execute(
                        "UPDATE snapshots SET checked=? WHERE id=?", (now, current)
                    )
                    snapshot_id = current
                elif len(rows) < previous["count"] * 0.8:
                    raise DomainError(
                        "ROW_COUNT_DROP",
                        "Snapshot row count fell by more than 20%; previous generation retained",
                    )
            if snapshot_id != current:
                db.execute(
                    "INSERT INTO snapshots(id,pack,hash,retrieved,checked,count) VALUES (?,?,?,?,?,?)",
                    (snapshot_id, pack, digest, now, now, len(rows)),
                )
                db.executemany(
                    "INSERT INTO records VALUES (?,?,?)",
                    [
                        (snapshot_id, r["id"], json.dumps(r, ensure_ascii=False))
                        for r in rows
                    ],
                )
                db.execute(
                    "INSERT OR REPLACE INTO active_packs VALUES (?,?)",
                    (pack, snapshot_id),
                )
                if current and snapshot_id != current:
                    db.execute(
                        "UPDATE snapshots SET retired=? WHERE id=?", (now, current)
                    )
        self.check(pack)
        return snapshot_id

    def rollback(self, pack: str, snapshot_id: str):
        self.snapshot(pack, snapshot_id)
        with self.connect() as db:
            db.execute(
                "UPDATE active_packs SET snapshot=? WHERE pack=?", (snapshot_id, pack)
            )

    def cache_get(self, key: str, ttl: int = 86400):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM address_cache WHERE key=?", (key,)
            ).fetchone()
        if row and time.time() - row["retrieved"] < ttl:
            return json.loads(row["payload"]), row["retrieved"]
        return None

    def consume_budget(self, source: str, limit: int):
        day = int(time.time() // 86400)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT count FROM budgets WHERE source=? AND day=?", (source, day)
            ).fetchone()
            if row and row[0] >= limit:
                raise DomainError(
                    "SOURCE_BUDGET_EXHAUSTED",
                    "Daily live-source budget exhausted; cached queries may still work",
                )
            db.execute(
                "INSERT INTO budgets VALUES (?,?,1) ON CONFLICT(source,day) DO UPDATE SET count=count+1",
                (source, day),
            )

    def cache_put(self, key: str, data, source: str = "addresses"):
        now = time.time()
        with self.connect() as db:
            db.execute(
                "INSERT OR REPLACE INTO address_cache VALUES (?,?,?)",
                (key, json.dumps(data, ensure_ascii=False), now),
            )
            if source in {"platehk", "seehouse"}:
                # Keep a live query cache bounded; it is not a bulk data mirror.
                db.execute(
                    "DELETE FROM address_cache WHERE key LIKE ? AND retrieved<?",
                    (source + ":%", now - 300),
                )
                db.execute(
                    "DELETE FROM address_cache WHERE key IN (SELECT key FROM address_cache "
                    "WHERE key LIKE ? ORDER BY retrieved DESC LIMIT -1 OFFSET 200)",
                    (source + ":%",),
                )
        self.check(source)
        return now

    def checks(self):
        with self.connect() as db:
            return {
                r["pack"]: dict(r) for r in db.execute("SELECT * FROM source_checks")
            }
