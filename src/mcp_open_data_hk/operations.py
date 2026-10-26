"""Consistent SQLite checkpoints and authenticated ephemeral-host recovery."""

import asyncio
import hashlib
import hmac
import io
import os
import re
import sqlite3
import tarfile
import tempfile
import threading
import urllib.request
import zlib
from contextlib import closing
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .contracts import DomainError

MAX_BACKUP = 150_000_000
MAX_DATABASE = 500_000_000
MAX_RESTORE = 750_000_000
refresh_lock = asyncio.Lock()
checkpoint_lock = threading.Lock()


def authorized(value: str | None):
    token = os.environ.get("MCP_HK_OPS_TOKEN", "")
    return bool(token) and hmac.compare_digest(value or "", "Bearer " + token)


def checkpoint(database: str, compresslevel=6) -> tuple[Path, str]:
    """Use SQLite's backup API, never copy a live WAL database file."""
    with checkpoint_lock:
        folder = Path(database).parent
        fd, name = tempfile.mkstemp(prefix="checkpoint-", suffix=".sqlite3", dir=folder)
        os.close(fd)
        raw, packed = Path(name), Path(name + ".tar.gz")
        try:
            with (
                closing(sqlite3.connect(database)) as source,
                closing(sqlite3.connect(raw)) as destination,
            ):
                source.backup(destination)
                # Shared archive compression is much smaller than independently
                # compressed metadata rows. Change only the isolated backup copy;
                # record-cache blobs retain their bounded cache encoding.
                tables = {
                    row[0]
                    for row in destination.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                expanded = False
                for table, column in (
                    ("inventory_resources", "payload"),
                    ("resource_variants", "schema_json"),
                ):
                    if table not in tables:
                        continue
                    rows = destination.execute(
                        f"SELECT rowid,{column} FROM {table} WHERE typeof({column})='blob'"
                    ).fetchall()
                    for rowid, payload in rows:
                        destination.execute(
                            f"UPDATE {table} SET {column}=? WHERE rowid=?",
                            (zlib.decompress(payload).decode("utf-8"), rowid),
                        )
                    expanded = expanded or bool(rows)
                if expanded:
                    destination.commit()
                    destination.execute("VACUUM")
                if destination.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise ValueError("Checkpoint integrity check failed")
            if raw.stat().st_size > MAX_DATABASE:
                raise ValueError("Checkpoint exceeds restored database size limit")
            with tarfile.open(packed, "w:gz", compresslevel=compresslevel) as archive:
                archive.add(raw, arcname="database.sqlite3", recursive=False)
                for capture in sorted((folder / "captures").glob("*.json")):
                    if (
                        re.fullmatch(r"[a-f0-9]{64}\.json", capture.name)
                        and not capture.is_symlink()
                    ):
                        archive.add(
                            capture, arcname="captures/" + capture.name, recursive=False
                        )
            if packed.stat().st_size > MAX_BACKUP:
                raise ValueError("Checkpoint exceeds storage transfer limit")
            digest = hashlib.sha256(packed.read_bytes()).hexdigest()
            return packed, digest
        except Exception:
            packed.unlink(missing_ok=True)
            raise
        finally:
            raw.unlink(missing_ok=True)


def restore(data: bytes, digest: str, database: str):
    if len(data) > MAX_BACKUP or not hmac.compare_digest(
        hashlib.sha256(data).hexdigest(), digest
    ):
        raise ValueError("Backup checksum mismatch")
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="restore-", dir=path.parent) as name:
        folder = Path(name)
        candidate = folder / "database.sqlite3"
        total = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
            names = set()
            for member in archive:
                if (
                    not member.isfile()
                    or member.name in names
                    or not (
                        member.name == "database.sqlite3"
                        or re.fullmatch(r"captures/[a-f0-9]{64}\.json", member.name)
                    )
                ):
                    raise ValueError("Backup contains an unexpected path or file type")
                names.add(member.name)
                total += member.size
                if total > MAX_RESTORE or (
                    member.name == "database.sqlite3" and member.size > MAX_DATABASE
                ):
                    raise ValueError("Restored data exceeds size limit")
                target = folder / member.name
                target.parent.mkdir(exist_ok=True)
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError("Backup member cannot be read")
                with source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        output.write(chunk)
                if (
                    member.name.startswith("captures/")
                    and hashlib.sha256(target.read_bytes()).hexdigest() != target.stem
                ):
                    raise ValueError("Source capture checksum mismatch")
        if not candidate.exists():
            raise ValueError("Backup lacks its database")
        with closing(sqlite3.connect(candidate)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Restored database integrity check failed")
            packs = {row[0] for row in db.execute("SELECT pack FROM active_packs")}
            if not {"restaurants", "population"} <= packs:
                raise ValueError("Backup lacks required data packs")
            for pack in ("restaurants", "population"):
                count = db.execute(
                    "SELECT count(*) FROM records WHERE snapshot=(SELECT snapshot FROM active_packs WHERE pack=?)",
                    (pack,),
                ).fetchone()[0]
                if count < (18 if pack == "population" else 1):
                    raise ValueError("Backup data pack is incomplete")
        # Restore is startup/operator-only, before opening service connections.
        if Path(str(path) + "-wal").exists():
            raise ValueError("Refusing to overwrite a database with a live WAL")
        os.replace(candidate, path)
        captures = path.parent / "captures"
        captures.mkdir(exist_ok=True)
        for capture in (folder / "captures").glob("*.json"):
            os.replace(capture, captures / capture.name)


def bootstrap():
    url = os.environ.get("MCP_HK_BOOTSTRAP_URL")
    if not url:
        return
    if not url.startswith("https://"):
        raise ValueError("Bootstrap requires HTTPS")
    token = os.environ.get("MCP_HK_OPS_TOKEN", "")
    if not token:
        raise ValueError("Bootstrap authentication is missing")
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": "Bearer " + token,
            "User-Agent": "mcp.hk-operations/0.3",
        },
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise ValueError("Bootstrap redirects are not allowed")

    with urllib.request.build_opener(NoRedirect).open(request, timeout=30) as response:
        data = response.read(MAX_BACKUP + 1)
        digest = response.headers.get("X-Snapshot-SHA256", "")
    restore(data, digest, os.environ.get("MCP_HK_DATABASE", ".data/mcp-hk.sqlite3"))


