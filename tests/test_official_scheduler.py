"""Exercise host runner failure/overlap behavior without host data or credentials."""

import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def executable(path, source):
    path.write_text("#!/bin/sh\n" + source + "\n")
    path.chmod(0o755)


def test_backfill_overlap_skips_without_starting_or_stopping_any_container(tmp_path):
    executable(tmp_path / "systemctl", '[ "$1" = is-active ] && exit 0; exit 99')
    executable(tmp_path / "docker", "exit 99")
    result = subprocess.run(
        ["sh", str(ROOT / "deploy/curated/run-official.sh"), "backfill"],
        env=dict(os.environ, PATH=str(tmp_path) + ":" + os.environ["PATH"]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "Backfill skipped" in result.stdout


def test_collector_interruption_still_runs_independent_logical_backup(tmp_path):
    release = tmp_path / "release" / "deploy" / "curated"
    release.mkdir(parents=True)
    runner = release / "run-official.sh"
    runner.write_bytes((ROOT / "deploy/curated/run-official.sh").read_bytes())
    executable(
        release / "backup-official.sh", 'touch "$(dirname "$0")/backup-observed"'
    )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable(binaries / "flock", "exit 0")
    executable(binaries / "systemctl", 'printf "0\\n"')
    executable(
        binaries / "awk",
        'case "$1" in *MemAvailable*) printf "2097152\\n";; *NR==2*) printf "20971520\\n";; *) printf "100000000\\n";; esac',
    )
    executable(
        binaries / "docker",
        '[ "$1" = compose ] && { printf "fixture-image\\n"; exit 0; }; exit 137',
    )
    result = subprocess.run(
        ["sh", str(runner), "freshness"],
        env=dict(
            os.environ,
            PATH=str(binaries) + ":" + os.environ["PATH"],
            MCP_HK_MAINTENANCE_LOCK=str(tmp_path / "maintenance.lock"),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 137
    assert "interrupted_or_unknown" in result.stdout
    assert (release / "backup-observed").exists()
