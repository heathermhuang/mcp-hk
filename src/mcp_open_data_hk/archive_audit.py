"""Offline Enigma acquisition/inspection. Never imported by the serving app."""

import argparse
import fcntl
import hashlib
import json
import os
import selectors
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from html.parser import HTMLParser
from importlib.resources import files
from pathlib import Path, PurePosixPath, PureWindowsPath
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit

import httpx

GIB = 1024**3
FILE_ID = "1AUpdv6nXd5G46dyUU-ydDL4rEUjbeoz5"
NOTICE = "https://drive.google.com/file/d/1zXq1bwP0jNlZXNelsGobkDG12abzC93-/view"
SOURCE = {
    "fileId": FILE_ID,
    "name": "enigma251227.7z",
    "size": 1721680391,
    "modifiedTime": "2025-12-27T02:51:27.000Z",
    "sourceUrl": f"https://drive.google.com/file/d/{FILE_ID}/view",
    "noticeUrl": NOTICE,
    "licence": "CC-BY; retain the original notice and attribution to David M Webb",
}


class AuditError(Exception):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as out:
        json.dump(value, out, indent=2, ensure_ascii=False)
        out.write("\n")
        out.flush()
        os.fsync(out.fileno())
    temp.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prefix_hash(path, length):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while length:
            block = source.read(min(length, 1024 * 1024))
            if not block:
                raise AuditError(
                    "PARTIAL_CHANGED", "Partial file is shorter than its checkpoint"
                )
            digest.update(block)
            length -= len(block)
    return digest.hexdigest()


def fingerprint(source):
    return hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest()


def preserve_notice(workspace):
    original = files("mcp_open_data_hk").joinpath("webb-site-NOTICE.txt").read_bytes()
    path = workspace / "webb-site-NOTICE.txt"
    if path.exists() and path.read_bytes() != original:
        raise AuditError("NOTICE_CHANGED", "Retained original source notice differs")
    if not path.exists():
        path.write_bytes(original)
    return hashlib.sha256(original).hexdigest()


def disk_check(path, needed=0, reserve=20 * GIB):
    scratch = sum(
        f.stat().st_size
        for f in Path(path).rglob("*")
        if f.is_file() and not f.is_symlink()
    )
    if scratch + needed > 80 * GIB:
        raise AuditError("SCRATCH_LIMIT", "Audit workspace exceeds its 80 GiB bound")
    free = shutil.disk_usage(path).free
    if free - needed < reserve:
        raise AuditError(
            "DISK_CAPACITY", "Required bytes plus free-space reserve unavailable"
        )
    return free


def safe_workspace(path):
    path = Path(path).absolute()
    for parent in [path, *path.parents]:
        if parent.is_symlink():
            raise AuditError(
                "UNSAFE_WORKSPACE", "Workspace ancestors must not be symlinks"
            )
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if any(p.is_symlink() for p in path.iterdir()):
        raise AuditError("UNSAFE_WORKSPACE", "Workspace contains a symlink")
    return path


def receipt(workspace, phase, status, **values):
    item = {"at": now(), "phase": phase, "status": status, **values}
    with (workspace / "receipts.jsonl").open("a", encoding="utf-8") as out:
        out.write(json.dumps(item, ensure_ascii=False) + "\n")
        out.flush()
        os.fsync(out.fileno())


class DownloadForm(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.action = None
        self.fields = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form" and attrs.get("id") == "download-form":
            self.active = True
            self.action = attrs.get("action")
        if tag == "input" and self.active and attrs.get("type") == "hidden":
            self.fields[attrs.get("name")] = attrs.get("value", "")

    def handle_endtag(self, tag):
        if tag == "form":
            self.active = False


def validate_download_url(url, source):
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != "drive.usercontent.google.com"
        or parts.path not in {"/uc", "/download"}
        or parts.username
        or parts.password
        or parts.port not in {None, 443}
        or parse_qs(parts.query).get("id") != [source["fileId"]]
    ):
        raise AuditError(
            "UNSAFE_DOWNLOAD_URL", "Unexpected public download destination"
        )


@contextmanager
def download_stream(client, source, url, headers=None):
    for _ in range(4):
        validate_download_url(url, source)
        with client.stream("GET", url, headers=headers) as response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("location", ""))
                continue
            yield response
            return
    raise AuditError("REDIRECT_LIMIT", "Too many public download redirects")


