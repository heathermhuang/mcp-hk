"""Operator build/replay and bounded collection commands; no public activation."""

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
        else:
            from .state import State

            state = State(os.environ["SFC_WRITER_DSN"])
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
            result = Collector(state, policy).collect(when, args.ce)
        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        # Never print DSNs, source bytes or file contents in error output.
        raise SystemExit(
            str(exc) if isinstance(exc, Rejected) else "SFC_OPERATOR_INPUT_ERROR"
        ) from None


if __name__ == "__main__":
    main()