def register_operations(app, service):
    async def send_checkpoint(compresslevel=6):
        await asyncio.to_thread(service.store.prune)
        path, digest = await asyncio.to_thread(
            checkpoint, service.store.path, compresslevel
        )
        candidate = await asyncio.to_thread(service.racing.store.pending)
        return FileResponse(
            path,
            media_type="application/gzip",
            headers={
                "X-Snapshot-SHA256": digest,
                **({"X-Racing-Candidate": candidate} if candidate else {}),
            },
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @app.post("/__ops/backup", include_in_schema=False)
    async def backup(request: Request):
        if not authorized(request.headers.get("authorization")):
            raise DomainError("NOT_FOUND", "Not found", 404)
        return await send_checkpoint()

    @app.post("/__ops/racing", include_in_schema=False)
    async def racing_operator(request: Request):
        if not authorized(request.headers.get("authorization")):
            raise DomainError("NOT_FOUND", "Not found", 404)
        if refresh_lock.locked():
            raise DomainError("REFRESH_IN_PROGRESS", "Another refresh is running", 409)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 16 * 1024 * 1024:
                raise DomainError("BODY_LIMIT", "Racing import exceeds bound", 413)
        import json
        from .curated.racing.policy import RacingRejected

        try:
            body = json.loads(raw)
            async with refresh_lock:
                inspection = None
                if body.get("action") == "import":
                    await asyncio.to_thread(
                        service.racing.store.import_bundle, body["bundle"]
                    )
                elif body.get("action") == "profile_import":
                    await asyncio.to_thread(
                        service.racing.store.profiles.stage,
                        body["observations"],
                        body["captures"],
                    )
                elif body.get("action") == "profile_advance":
                    await asyncio.to_thread(service.racing.store.profiles.collect, 2)
                elif body.get("action") == "profile_policy":
                    await asyncio.to_thread(
                        service.racing.store.profiles.install_policy,
                        body["record"],
                        body["sha256"],
                    )
                elif body.get("action") == "inspect_redirect":
                    from .racing_inspection import inspect_redirect

                    inspection = await asyncio.to_thread(
                        inspect_redirect, service.racing.store, body["attempt"]
                    )
                elif body.get("action") == "enqueue":
                    await asyncio.to_thread(
                        service.racing.store.enqueue,
                        body["meetings"],
                        body.get("refresh", False),
                    )
                elif body.get("action") == "advance":
                    await asyncio.to_thread(service.racing.advance, 40)
                elif body.get("action") == "calendar":
                    await asyncio.to_thread(
                        service.racing.store.calendar, body["year"], body["month"]
                    )
                elif body.get("action") == "reconcile_parser":
                    await asyncio.to_thread(
                        service.racing.store.reconcile_parser_fix,
                        body["attempt"],
                        body["transformSha256"],
                    )
                else:
                    raise DomainError(
                        "INVALID_QUERY", "Unknown racing operator action", 400
                    )
                response = await send_checkpoint(compresslevel=1)
                if inspection is not None:
                    response.headers["X-Racing-Inspection"] = json.dumps(
                        inspection, ensure_ascii=True, separators=(",", ":")
                    )
                return response
        except (ValueError, KeyError, TypeError, RacingRejected) as exc:
            raise DomainError(
                "RACING_INGEST_REJECTED",
                "Racing import/collection was not accepted; inspect the preserved source receipt",
                400,
            ) from exc

    @app.post("/__ops/racing/qualify", include_in_schema=False)
    async def racing_qualify(request: Request):
        if not authorized(request.headers.get("authorization")):
            raise DomainError("NOT_FOUND", "Not found", 404)
        raw = await request.body()
        if len(raw) > 1024:
            raise DomainError("BODY_LIMIT", "Qualification body exceeds bound", 413)
        import json

        body = json.loads(raw)
        async with refresh_lock:
            await asyncio.to_thread(
                service.racing.qualify_checkpoint, body["version"], body["backupSha256"]
            )
            return await send_checkpoint(compresslevel=1)

    @app.post("/__ops/refresh", include_in_schema=False)
    async def refresh_data(request: Request, pack: str):
        if not authorized(request.headers.get("authorization")):
            raise DomainError("NOT_FOUND", "Not found", 404)
        if pack not in {
            "restaurants",
            "population",
            "all",
            "catalogue",
            "resources",
            "resources-recovery",
            "racing",
        }:
            raise DomainError("INVALID_PACK", "Unknown pack", 400)
        if refresh_lock.locked():
            raise DomainError("REFRESH_IN_PROGRESS", "Another refresh is running", 409)
        from .ingest import refresh

        async with refresh_lock:
            if pack == "racing":
                await asyncio.to_thread(service.racing.advance, 40)
                return await send_checkpoint(compresslevel=1)
            if pack == "catalogue":
                from .catalogue_sync import sync

                await sync(service.store)
                return await send_checkpoint()
            if pack in {"resources", "resources-recovery"}:
                from .review_config import (
                    BATCH_SIZE,
                    RUN_SECONDS,
                    RECOVERY_BATCH_SIZE,
                    RECOVERY_SECONDS,
                )

                recovery = pack == "resources-recovery"
                # One bounded source step; unchanged/held racing never blocks other packs.
                await asyncio.to_thread(service.racing.advance, 1)
                await service.resources.audit(
                    RECOVERY_BATCH_SIZE if recovery else BATCH_SIZE,
                    max_seconds=RECOVERY_SECONDS if recovery else RUN_SECONDS,
                )
                return await send_checkpoint(compresslevel=1)
            for name in (["population", "restaurants"] if pack == "all" else [pack]):
                await refresh(service.store, name)
            return await send_checkpoint()


def main():
    bootstrap()
    from .api import main as serve

    serve()