def resolve_download(client, source):
    url = "https://drive.usercontent.google.com/uc?" + urlencode(
        {"id": source["fileId"], "export": "download"}
    )
    with download_stream(client, source, url) as response:
        response.raise_for_status()
        if "text/html" not in response.headers.get("content-type", ""):
            return url
        chunks = bytearray()
        for block in response.iter_bytes(16384):
            chunks.extend(block)
            if len(chunks) > 262144:
                raise AuditError(
                    "DOWNLOAD_PAGE_TOO_LARGE", "Download page exceeds 256 KiB"
                )
    form = DownloadForm()
    form.feed(chunks.decode("utf-8"))
    if (
        form.action != "https://drive.usercontent.google.com/download"
        or form.fields.get("id") != source["fileId"]
        or set(form.fields) - {"id", "export", "confirm", "uuid"}
        or form.fields.get("export") != "download"
    ):
        raise AuditError(
            "ACCESS_REQUIRED",
            "No recognized public download form; do not bypass access checks",
        )
    result = form.action + "?" + urlencode(form.fields)
    validate_download_url(result, source)
    return result


def acquire(workspace, source, client, reserve=20 * GIB, max_bytes=4 * GIB):
    notice_hash = preserve_notice(workspace)
    size = source["size"]
    if type(size) is not int or not 0 < size <= max_bytes:
        raise AuditError(
            "DOWNLOAD_LIMIT", "Declared archive size exceeds download bound"
        )
    part = workspace / "archive.7z.part"
    final = workspace / "archive.7z"
    state_path = workspace / "acquisition.json"
    identity = fingerprint(source)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if state and state.get("sourceFingerprint") != identity:
        raise AuditError(
            "SOURCE_CHANGED", "Metadata differs from the existing acquisition"
        )
    if final.exists():
        expected = state.get("sha256") or state.get("partialSha256")
        if (
            not expected
            or final.stat().st_size != size
            or (state.get("status") != "verified" and state.get("bytes") != size)
        ):
            raise AuditError(
                "UNVERIFIED_ARCHIVE", "Final archive lacks a matching receipt"
            )
        if sha256(final) != expected:
            raise AuditError("CHECKSUM_MISMATCH", "Acquired archive bytes changed")
        if state.get("status") != "verified" or state.get("bytes") != size:
            state.update(
                status="verified", bytes=size, sha256=expected, verifiedAt=now()
            )
            atomic_json(state_path, state)
            receipt(
                workspace,
                "acquire",
                "verified",
                recoveredFinalRename=True,
                sha256=expected,
                bytes=size,
            )
        if state.get("noticeSha256") != notice_hash:
            state["noticeSha256"] = notice_hash
            atomic_json(state_path, state)
        return final
    offset = part.stat().st_size if part.exists() else 0
    if offset:
        committed = state.get("bytes")
        if type(committed) is not int or not 0 <= committed <= offset:
            raise AuditError("PARTIAL_CHANGED", "No valid partial checkpoint")
        if prefix_hash(part, committed) != state.get("partialSha256"):
            raise AuditError(
                "PARTIAL_CHANGED",
                "Partial bytes do not match the saved resume checkpoint",
            )
        if offset > committed:
            with part.open("r+b") as out:
                out.truncate(committed)
            receipt(
                workspace,
                "acquire",
                "resume",
                discardedUncommittedBytes=offset - committed,
            )
            offset = committed
    if offset > size:
        raise AuditError("DOWNLOAD_LIMIT", "Partial file exceeds declared archive size")
    disk_check(workspace, size - offset, reserve)
    digest = hashlib.sha256()
    if offset:
        with part.open("rb") as old:
            for block in iter(lambda: old.read(1024 * 1024), b""):
                digest.update(block)
    state.update(
        source=source,
        sourceFingerprint=identity,
        bytes=offset,
        status="partial",
        noticeSha256=notice_hash,
    )
    written = offset

    def checkpoint():
        state.update(bytes=written, partialSha256=digest.hexdigest(), updatedAt=now())
        atomic_json(state_path, state)

    checkpoint()
    try:
        if written < size:
            url = resolve_download(client, source)
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            if offset and state.get("etag"):
                headers["If-Range"] = state["etag"]
            with download_stream(client, source, url, headers) as response:
                response.raise_for_status()
                if offset:
                    expected = f"bytes {offset}-{size - 1}/{size}"
                    if (
                        response.status_code != 206
                        or response.headers.get("content-range") != expected
                    ):
                        raise AuditError(
                            "RESUME_REFUSED",
                            "Server did not return the exact remaining byte range",
                        )
                    if (
                        state.get("etag")
                        and response.headers.get("etag") != state["etag"]
                    ):
                        raise AuditError("SOURCE_CHANGED", "Download validator changed")
                elif response.status_code != 200:
                    raise AuditError(
                        "INVALID_DOWNLOAD", "Expected an entire public archive response"
                    )
                if "text/html" in response.headers.get("content-type", ""):
                    raise AuditError(
                        "ACCESS_REQUIRED", "Received a page instead of archive bytes"
                    )
                length = response.headers.get("content-length")
                if length is not None and int(length) != size - offset:
                    raise AuditError(
                        "SIZE_MISMATCH",
                        "Response length disagrees with source metadata",
                    )
                etag = response.headers.get("etag", "")
                if etag and not etag.startswith("W/"):
                    state["etag"] = etag
                checkpoint()
                last_checkpoint = written
                with part.open("ab") as out:
                    for block in response.iter_bytes(1024 * 1024):
                        if written + len(block) > size:
                            raise AuditError(
                                "DOWNLOAD_LIMIT",
                                "Response exceeds declared archive size",
                            )
                        out.write(block)
                        digest.update(block)
                        written += len(block)
                        if written - last_checkpoint >= 32 * 1024 * 1024:
                            disk_check(workspace, reserve=reserve)
                            out.flush()
                            os.fsync(out.fileno())
                            checkpoint()
                            last_checkpoint = written
                    out.flush()
                    os.fsync(out.fileno())
        if written != size:
            raise AuditError("INCOMPLETE_DOWNLOAD", "Archive response was truncated")
        expected_hash = source.get("sha256")
        if expected_hash and digest.hexdigest() != expected_hash:
            raise AuditError(
                "CHECKSUM_MISMATCH", "Archive disagrees with the publisher checksum"
            )
        checkpoint()
        part.replace(final)
        state.update(
            status="verified",
            bytes=written,
            sha256=digest.hexdigest(),
            verifiedAt=now(),
        )
        atomic_json(state_path, state)
        receipt(workspace, "acquire", "verified", bytes=written, sha256=state["sha256"])
        return final
    except BaseException as error:
        checkpoint()
        receipt(
            workspace,
            "acquire",
            "failed",
            code=getattr(error, "code", type(error).__name__),
            bytes=written,
        )
        error.audit_recorded = True
        raise


