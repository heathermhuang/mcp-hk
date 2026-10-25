"""Audited operator entrypoint. No live provider transport is installed."""

import argparse
import json
import os
from pathlib import Path

from ..read import Reader
from .read import HkexReader
from .recovery import backup, build_export, restore
from .store import Store, accept_restore, activate_policy, grant_reader, migrate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="operation", required=True)
    subs.add_parser("migrate")
    p = subs.add_parser("grant-reader")
    p.add_argument("role")
    p = subs.add_parser("activate-policy")
    p.add_argument("file", type=Path)
    p.add_argument("--reviewed-sha256", required=True)
    subs.add_parser("status")
    p = subs.add_parser("backup")
    p.add_argument("destination", type=Path)
    p = subs.add_parser("restore")
    p.add_argument("archive", type=Path)
    p.add_argument("--sha256", required=True)
    p = subs.add_parser("qualify-restore")
    p.add_argument("version")
    p.add_argument("--sha256", required=True)
    p = subs.add_parser("publish")
    p.add_argument("version")
    p.add_argument(
        "--expected-version",
        required=True,
        help="Exact accepted version; NONE only if no pointer",
    )
    p = subs.add_parser("export")
    p.add_argument("version")
    p.add_argument("destination", type=Path)
    args = parser.parse_args()
    dsn = os.environ["HKEX_DSN"]
    if args.operation == "migrate":
        migrate(dsn)
        result = {"schema": "hkex"}
    elif args.operation == "grant-reader":
        grant_reader(dsn, args.role)
        result = {"granted": "source SELECT only"}
    elif args.operation == "activate-policy":
        result = {
            "policyHash": activate_policy(
                dsn, json.loads(args.file.read_text()), args.reviewed_sha256
            )
        }
    elif args.operation == "backup":
        result = backup(dsn, args.destination)
    elif args.operation == "restore":
        result = restore(dsn, args.archive, args.sha256)
    elif args.operation == "qualify-restore":
        result = accept_restore(
            dsn, os.environ["HKEX_RESTORED_DSN"], args.version, args.sha256
        )
    elif args.operation == "publish":
        result = {
            "version": Store(dsn, os.environ["HKEX_POLICY_SHA256"]).publish(
                args.version,
                None if args.expected_version == "NONE" else args.expected_version,
            )
        }
    else:
        reader = HkexReader(Reader(dsn, os.environ["CURATED_CURSOR_SECRET"].encode()))
        result = (
            reader.status()
            if args.operation == "status"
            else build_export(reader, args.version, args.destination)
        )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
