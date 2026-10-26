"""Scoped uploader preparation; requires separately approved host-only capability.

No R2/operator OAuth or gateway credential is accepted. Uploads are immutable;
source metadata and dump are independently retrieved before manifest publication.
"""

import hashlib
from contextlib import ExitStack
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
import uuid

import httpx

from .official import encoded

ORIGIN = "https://mcp.hk/__company-backup/"
MAX_DUMP = 256 * 1024 * 1024
PART_BYTES = 64 * 1024 * 1024


def checksum(path):
    h = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def upload(
    config_path, dump_path, source_path, client=None, job_id=None, retrieved_dump=None
):
    config_path, dump_path, source_path = map(
        Path, (config_path, dump_path, source_path)
    )
    if config_path.stat().st_mode & 0o077:
        raise ValueError("Uploader configuration must be owner-only")
    config = json.loads(config_path.read_text())
    if (
        set(config) != {"origin", "token"}
        or config["origin"] != ORIGIN
        or not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", config["token"])
    ):
        raise ValueError(
            "Only the approved fixed-origin uploader capability is accepted"
        )
    if (
        not 0 < dump_path.stat().st_size <= MAX_DUMP
        or not 0 < source_path.stat().st_size <= 1024 * 1024
    ):
        raise ValueError("Offsite artifact bound exceeded")
    stamp = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + "-"
        + uuid.uuid4().hex[:8]
    )
    owned = client is None
    client = client or httpx.Client(
        timeout=120, follow_redirects=False, trust_env=False
    )
    headers = {"Authorization": "Bearer " + config["token"]}
    artifacts = {}

    def put_and_verify(name, path, offset=0, size=None, destination=None):
        size = path.stat().st_size if size is None else size
        h = hashlib.sha256()
        with path.open("rb") as source:
            source.seek(offset)
            remaining = size
            while remaining:
                block = source.read(min(65536, remaining))
                if not block:
                    raise RuntimeError("OFFSITE_SOURCE_TRUNCATED")
                h.update(block)
                remaining -= len(block)
        sha = h.hexdigest()
        with path.open("rb") as source:
            source.seek(offset)

            def chunks():
                remaining = size
                while remaining:
                    block = source.read(min(65536, remaining))
                    if not block:
                        raise RuntimeError("OFFSITE_SOURCE_TRUNCATED")
                    remaining -= len(block)
                    yield block

            response = client.put(
                ORIGIN + stamp + "/" + name,
                headers=dict(
                    headers, **{"content-length": str(size), "x-object-sha256": sha}
                ),
                content=chunks(),
            )
        if response.status_code != 200:
            raise RuntimeError("OFFSITE_UPLOAD_HTTP_" + str(response.status_code))
        h, total = hashlib.sha256(), 0
        with client.stream(
            "GET", ORIGIN + stamp + "/" + name, headers=headers
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(
                    "OFFSITE_RETRIEVAL_HTTP_" + str(response.status_code)
                )
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > size:
                    raise RuntimeError("OFFSITE_SIZE_MISMATCH")
                h.update(chunk)
                if destination:
                    destination.write(chunk)
        if total != size or h.hexdigest() != sha:
            raise RuntimeError("OFFSITE_CHECKSUM_MISMATCH")
        return {"sha256": sha, "bytes": size}

    try:
        # Keep every HTTP request below the existing zone's 100 MB limit.
        # The independent downloaded file is reconstructed and checked in full.
        with ExitStack() as stack:
            destination = None
            if retrieved_dump:
                destination = stack.enter_context(
                    os.fdopen(
                        os.open(
                            retrieved_dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                        ),
                        "wb",
                    )
                )
            size = dump_path.stat().st_size
            if size <= PART_BYTES:
                artifacts["official.dump"] = put_and_verify(
                    "official.dump", dump_path, destination=destination
                )
            else:
                parts = []
                for index, offset in enumerate(range(0, size, PART_BYTES)):
                    name = f"official.part-{index:03d}"
                    part = put_and_verify(
                        name,
                        dump_path,
                        offset,
                        min(PART_BYTES, size - offset),
                        destination,
                    )
                    parts.append(dict(name=name, **part))
                artifacts["official.dump"] = {
                    "sha256": checksum(dump_path),
                    "bytes": size,
                    "parts": parts,
                }
        if (
            retrieved_dump
            and checksum(Path(retrieved_dump)) != artifacts["official.dump"]["sha256"]
        ):
            raise RuntimeError("OFFSITE_REASSEMBLED_CHECKSUM_MISMATCH")
        artifacts["source.json"] = put_and_verify("source.json", source_path)
        # A manifest is the immutable recovery pointer. It is written only after
        # the two dependencies round-trip. No arbitrary prefix/list/delete exists.
        import tempfile

        manifest = {
            "prefix": "curated/official/daily/" + stamp,
            "artifacts": dict(artifacts),
            "verifiedAt": datetime.now(timezone.utc).isoformat(),
            "credentialRoute": "dedicated_prefix_capability",
            "jobId": job_id,
            "restoreObserved": False,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_bytes(encoded(manifest))
            artifacts["manifest.json"] = put_and_verify("manifest.json", path)
        return dict(manifest, artifacts=artifacts)
    finally:
        if owned:
            client.close()


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--dump", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--job-id")
    parser.add_argument("--retrieved-dump")
    args = parser.parse_args()
    try:
        receipt = upload(
            args.config,
            args.dump,
            args.source,
            job_id=args.job_id,
            retrieved_dump=args.retrieved_dump,
        )
        print(json.dumps(receipt))
    except Exception as exc:
        # Only our fixed status codes survive; HTTP/OS details remain private.
        code = str(exc) if isinstance(exc, RuntimeError) else ""
        if not re.fullmatch(r"OFFSITE_[A-Z0-9_]{1,70}", code):
            code = "OFFSITE_UPLOAD_OR_VERIFICATION_FAILURE"
        # HTTP/OS errors can contain credentials or file/connection details.
        print(
            json.dumps(
                {
                    "status": "offsite_failed",
                    "errorCode": code,
                }
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
