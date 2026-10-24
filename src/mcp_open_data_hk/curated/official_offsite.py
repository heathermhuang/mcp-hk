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

    def put_and_verify(name, path):
        sha, size = checksum(path), path.stat().st_size
        with path.open("rb") as source:
            response = client.put(
                ORIGIN + stamp + "/" + name,
                headers=dict(
                    headers, **{"content-length": str(size), "x-object-sha256": sha}
                ),
                content=source,
            )
        if response.status_code != 200:
            raise RuntimeError("OFFSITE_UPLOAD_FAILED")
        h, total = hashlib.sha256(), 0
        with ExitStack() as stack:
            destination = None
            if name == "official.dump" and retrieved_dump:
                destination = stack.enter_context(
                    os.fdopen(
                        os.open(
                            retrieved_dump, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                        ),
                        "wb",
                    )
                )
            with client.stream(
                "GET", ORIGIN + stamp + "/" + name, headers=headers
            ) as response:
                if response.status_code != 200:
                    raise RuntimeError("OFFSITE_RETRIEVAL_FAILED")
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > size:
                        raise RuntimeError("OFFSITE_SIZE_MISMATCH")
                    h.update(chunk)
                    if destination:
                        destination.write(chunk)
        if total != size or h.hexdigest() != sha:
            raise RuntimeError("OFFSITE_CHECKSUM_MISMATCH")
        artifacts[name] = {"sha256": sha, "bytes": size}

    try:
        put_and_verify("official.dump", dump_path)
        put_and_verify("source.json", source_path)
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
            put_and_verify("manifest.json", path)
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
    except Exception:
        # HTTP/OS errors can contain credentials or file/connection details.
        print(
            json.dumps(
                {
                    "status": "offsite_failed",
                    "errorCode": "OFFSITE_UPLOAD_OR_VERIFICATION_FAILURE",
                }
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
