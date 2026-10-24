#!/usr/bin/env python3
"""Freeze a clean candidate, checks and explicitly supplied sanitized receipts.

Output must be outside the repository. Never supply raw auth/runtime logs.
"""

import argparse
import hashlib
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

AUDIT = "4692f9a4c199aaabc75e26eb837cbb918e672553"
BASE = "d6a4dda7ff53ed04d197bca1b89604ae6c713351"


def git(*args):
    return subprocess.check_output(["git", *args])


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, action="append", default=[])
    args = parser.parse_args()
    root = Path(git("rev-parse", "--show-toplevel").decode().strip()).resolve()
    output = args.output.resolve()
    if output == root or root in output.parents:
        raise SystemExit("Use an output directory outside the candidate checkout")
    if git("status", "--porcelain").strip():
        raise SystemExit("Commit the candidate first; dirty evidence is not immutable")
    output.mkdir(parents=True, exist_ok=False)
    candidate = git("rev-parse", "HEAD").decode().strip()
    tree = git("rev-parse", "HEAD^{tree}").decode().strip()
    started = datetime.now(timezone.utc).isoformat()
    checks = output / "required-checks.log"
    with checks.open("wb") as log:
        result = subprocess.run(
            ["bash", "scripts/check.sh", "all"], stdout=log, stderr=subprocess.STDOUT
        )
    if (
        result.returncode
        or git("status", "--porcelain").strip()
        or git("rev-parse", "HEAD").decode().strip() != candidate
    ):
        raise SystemExit(
            "Checks failed or candidate changed; retain failed log and freeze a new directory after repair"
        )
    subprocess.run(
        [
            "git",
            "archive",
            "--format=tar.gz",
            "--output=" + str(output / "candidate-source.tar.gz"),
            candidate,
        ],
        check=True,
    )
    (output / "audit-to-candidate.diff").write_bytes(
        git("diff", "--binary", AUDIT, candidate)
    )
    (output / "audit-to-base.diff").write_bytes(git("diff", "--binary", AUDIT, BASE))
    for name in ["README.md", "delta-review.md"]:
        shutil.copyfile(
            root / "docs/security/remediation-20261024" / name, output / name
        )
    for receipt in args.receipt:
        # Caller supplies reviewed, sanitized evidence only; keep exact bytes/hash.
        if receipt.suffix not in {".json", ".jsonl"}:
            raise SystemExit("Only reviewed structured receipts may be included")
        shutil.copyfile(receipt, output / receipt.name)
    hashes = {
        str(p.relative_to(root)): sha(p)
        for p in [
            root / "requirements.lock",
            root / "uv.lock",
            root / "pyproject.toml",
            root / "Dockerfile",
            root / "deploy/cloudflare/package.json",
            root / "deploy/cloudflare/package-lock.json",
            root / "deploy/cloudflare/wrangler.jsonc",
        ]
    }
    fixtures = {
        str(p.relative_to(root)): sha(p)
        for pattern in [
            "tests/test_security_*.py",
            "tests/fixtures/*.json",
            "deploy/cloudflare/*auth.test.mjs",
            "deploy/cloudflare/upstream.test.mjs",
            "deploy/cloudflare/security-policy.test.mjs",
            "scripts/security/*.py",
            "scripts/security_baseline*",
        ]
        for p in sorted(root.glob(pattern))
    }
    states = {
        str(i): {
            "planned": True,
            "code_complete": i not in {2, 5, 6},
            "local_validation": (
                "failed-egress-acceptance"
                if i in {2, 6}
                else (
                    "partial-hosted-network"
                    if i == 5
                    else (
                        "contract-only-no-model-eval"
                        if i == 7
                        else "passed-focused-tests"
                    )
                )
            ),
            "staging_validated": False,
            "deployed_observed": False,
            "assessor_closed": False,
        }
        for i in range(1, 8)
    }
    manifest = {
        "candidate": candidate,
        "tree": tree,
        "audit": AUDIT,
        "implementationBase": BASE,
        "startedAt": started,
        "finishedAt": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": subprocess.check_output(
                [str(root / ".venv/bin/python"), "--version"]
            )
            .decode()
            .strip(),
            "node": subprocess.check_output(["node", "--version"]).decode().strip(),
            "kind": "local synthetic; no remote staging or production",
        },
        "checks": {
            "command": "bash scripts/check.sh all",
            "exitCode": result.returncode,
            "expected": "required checks pass",
            "actual": "passed",
            "artifact": checks.name,
            "artifactSha256": sha(checks),
        },
        "dependencyConfigurationHashes": hashes,
        "fixtureHashes": fixtures,
        "findings": states,
        "assessorAddendum": "not supplied; exact classification pending",
        "artifacts": {p.name: sha(p) for p in sorted(output.iterdir()) if p.is_file()},
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(
        json.dumps(
            {
                "candidate": candidate,
                "output": str(output),
                "checks": "passed",
                "releaseReady": False,
                "blockingAcceptance": "local container direct-egress bypass",
            }
        )
    )


if __name__ == "__main__":
    main()
