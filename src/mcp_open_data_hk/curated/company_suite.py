"""Deterministic coordinator for one existing full-cohort qualification wake.

No timer/model is installed. Local public-read verification can continue through
successive checkpointed batches within a finite session; source collectors retain
their own separate ten-minute bounds, locks, holds and provider allowances.
"""

import argparse
import json
import os
from pathlib import Path
import time

from .acceptance import Journal, company_plan
from .company_verify import PublicVerifier
from .company_browser_verify import visible_verifier


def run(journal, verify, *, seconds=5400):
    if type(seconds) is not int or not 1 <= seconds <= 5400:
        raise ValueError("ACCEPTANCE_SESSION_BOUND_REQUIRED")
    deadline = time.monotonic() + seconds
    while journal.pending() and time.monotonic() < deadline:
        progress = journal.run(
            verify, limit=20, seconds=min(580, deadline - time.monotonic())
        )
        if not progress["completedSteps"]:
            break
    return journal.summary()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--seconds", type=int, default=5400)
    args = parser.parse_args()
    plan = company_plan(json.loads(Path(args.cohort).read_text()))
    folder = Path(args.folder).resolve() / plan["version"]
    journal = Journal(folder / "progress.sqlite3", plan)
    public = PublicVerifier(folder / "responses")
    browser = visible_verifier(plan, folder)

    def verify(case, step, version):
        return (
            public.verify(case, step, version)
            if step in {"rest", "mcp"}
            else browser(case, step, version)
        )

    try:
        print(json.dumps(run(journal, verify, seconds=args.seconds)))
    finally:
        public.client.close()


if __name__ == "__main__":
    os.umask(0o077)
    main()
