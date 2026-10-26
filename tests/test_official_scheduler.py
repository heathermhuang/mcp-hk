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


def test_partial_backfill_still_requests_recovery_milestone(tmp_path):
    import json

    release = tmp_path / "release" / "deploy" / "curated"
    release.mkdir(parents=True)
    runner = release / "run-backfill.sh"
    runner.write_bytes((ROOT / "deploy/curated/run-backfill.sh").read_bytes())
    executable(release / "run-official.sh", "exit 1")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    counter = tmp_path / "counter"
    executable(
        binaries / "docker",
        f"""if [ -f '{counter}' ]; then printf '%s\\n' '{{"pendingPairs":80,"milestoneNeeded":10,"noOp":false}}'; else touch '{counter}'; printf '%s\\n' '{{"pendingPairs":84,"milestoneNeeded":null,"noOp":false}}'; fi""",
    )
    marker = tmp_path / "milestone"
    executable(binaries / "systemctl", f'touch "{marker}"')
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "providerBackupWeekdayUtc": "SUN",
                "providerBackupStartHourUtc": 0,
                "providerBackupEndHourUtc": 0,
            }
        )
    )
    result = subprocess.run(
        ["sh", str(runner)],
        env=dict(
            os.environ,
            PATH=str(binaries) + ":" + os.environ["PATH"],
            MCP_HK_MAINTENANCE_POLICY=str(policy),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert marker.exists()
    assert '"milestoneNeeded":10' in result.stdout


def test_timer_provenance_uses_typed_monotonic_value(tmp_path):
    for mode in ["freshness", "offsite"]:
        folder = tmp_path / mode
        release = folder / "release" / "deploy" / "curated"
        release.mkdir(parents=True)
        source = (
            ROOT
            / "deploy/curated"
            / ("run-official.sh" if mode == "freshness" else "run-offsite.sh")
        )
        config = folder / "uploader.json"
        config.write_text("{}")
        runner = release / source.name
        state = folder / "state"
        state.mkdir()
        runner.write_text(
            source.read_text()
            .replace("/etc/mcp-hk-curated/official-uploader.json", str(config))
            .replace("/srv/mcp-hk-curated", str(state))
        )
        executable(release / "backup-official.sh", "exit 0")
        binaries = folder / "bin"
        binaries.mkdir()
        executable(binaries / "flock", "exit 0")
        executable(binaries / "systemctl", 'printf "1d 5h 42min 31.861600s\\n"')
        executable(binaries / "busctl", 'printf "t 99999000\\n"')
        executable(
            binaries / "awk",
            'case "$1" in *MemAvailable*) printf "2097152\\n";; *NR==2*) printf "20971520\\n";; *) printf "100000000\\n";; esac',
        )
        arguments = folder / "arguments"
        executable(
            binaries / "docker",
            f"""[ "$1" = compose ] && {{ printf 'fixture-image\\n'; exit 0; }}
printf '%s\\n' "$@" > '{arguments}'
printf '%s\\n' '{{"status":"success","jobId":""}}'""",
        )
        result = subprocess.run(
            ["sh", str(runner)],
            env=dict(
                os.environ,
                PATH=str(binaries) + ":" + os.environ["PATH"],
                MCP_HK_MAINTENANCE_LOCK=str(folder / "lock"),
            ),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        values = arguments.read_text().splitlines()
        stamp = values[values.index("--scheduled-for") + 1]
        assert stamp.endswith("T05:00:00Z" if mode == "freshness" else "T05:17:00Z")
        assert "Illegal number" not in result.stderr


def test_restore_prepares_statistics_before_reader_qualification(tmp_path):
    release = tmp_path / "release" / "deploy" / "curated"
    release.mkdir(parents=True)
    runner = release / "restore-official.sh"
    runner.write_text(
        (ROOT / "deploy/curated/restore-official.sh")
        .read_text()
        .replace("/srv/mcp-hk-curated", str(tmp_path))
    )
    job = "a" * 32
    evidence = tmp_path / "official-offsite"
    evidence.mkdir()
    (evidence / ("retrieved-" + job + ".dump")).write_bytes(b"retained dump")
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable(binaries / "stat", 'printf "128\\n"')
    executable(binaries / "awk", 'printf "20971520\\n"')
    marker = tmp_path / "analyzed"
    calls = tmp_path / "calls"
    executable(
        binaries / "docker",
        f"""printf '%s\\n' "$*" >> '{calls}'
[ "$1" = compose ] && {{ printf 'fixture-image\\n'; exit 0; }}
case "$*" in
 *vacuumdb*) touch '{marker}';;
 *official_restore_check*) [ -f '{marker}' ] || exit 1; printf '%s\\n' '{{"freshOffsiteRestoreVerified":true}}';;
esac
exit 0""",
    )
    result = subprocess.run(
        ["sh", str(runner), job],
        env=dict(os.environ, PATH=str(binaries) + ":" + os.environ["PATH"]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    log = calls.read_text()
    assert "--analyze-only --schema=curated" in log
    assert (
        log.index("pg_restore")
        < log.index("vacuumdb")
        < log.index("official_restore_check")
    )
    assert log.index("official_restore_check") < log.index("dropdb")


def test_health_defers_all_database_writes_while_owning_backup_lock_is_busy(tmp_path):
    release = tmp_path / "release" / "deploy" / "curated"
    release.mkdir(parents=True)
    runner = release / "verify-official.sh"
    state = tmp_path / "state"
    state.mkdir()
    runner.write_text(
        (ROOT / "deploy/curated/verify-official.sh")
        .read_text()
        .replace("/srv/mcp-hk-curated", str(state))
    )
    binaries = tmp_path / "bin"
    binaries.mkdir()
    executable(binaries / "flock", "exit 1")
    executable(
        binaries / "date",
        'case "$1" in +%H) printf "05\\n";; *) printf "2026-10-26T05:00:00Z\\n";; esac',
    )
    marker = tmp_path / "database-write"
    executable(
        binaries / "docker",
        f'touch "{marker}"; printf \'{{"status":"performance_or_restore_failure"}}\\n\'',
    )
    result = subprocess.run(
        ["sh", str(runner)],
        env=dict(
            os.environ,
            PATH=str(binaries) + ":" + os.environ["PATH"],
            MCP_HK_MAINTENANCE_LOCK=str(tmp_path / "maintenance.lock"),
        ),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert not marker.exists()
    assert '"verificationDeferred":true' in result.stdout
    assert (state / "official-health-running").read_text() == "2026-10-26T05:00:00Z"


def test_hkex_timer_uses_typed_trigger_and_canonical_occurrence():
    import importlib.util
    from datetime import datetime, timezone

    spec = importlib.util.spec_from_file_location(
        "hkex_host_job", ROOT / "deploy/curated/hkex-daily-job.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    current = datetime(2026, 10, 26, 5, 20, 0, 411112, tzinfo=timezone.utc)
    assert module.scheduled_occurrence("t 99999000", 100000000, current) == (
        "timer",
        "2026-10-26T05:20:00Z",
    )
    assert module.scheduled_occurrence("t 1", 100000000, current)[0] == "manual"
    assert (
        module.scheduled_occurrence("1d 5h 42min 31.861600s", 100000000, current)[0]
        == "manual"
    )
    assert module.scheduled_occurrence("t 100000001", 100000000, current)[0] == "manual"
    catchup = datetime(2026, 10, 26, 0, 30, tzinfo=timezone.utc)
    assert module.scheduled_occurrence("t 99999000", 100000000, catchup) == (
        "timer",
        "2026-10-25T14:20:00Z",
    )
