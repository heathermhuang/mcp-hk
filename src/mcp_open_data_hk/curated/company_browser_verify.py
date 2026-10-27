"""Visible-browser batches for the existing company owner, using its pinned journal."""

import argparse
import json
import os
from pathlib import Path
import subprocess

from .acceptance import (
    Journal,
    company_plan,
    sha,
    verify_company_record,
    verify_page_zip,
    canonical,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", required=True)
    parser.add_argument("--folder", required=True)
    parser.add_argument("--limit", type=int, default=2)
    args = parser.parse_args()
    plan = company_plan(json.loads(Path(args.cohort).read_text()))
    folder = Path(args.folder).resolve() / plan["version"]
    journal = Journal(folder / "progress.sqlite3", plan)
    script = (
        Path(__file__).resolve().parents[3] / "deploy/cloudflare/company-acceptance.mjs"
    )

    def verify(case, step, version):
        language = step.removeprefix("browser_zip_").removeprefix("browser_")
        target = folder / "browser" / (sha(case["id"].encode()) + "-" + language)
        proof = target / "verified.json"
        if not proof.exists():
            target.mkdir(parents=True, exist_ok=True, mode=0o700)
            task = target / "task.json"
            task.write_bytes(
                canonical(
                    {
                        "case": case,
                        "language": language,
                        "version": version,
                        "screenshot": case == plan["cases"][0],
                    }
                )
            )
            result = subprocess.run(
                ["node", str(script), str(task), str(target)],
                capture_output=True,
                timeout=180,
            )
            (target / "runner.log").write_bytes(result.stdout + result.stderr)
            if result.returncode:
                raise ValueError("ACTUAL_BROWSER_VERIFICATION_FAILED")
        receipt = json.loads((target / "receipt.json").read_text())
        envelope = json.loads((target / "envelope.json").read_text())
        selection = json.loads((target / "selection.json").read_text())
        if (
            receipt["actualVisibleBrowser"] is not True
            or receipt["version"] != version
            or receipt["sourceKey"] != case["id"]
            or receipt["language"] != language
        ):
            raise ValueError("ACTUAL_BROWSER_IDENTITY_MISMATCH")
        detail = {**envelope, "data": envelope["data"]["items"][0]}
        verify_company_record(detail, case, version)
        package = verify_page_zip(
            (target / "actual.zip").read_bytes(), envelope, selection
        )
        proof.write_bytes(
            canonical(
                dict(
                    package,
                    actualVisibleBrowser=True,
                    version=version,
                    language=language,
                    sourceKey=case["id"],
                )
            )
            + b"\n"
        )
        return [
            target / "receipt.json",
            proof,
            target / "actual.zip",
            target / "envelope.json",
        ]

    journal.run(
        verify,
        limit=args.limit,
        seconds=580,
        steps={
            "browser_en",
            "browser_zh-Hant",
            "browser_zip_en",
            "browser_zip_zh-Hant",
        },
    )
    print(json.dumps(journal.summary()))


if __name__ == "__main__":
    os.umask(0o077)
    main()
