"""Operator source setup, bounded collection and restore-qualified publication."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from .contracts import Rejected
from .public_register import MAX_BODY, Collector, parse_page


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    replay = commands.add_parser(
        "parse", help="Parse saved corporate licence HTML without network or a database"
    )
    replay.add_argument("--html", required=True)
    replay.add_argument("--ce", required=True)
    replay.add_argument("--observed-at", required=True)
    collect = commands.add_parser(
        "collect",
        help="Run the bounded collector using an existing operator policy and writer DSN",
    )
    collect.add_argument("--policy-sha256", required=True)
    collect.add_argument("--scheduled-for", required=True)
    collect.add_argument("--ce", action="append", required=True)
    install = commands.add_parser(
        "install", help="Apply the source-only schema and SELECT-only reader grants"
    )
    install.add_argument("--reader-role", required=True)
    activate = commands.add_parser(
        "activate-policy",
        help="Record an existing reviewed checksum-pinned source policy",
    )
    activate.add_argument("--file", required=True)
    activate.add_argument("--sha256", required=True)
    commands.add_parser(
        "status", help="Read actual persisted state through SFC_READER_DSN"
    )
    publish = commands.add_parser(
        "publish", help="Publish or roll back an independently restored source version"
    )
    publish.add_argument("--version", required=True)
    publish.add_argument(
        "--expected-version",
        required=True,
        help="Exact accepted version, or NONE for the first publication",
    )
    qualify = commands.add_parser(
        "qualify-restore",
        help="Compare a real independently restored database and retrieved artifact",
    )
    qualify.add_argument("--version", required=True)
    qualify.add_argument("--artifact", required=True)
    qualify.add_argument("--sha256", required=True)
    revoke = commands.add_parser(
        "revoke-policy", help="Close the exact source policy without deleting data"
    )
    revoke.add_argument("--sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "parse":
            with Path(args.html).open("rb") as source:
                raw = source.read(MAX_BODY + 1)
            result = parse_page(
                raw,
                args.ce,
                datetime.fromisoformat(args.observed_at.replace("Z", "+00:00")),
            ).model_dump(mode="json")
        elif args.command == "status":
            from ..read import Reader
            from .read import SfcReader

            result = SfcReader(
                Reader(
                    os.environ["SFC_READER_DSN"],
                    b"operator-status-only-secret-32-bytes",
                )
            ).status()
        else:
            from .state import State

            state = State(os.environ["SFC_WRITER_DSN"])
            if args.command == "install":
                from .state import grant_reader

                sha = state.migrate()
                grant_reader(state.dsn, args.reader_role)
                result = {"schemaSha256": sha, "reader": "SELECT_only"}
            elif args.command == "activate-policy":
                from .policy import Policy

                with Path(args.file).open("rb") as source:
                    raw = source.read(32769)
                if len(raw) > 32768:
                    raise Rejected("SFC_POLICY_SIZE")
                policy = Policy.model_validate_json(raw)
                state.activate(policy, args.sha256)
                result = {"policySha256": policy.sha256, "activated": True}
            elif args.command == "revoke-policy":
                state.revoke(args.sha256)
                result = {
                    "policySha256": args.sha256,
                    "revoked": True,
                    "dataDeleted": False,
                }
            elif args.command == "qualify-restore":
                result = state.qualify_restore(
                    args.version,
                    State(os.environ["SFC_RESTORED_DSN"]),
                    args.artifact,
                    args.sha256,
                )
            elif args.command == "publish":
                state.publish(
                    args.version,
                    None if args.expected_version == "NONE" else args.expected_version,
                )
                result = {"acceptedVersion": args.version}
            else:
                result = collect_run(state, args)
        print(json.dumps(result, ensure_ascii=False, default=str))
    except Exception as exc:
        # Never print DSNs, source bytes or file contents in error output.
        raise SystemExit(
            str(exc) if isinstance(exc, Rejected) else "SFC_OPERATOR_INPUT_ERROR"
        ) from None


def collect_run(state, args):
    with state.connection() as conn:
        policy = state.policy(
            conn, args.policy_sha256, "automation", "retention", "backup"
        )
    when = datetime.fromisoformat(args.scheduled_for.replace("Z", "+00:00"))
    if (
        when.tzinfo is None
        or when.utcoffset() is None
        or when > datetime.now(timezone.utc)
    ):
        raise Rejected("SFC_INVALID_OCCURRENCE")
    return Collector(state, policy).collect(when, args.ce)


if __name__ == "__main__":
    main()
