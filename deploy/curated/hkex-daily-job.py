#!/usr/bin/env python3
"""Ordinary host job: source collection, offsite download/restore, then publication.

Source credentials and the prefix-only upload capability are owner-only files.
No administrator credential or Docker socket is exposed to the job image.
"""

import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone

CONFIG = Path("/etc/mcp-hk-curated/hkex-daily-uploader.json")
ENV = "/etc/mcp-hk-curated/hkex-daily.env"
ROOT = Path("/srv/mcp-hk-curated/hkex-daily")
MAX_DUMP = 64 * 1024**2
TABLES = (
    "control",
    "versions",
    "reports",
    "records",
    "version_reports",
    "runs",
    "requests",
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise RuntimeError("OFFSITE_REDIRECT_REJECTED")


def execute(argv, **kwargs):
    return subprocess.run(
        argv, check=True, timeout=kwargs.pop("timeout", 180), **kwargs
    )


def runner(image, *args, expected_failure=False):
    command = [
        "docker",
        "run",
        "--rm",
        "--read-only",
        "--memory",
        "512m",
        "--cpus",
        "1",
        "--network",
        "curated_default",
        "--env-file",
        ENV,
        "--entrypoint",
        "python",
        image,
        "-m",
        "mcp_open_data_hk.curated.hkex_daily.runner",
        *args,
    ]
    p = subprocess.run(command, capture_output=True, text=True, timeout=660)
    try:
        r = json.loads(p.stdout)
    except ValueError:
        raise RuntimeError("SOURCE_JOB_NO_VALID_RECEIPT") from None
    if p.returncode and not (expected_failure and r.get("state") == "failed"):
        raise RuntimeError("SOURCE_JOB_REJECTED")
    return r


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def source_state(image, version=None):
    return runner(image, "state", *(["--version", version] if version else []))


def source_backup(image, token, stage, version):
    prune_own_files()
    stamp = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + secrets.token_hex(4)
    )
    backups = ROOT / "backups"
    occupied = (
        sum(
            p.stat().st_size
            for p in backups.rglob("*")
            if p.is_file() and not p.is_symlink()
        )
        if backups.exists()
        else 0
    )
    if occupied + 2 * MAX_DUMP > 512 * 1024**2:
        raise RuntimeError("LOCAL_SOURCE_BACKUP_RESERVE_EXHAUSTED")
    directory = ROOT / "backups" / stamp
    directory.mkdir(parents=True, mode=0o700)
    archive, download = directory / "source.dump", directory / "offsite.dump"
    with archive.open("wb") as f:
        execute(
            [
                "docker",
                "exec",
                "curated-postgres-1",
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                "curated",
                "-Fc",
                "-n",
                "hkex_daily",
                "--no-owner",
                "--no-acl",
            ],
            stdout=f,
        )
    n = archive.stat().st_size
    if not 0 < n <= MAX_DUMP:
        raise RuntimeError("SOURCE_DUMP_SIZE_LIMIT")
    sha = file_sha(archive)
    opener = urllib.request.build_opener(NoRedirect)
    base = "https://mcp.hk/__hkex-daily-backup/"

    def request(path, method="GET", body=None, length=None, checksum=None):
        headers = {
            "Authorization": "Bearer " + token,
            "User-Agent": "mcp.hk-hkex-daily-recovery",
            "Content-Type": "application/octet-stream",
        }
        if length is not None:
            headers["Content-Length"] = str(length)
        if checksum:
            headers["x-object-sha256"] = checksum
        req = urllib.request.Request(
            base + path, method=method, headers=headers, data=body
        )
        return opener.open(req, timeout=45)

    with archive.open("rb") as f:
        with request(stamp + "/summary.dump", "PUT", f, n, sha) as r:
            receipt = json.load(r)
    if receipt.get("sha256") != sha or receipt.get("bytes") != n:
        raise RuntimeError("OFFSITE_UPLOAD_NOT_VERIFIED")
    with request(stamp + "/summary.dump") as r, download.open("wb") as f:
        if r.headers.get("x-object-sha256") != sha:
            raise RuntimeError("OFFSITE_HEADER_DIFFERS")
        count = 0
        for block in iter(lambda: r.read(1024 * 1024), b""):
            count += len(block)
            if count > n:
                raise RuntimeError("OFFSITE_DOWNLOAD_OVERFLOW")
            f.write(block)
    if download.stat().st_size != n or file_sha(download) != sha:
        raise RuntimeError("OFFSITE_DOWNLOAD_CHECKSUM_DIFFERS")
    database = "hkex_daily_restore_" + stamp.lower().replace("-", "_")
    created = False
    try:
        execute(
            [
                "docker",
                "exec",
                "curated-postgres-1",
                "createdb",
                "-U",
                "postgres",
                database,
            ]
        )
        created = True
        with download.open("rb") as f:
            execute(
                [
                    "docker",
                    "exec",
                    "-i",
                    "curated-postgres-1",
                    "pg_restore",
                    "-U",
                    "postgres",
                    "-d",
                    database,
                    "--no-owner",
                    "--no-acl",
                    "--single-transaction",
                    "--exit-on-error",
                ],
                stdin=f,
            )
        # This role owns only this source. The temporary database is newly
        # created by this invocation; no shared/live schema is restored over.
        sql = "ALTER SCHEMA hkex_daily OWNER TO hkex_daily_writer;\n" + "".join(
            "ALTER TABLE hkex_daily." + t + " OWNER TO hkex_daily_writer;\n"
            for t in TABLES
        )
        execute(
            [
                "docker",
                "exec",
                "-i",
                "curated-postgres-1",
                "psql",
                "-U",
                "postgres",
                "-d",
                database,
                "-v",
                "ON_ERROR_STOP=1",
            ],
            input=sql.encode(),
            stdout=subprocess.DEVNULL,
        )
        if stage == "candidate":
            proof = runner(
                image,
                "qualify",
                "--version",
                version,
                "--sha256",
                sha,
                "--restore-database",
                database,
            )
            fingerprints = proof["allTables"]
        else:
            fingerprints = runner(image, "fingerprint")
            if fingerprints != runner(
                image, "fingerprint", "--restore-database", database
            ):
                raise RuntimeError("ACCEPTED_RESTORE_CONTENT_DIFFERS")
        state = source_state(image, version)
        manifest = {
            "source": "hkex_daily_summary",
            "stamp": stamp,
            "stage": stage,
            "version": version,
            "dump": {"bytes": n, "sha256": sha},
            "restoreVerified": True,
            "allTables": fingerprints,
            "publicationRevision": (
                state["control"]["accepted_revision"] if stage == "accepted" else 0
            ),
        }
        data = (
            json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        manifest_sha = hashlib.sha256(data).hexdigest()
        with request(
            stamp + "/manifest.json", "PUT", data, len(data), manifest_sha
        ) as r:
            saved = json.load(r)
        if not saved.get("stored") or saved.get("sha256") != manifest_sha:
            raise RuntimeError("OFFSITE_MANIFEST_NOT_CONFIRMED")
        if stage == "accepted":
            with request("latest.json") as r:
                latest = json.load(r)
            if (
                latest.get("stamp") != stamp
                or latest.get("version") != version
                or latest.get("manifestSha256") != manifest_sha
            ):
                raise RuntimeError("OFFSITE_RECOVERY_POINTER_NOT_CONFIRMED")
            manifest.update(
                verifiedAt=datetime.now(timezone.utc).isoformat(),
                manifestSha256=manifest_sha,
            )
            temporary = ROOT / "last-offsite.pending.json"
            temporary.write_text(json.dumps(manifest, indent=2) + "\n")
            os.replace(temporary, ROOT / "last-offsite.json")
        (directory / "receipt.json").write_text(json.dumps(manifest, indent=2) + "\n")
        return manifest
    finally:
        if created:
            execute(
                [
                    "docker",
                    "exec",
                    "curated-postgres-1",
                    "dropdb",
                    "-U",
                    "postgres",
                    database,
                ]
            )


def prune_own_files():
    # Keep a small local recovery/debug set. R2 retains immutable copies 30 days.
    # Never traverse symlinks or delete an unknown/partial directory.
    root = ROOT / "backups"
    if not root.exists():
        return
    completed = []
    for p in root.iterdir():
        if (
            p.is_symlink()
            or not p.is_dir()
            or not re.fullmatch(r"\d{8}T\d{6}Z-[a-f0-9]{8}", p.name)
        ):
            continue
        if (p / "receipt.json").is_file():
            completed.append(p)
    for p in sorted(completed, key=lambda x: x.name)[:-3]:
        files = list(p.iterdir())
        if any(
            x.is_symlink()
            or not x.is_file()
            or x.name not in {"source.dump", "offsite.dump", "receipt.json"}
            for x in files
        ):
            continue
        for x in files:
            x.unlink()
        p.rmdir()


def main():
    os.umask(0o077)
    if CONFIG.is_symlink() or CONFIG.stat().st_mode & 0o077:
        raise RuntimeError("PRIVATE_SOURCE_CONFIG_REQUIRED")
    config = json.loads(CONFIG.read_text())
    image = config.get("image", "")
    token = config.get("token", "")
    if (
        not re.fullmatch(r"mcp-hk-curated:[a-f0-9]{40}", image)
        or not isinstance(token, str)
        or len(token) < 32
    ):
        raise RuntimeError("SOURCE_CONFIG_INVALID")
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Timer evidence is recorded separately from an ordinary operator start.
    trigger = subprocess.check_output(
        [
            "systemctl",
            "show",
            "mcp-hk-hkex-daily.timer",
            "--property=LastTriggerUSecMonotonic",
            "--value",
        ],
        text=True,
    ).strip()
    uptime = int(float(Path("/proc/uptime").read_text().split()[0]) * 1e6)
    provenance = (
        "timer"
        if trigger.isdigit()
        and 0 < int(trigger) <= uptime
        and uptime - int(trigger) < 60_000_000
        else "manual"
    )
    collected = runner(
        image,
        "collect",
        "--provenance",
        provenance,
        "--scheduled-for",
        datetime.now(timezone.utc).isoformat(),
        expected_failure=True,
    )
    version = collected.get("version")
    if collected.get("state") in {"staged", "pending_recovery"}:
        state = source_state(image, version)
        if state["version"]["state"] not in {"staged", "qualified"}:
            raise RuntimeError("SOURCE_CANDIDATE_STATE_DIFFERS")
        source_backup(image, token, "candidate", version)
        runner(image, "publish", "--version", version)
        source_backup(image, token, "accepted", version)
        outcome = "published"
    else:
        state = source_state(image)
        version = state["control"]["accepted_version"]
        outcome = collected["state"]
        previous = (
            json.loads((ROOT / "last-offsite.json").read_text())
            if (ROOT / "last-offsite.json").exists()
            else {}
        )
        if version and (
            previous.get("version") != version
            or previous.get("verifiedAt", "")[:10]
            != datetime.now(timezone.utc).date().isoformat()
        ):
            source_backup(image, token, "accepted", version)
    prune_own_files()
    print(
        json.dumps(
            {
                "state": outcome,
                "run": collected.get("run"),
                "code": collected.get("code"),
                "version": version,
                "provenance": provenance,
                "offsiteLastVerified": (
                    json.loads((ROOT / "last-offsite.json").read_text()).get(
                        "verifiedAt"
                    )
                    if (ROOT / "last-offsite.json").exists()
                    else None
                ),
            }
        )
    )
    if collected.get("state") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    try:
        main()
    except (
        RuntimeError,
        subprocess.SubprocessError,
        urllib.error.URLError,
        ValueError,
        OSError,
    ):
        # Deliberately omit arguments, remote bodies, URLs and credential files.
        print(
            json.dumps(
                {"state": "not_confirmed", "code": "HKEX_DAILY_JOB_OR_RECOVERY_FAILED"}
            )
        )
        raise SystemExit(1)
