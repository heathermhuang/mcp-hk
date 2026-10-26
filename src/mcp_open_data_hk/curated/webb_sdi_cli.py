"""Offline Webb archive operations. Credentials are environment-only, never argv."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "extract",
            "migrate",
            "stage",
            "grant-reader",
            "qualify-restore",
            "publish",
            "fingerprint",
        ],
    )
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version")
    parser.add_argument(
        "--expected-version",
        help="Previously accepted version; omit only for first publication",
    )
    parser.add_argument("--backup-sha256")
    parser.add_argument("--role")
    args = parser.parse_args()
    from . import webb_sdi_store as store

    if args.command == "extract":
        from .webb_sdi_source import extract

        if not args.workspace or not args.output:
            parser.error(
                "extract requires the audited workspace and new output directory"
            )
        result = extract(args.workspace, args.output)
    else:
        dsn = os.environ["CURATED_DSN"]
        if args.command == "migrate":
            store.migrate(dsn)
            result = {"schema": "webb_sdi", "migrated": True}
        elif args.command == "stage":
            if not args.workspace:
                parser.error("stage requires the extracted projection workspace")
            result = store.stage(dsn, args.workspace)
        elif args.command == "grant-reader":
            if not args.role:
                parser.error("grant-reader requires a dedicated SELECT-only role")
            store.grant_reader(dsn, args.role)
            result = {"readerRole": args.role}
        elif args.command == "qualify-restore":
            if not args.version or not args.backup_sha256:
                parser.error("qualify-restore requires version and backup-sha256")
            result = store.qualify_restore(
                dsn, os.environ["CURATED_RESTORE_DSN"], args.version, args.backup_sha256
            )
        elif args.command == "publish":
            if not args.version:
                parser.error("publish requires an exact restore-qualified version")
            result = {
                "publishedVersion": store.publish(
                    dsn, args.version, args.expected_version
                )
            }
        else:
            result = store.snapshot(dsn)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
