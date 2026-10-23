"""Extract verified data members through stdout, never archive-controlled paths."""

import hashlib
import json
import os
import selectors
import subprocess
import tempfile
import time

from .archive_audit import AuditError, GIB, atomic_json, disk_check, now, receipt


def extract_member(workspace, name, binary="7zz", reserve=20 * GIB, max_seconds=1800):
    inventory = json.loads((workspace / "archive-members.json").read_text())
    from .archive_audit import sha256

    if sha256(workspace / "archive.7z") != inventory["archiveSha256"]:
        raise AuditError("CHECKSUM_MISMATCH", "Archive changed after member inspection")
    member = next((m for m in inventory["members"] if m["path"] == name), None)
    if member is None or member["directory"]:
        raise AuditError("UNLISTED_MEMBER", "Choose a previously validated SQL member")
    # Destinations are our opaque keys, not names/paths supplied by the archive.
    key = hashlib.sha256(name.encode()).hexdigest()[:24]
    output = workspace / f"member-{key}.sql"
    proof = workspace / f"member-{key}.json"
    if output.exists():
        if not proof.exists():
            raise AuditError(
                "UNVERIFIED_EXTRACTION", "Existing extraction lacks its receipt"
            )
        accepted = json.loads(proof.read_text())
        if (
            accepted.get("archiveSha256") != inventory["archiveSha256"]
            or accepted.get("sha256") != sha256(output)
            or output.stat().st_size != member["bytes"]
        ):
            raise AuditError("CHECKSUM_MISMATCH", "Existing extraction changed")
        return accepted
    disk_check(workspace, member["bytes"], reserve)
    fd, attempt = tempfile.mkstemp(
        prefix=f"member-{key}-", suffix=".sql.part", dir=workspace
    )
    os.close(fd)
    part = workspace / os.path.basename(attempt)
    started, size, peak_rss, digest = time.monotonic(), 0, 0, hashlib.sha256()
    process = None
    try:
        with tempfile.TemporaryFile() as errors, part.open("wb") as target:
            process = subprocess.Popen(
                [
                    binary,
                    "x",
                    "-so",
                    "-spd",
                    "-mmt=2",
                    str(workspace / "archive.7z"),
                    "--",
                    name,
                ],
                stdout=subprocess.PIPE,
                stderr=errors,
                start_new_session=True,
            )
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            last_check = -2
            while True:
                elapsed = time.monotonic() - started
                if elapsed > max_seconds:
                    raise AuditError(
                        "EXTRACTION_TIMEOUT", "Extraction elapsed-time bound reached"
                    )
                if elapsed - last_check >= 2:
                    disk_check(workspace, reserve=reserve)
                    rss = subprocess.run(
                        ["ps", "-o", "rss=", "-p", str(process.pid)],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )
                    peak_rss = max(peak_rss, int(rss.stdout.strip() or "0") * 1024)
                    if peak_rss > 8 * GIB:
                        raise AuditError(
                            "MEMORY_LIMIT", "Extractor exceeds 8 GiB resident memory"
                        )
                    if errors.tell() > 2 * 1024 * 1024:
                        raise AuditError(
                            "EXTRACTION_ERROR_LIMIT",
                            "Extractor diagnostic bound reached",
                        )
                    last_check = elapsed
                if not selector.select(timeout=1):
                    continue
                block = os.read(process.stdout.fileno(), 1024 * 1024)
                if not block:
                    break
                if size + len(block) > member["bytes"]:
                    raise AuditError(
                        "EXPANSION_LIMIT", "Extracted bytes exceed declared member size"
                    )
                target.write(block)
                digest.update(block)
                size += len(block)
            selector.close()
            process.wait(timeout=10)
            if process.returncode or size != member["bytes"]:
                raise AuditError(
                    "EXTRACTION_FAILED",
                    "Extractor integrity check or byte count failed",
                )
            target.flush()
            os.fsync(target.fileno())
        part.replace(output)
        accepted = {
            "member": name,
            "path": output.name,
            "bytes": size,
            "sha256": digest.hexdigest(),
            "archiveSha256": inventory["archiveSha256"],
            "elapsedSeconds": round(time.monotonic() - started, 3),
            "extractorPeakRssBytes": peak_rss,
            "verifiedAt": now(),
        }
        atomic_json(proof, accepted)
        receipt(workspace, "extract", "verified", **accepted)
        return accepted
    except BaseException as error:
        receipt(
            workspace,
            "extract",
            "failed",
            member=name,
            partial=part.name,
            bytes=size,
            code=getattr(error, "code", type(error).__name__),
        )
        error.audit_recorded = True
        raise
    finally:
        if process is not None:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
            if process.stdout:
                process.stdout.close()
