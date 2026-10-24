"""Prune only expired, verified local offsite duplicates; retain latest two."""

import argparse
import json
from pathlib import Path
import re
import time

import httpx

from .official_offsite import ORIGIN, checksum


def prune(folder, config_path, client=None, now=None):
    folder = Path(folder)
    config_path = Path(config_path)
    if config_path.stat().st_mode & 0o077:
        raise ValueError("Owner-only uploader configuration required")
    config = json.loads(config_path.read_text())
    if config.get("origin") != ORIGIN:
        raise ValueError("Fixed uploader origin required")
    now = time.time() if now is None else now
    qualified = []
    for path in folder.glob("retrieved-*.dump"):
        match = re.fullmatch(r"retrieved-([a-f0-9]{32})\.dump", path.name)
        if not match or path.is_symlink() or not path.is_file():
            continue
        job = match[1]
        try:
            proof = json.loads((folder / ("restore-" + job + ".json")).read_text())
            receipt = json.loads((folder / ("receipt-" + job + ".json")).read_text())
            artifact = receipt["artifacts"]["official.dump"]
            if (
                not proof.get("freshOffsiteRestoreVerified")
                or proof.get("backupSha256") != artifact["sha256"]
                or proof.get("prefix") != receipt["prefix"]
                or not re.fullmatch(
                    r"curated/official/daily/\d{8}T\d{6}Z-[a-f0-9]{8}",
                    receipt["prefix"],
                )
            ):
                continue
        except (ValueError, OSError, KeyError, TypeError):
            continue
        qualified.append((path.stat().st_mtime, path, receipt, artifact))
    qualified.sort(key=lambda row: row[0], reverse=True)
    candidates = [r for r in qualified[2:] if r[0] < now - 30 * 86400][:4]
    owned = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=False, trust_env=False)
    removed = 0
    try:
        for _, path, receipt, artifact in candidates:
            suffix = (
                receipt["prefix"].removeprefix("curated/official/daily/")
                + "/official.dump"
            )
            response = client.head(
                ORIGIN + suffix, headers={"Authorization": "Bearer " + config["token"]}
            )
            if (
                response.status_code != 200
                or response.headers.get("x-object-sha256") != artifact["sha256"]
                or response.headers.get("content-length") != str(artifact["bytes"])
            ):
                continue
            if (
                path.stat().st_size != artifact["bytes"]
                or checksum(path) != artifact["sha256"]
            ):
                continue
            path.unlink()
            removed += 1
    finally:
        if owned:
            client.close()
    return {
        "expiredLocalDuplicatesPruned": removed,
        "latestTwoQualifiedCopiesRetained": True,
        "offsiteObjectsDeleted": 0,
        "unverifiedEvidenceDeleted": 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True)
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(prune(args.folder, args.config)))
    except Exception:
        print(
            json.dumps(
                {
                    "expiredLocalDuplicatesPruned": 0,
                    "retentionStatus": "held_preserve_all",
                }
            )
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