def member_records(text):
    records = []
    item = {}
    for line in [*text.splitlines(), ""]:
        if " = " in line:
            key, value = line.split(" = ", 1)
            if key in item:
                raise AuditError(
                    "INVALID_MEMBER_LIST", "Duplicate archive metadata key"
                )
            item[key] = value
        elif not line.strip() and item:
            records.append(item)
            item = {}
    return records


def validate_members(records, max_expanded=40 * GIB):
    members, names, total = [], set(), 0
    if not records or len(records) > 10000:
        raise AuditError("MEMBER_LIMIT", "Archive must contain 1..10000 members")
    for item in records:
        name = item.get("Path", "")
        path, windows = PurePosixPath(name), PureWindowsPath(name)
        attributes = item.get("Attributes", "")
        canonical = path.as_posix().casefold()
        mode = attributes.split()[-1] if attributes.split() else ""
        if (
            not name
            or path.is_absolute()
            or windows.drive
            or "\\" in name
            or any(p in {"..", ".", ""} for p in name.rstrip("/").split("/"))
            or any(ord(c) < 32 for c in name)
            or ":" in name
            or canonical in names
            or item.get("Symbolic Link")
            or item.get("Hard Link")
            or (len(mode) >= 10 and mode[0] in "lbcps")
        ):
            raise AuditError("UNSAFE_MEMBER", "Unsafe archive member path/type")
        names.add(canonical)
        directory = item.get("Folder") == "+" or "D" in attributes.split(" ")[0]
        size = int(item.get("Size", "0"))
        if size < 0:
            raise AuditError("INVALID_MEMBER_LIST", "Negative archive member size")
        total += size
        if total > max_expanded:
            raise AuditError("EXPANSION_LIMIT", "Declared expansion exceeds bound")
        if not directory and path.suffix.lower() != ".sql":
            raise AuditError(
                "UNEXPECTED_MEMBER", "Only SQL data files are accepted for this audit"
            )
        members.append({"path": name, "bytes": size, "directory": directory})
    return {"members": members, "declaredExpandedBytes": total}


