"""Checksummed local backup/restore through a fixed operator-owned PG container."""

import hashlib
import re
import subprocess
from pathlib import Path

from .schema import schema_name


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def backup(container, database, version, destination):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", container) or not re.fullmatch(
        r"[A-Za-z0-9_]+", database
    ):
        raise ValueError("Use explicit local container and database names")
    schema_name(version)
    destination = Path(destination)
    # Exclusive create retains earlier successful/failed artifacts. No caller SQL.
    with destination.open("xb") as output:
        subprocess.run(
            [
                "docker",
                "exec",
                container,
                "pg_dump",
                "-U",
                "postgres",
                "-d",
                database,
                "-Fc",
                "--no-owner",
                "--no-acl",
                "-n",
                "curated",
                "-n",
                "curated_*",
            ],
            stdout=output,
            timeout=900,
            check=True,
        )
    return {
        "path": str(destination),
        "bytes": destination.stat().st_size,
        "sha256": file_hash(destination),
        "version": version,
    }


def restore(container, database, path, expected_sha256):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", container) or not re.fullmatch(
        r"[A-Za-z0-9_]+", database
    ):
        raise ValueError("Use explicit local container and database names")
    path = Path(path)
    if path.is_symlink() or file_hash(path) != expected_sha256:
        raise ValueError("Backup checksum differs before restore")
    # pg_restore has no --clean: only a new, isolated target may accept this dump.
    with path.open("rb") as source:
        subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container,
                "pg_restore",
                "-U",
                "postgres",
                "-d",
                database,
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-acl",
            ],
            stdin=source,
            timeout=900,
            check=True,
        )
