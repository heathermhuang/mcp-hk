"""Offline/local model operations. DSNs come from the environment, not argv/logs."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "backup",
            "restore",
            "stage",
            "inspect",
            "accept-restore",
            "publish",
            "grant-reader",
            "search",
            "get",
        ],
    )
    parser.add_argument("--version")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--container")
    parser.add_argument("--database", default="audit_enigma_checked")
    parser.add_argument("--backup-sha256")
    parser.add_argument("--artifact", type=Path)
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--role")
    parser.add_argument("--name")
    parser.add_argument("--entity-id", type=int)
    args = parser.parse_args()
    from .build import stage
    from .qualify import accept_restore, grant_reader, inspect, publish

    dsn = os.environ.get("CURATED_DSN")
    if args.command in {"backup", "restore"}:
        from .backup import backup, restore

        if not args.container or not args.artifact:
            parser.error("backup/restore require container and artifact")
        if args.command == "backup":
            result = backup(args.container, args.database, args.version, args.artifact)
        else:
            restore(args.container, args.database, args.artifact, args.backup_sha256)
            result = {"restoredBackupSha256": args.backup_sha256}
    elif args.command == "stage":
        from .source import Source

        if not args.workspace or not args.container or not args.version:
            parser.error("stage requires workspace, container and version")
        result = stage(
            dsn, Source(args.workspace, args.container, args.database), args.version
        )
    elif args.command == "inspect":
        result = inspect(dsn, args.version)
    elif args.command == "accept-restore":
        if args.source_receipt:
            from .qualify import accept_restore_receipt

            if not args.artifact:
                parser.error(
                    "Receipt-based restore qualification requires the backup artifact"
                )
            result = accept_restore_receipt(
                dsn, json.loads(args.source_receipt.read_text()), args.artifact
            )
        else:
            result = accept_restore(
                dsn, os.environ["CURATED_RESTORE_DSN"], args.version, args.backup_sha256
            )
    elif args.command == "publish":
        publish(dsn, args.version)
        result = {"publishedLocalVersion": args.version}
    elif args.command == "grant-reader":
        grant_reader(dsn, args.role)
        result = {"readerRole": args.role}
    else:
        from .read import Reader

        reader = Reader(dsn, os.environ["CURATED_CURSOR_SECRET"].encode())
        result = (
            reader.search(name=args.name)
            if args.command == "search"
            else reader.get(args.entity_id)
        )
    print(json.dumps(result, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