def inspect_archive(workspace, binary="7zz"):
    archive = workspace / "archive.7z"
    state = json.loads((workspace / "acquisition.json").read_text())
    if state.get("status") != "verified" or sha256(archive) != state.get("sha256"):
        raise AuditError("UNVERIFIED_ARCHIVE", "Verify acquired bytes before listing")
    content, started, process = bytearray(), time.monotonic(), None
    selector = selectors.DefaultSelector()
    try:
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                [binary, "l", "-slt", "-ba", "-sccUTF-8", str(archive)],
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                if time.monotonic() - started > 120:
                    raise AuditError(
                        "INSPECTION_TIMEOUT", "Archive listing exceeded two minutes"
                    )
                if not selector.select(timeout=1):
                    continue
                block = os.read(process.stdout.fileno(), 16384)
                if not block:
                    break
                content.extend(block)
                if len(content) > 2 * 1024 * 1024:
                    raise AuditError("MEMBER_LIMIT", "Archive listing exceeds 2 MiB")
            process.wait(timeout=10)
            if process.returncode:
                raise AuditError("INSPECTION_FAILED", "Native archive listing failed")
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
    report = validate_members(member_records(content.decode("utf-8")))
    report.update(archiveSha256=state["sha256"], inspectedAt=now())
    atomic_json(workspace / "archive-members.json", report)
    receipt(
        workspace,
        "inspect",
        "verified",
        members=len(report["members"]),
        expandedBytes=report["declaredExpandedBytes"],
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["acquire", "inspect", "extract", "restore", "qualify"]
    )
    parser.add_argument("--workspace", required=True)
    parser.add_argument(
        "--source-metadata", help="Fresh, verified source metadata JSON"
    )
    parser.add_argument("--member", help="Exact SQL member from the accepted inventory")
    parser.add_argument(
        "--container", help="Disconnected, bounded audit MySQL container"
    )
    parser.add_argument(
        "--database", help="New audit_ database name; never an existing database"
    )
    args = parser.parse_args()
    os.umask(0o077)
    workspace = safe_workspace(args.workspace)
    with (workspace / ".audit.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "busy", "code": "AUDIT_BUSY"}))
            raise SystemExit(2) from None
        try:
            if args.command == "acquire":
                source = (
                    json.loads(Path(args.source_metadata).read_text())
                    if args.source_metadata
                    else SOURCE
                )
                with httpx.Client(
                    trust_env=False, timeout=60, follow_redirects=False
                ) as client:
                    acquire(workspace, source, client)
                print(json.dumps({"status": "verified", "phase": "acquire"}))
            elif args.command == "inspect":
                print(json.dumps(inspect_archive(workspace)))
            elif args.command == "extract":
                from .archive_extract import extract_member

                if not args.member:
                    raise AuditError(
                        "MEMBER_REQUIRED", "Provide the exact validated SQL member"
                    )
                print(json.dumps(extract_member(workspace, args.member)))
            else:
                from .archive_restore import restore
                from .archive_qualify import qualify

                if not args.container or not args.database:
                    raise AuditError(
                        "DATABASE_REQUIRED",
                        "Provide the isolated audit container and a new database name",
                    )
                operation = restore if args.command == "restore" else qualify
                result = operation(workspace, args.container, args.database)
                print(
                    json.dumps({"status": result["status"], "database": args.database})
                )
        except Exception as error:
            code = getattr(error, "code", type(error).__name__)
            if not getattr(error, "audit_recorded", False):
                receipt(workspace, args.command, "failed", code=code)
            print(json.dumps({"status": "failed", "code": code}))
            raise SystemExit(1) from error


if __name__ == "__main__":
    main()
