"""Exercise push rejection with real local Git remotes, without network access."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd, env):
    return subprocess.run(
        args, cwd=cwd, env=env, text=True, capture_output=True, timeout=20
    )


@pytest.mark.parametrize("case", ["success", "failed", "dirty", "changed", "other"])
def test_pre_push_checks_actual_pushed_commit(tmp_path, case):
    repo, remote = tmp_path / "repo", tmp_path / "remote.git"
    repo.mkdir()
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"}
    }
    env.update(
        GIT_AUTHOR_NAME="Test",
        GIT_AUTHOR_EMAIL="test@example.invalid",
        GIT_COMMITTER_NAME="Test",
        GIT_COMMITTER_EMAIL="test@example.invalid",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_CONFIG_GLOBAL=os.devnull,
    )

    def git(*args):
        result = run("git", *args, cwd=repo, env=env)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    git("init", "-q")
    git("init", "--bare", "-q", str(remote))
    (repo / ".githooks").mkdir()
    shutil.copy2(ROOT / ".githooks/pre-push", repo / ".githooks/pre-push")
    (repo / "scripts").mkdir()
    check = repo / "scripts/check.sh"
    check.write_text(
        {
            "failed": "exit 23\n",
            "changed": "echo changed >> tracked.txt\n",
        }.get(case, 'test "$1" = all\n')
    )
    (repo / "tracked.txt").write_text("original\n")
    git("add", ".")
    git("commit", "-qm", "Initial")
    git("config", "core.hooksPath", ".githooks")
    tip = git("rev-parse", "HEAD")
    if case == "dirty":
        (repo / "uncommitted.txt").write_text("must not mask the pushed files\n")
    if case == "other":
        (repo / "tracked.txt").write_text("second\n")
        git("commit", "-qam", "Second")

    result = run(
        "git", "push", str(remote), f"{tip}:refs/heads/test", cwd=repo, env=env
    )
    published = run(
        "git",
        "--git-dir",
        str(remote),
        "rev-parse",
        "--verify",
        "refs/heads/test",
        cwd=repo,
        env=env,
    )
    if case == "success":
        assert result.returncode == 0, result.stderr
        assert published.stdout.strip() == tip
    else:
        assert result.returncode != 0
        assert published.returncode != 0
        if case != "failed":
            assert "Push blocked:" in result.stderr


@pytest.mark.parametrize("fail_pytest", [False, True])
def test_shared_check_runs_full_suite_and_propagates_failure(tmp_path, fail_pytest):
    (tmp_path / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/check.sh", tmp_path / "scripts/check.sh")
    (tmp_path / "deploy/cloudflare").mkdir(parents=True)
    tools = tmp_path / "bin"
    tools.mkdir()
    log = tmp_path / "calls"
    for name in ["python", "npm"]:
        tool = tools / name
        tool.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CHECK_LOG"\n'
            'if [ "$1" = -m ] && [ "$2" = pytest ]; then\n'
            '  test "$PYTHONPATH" = "$CHECK_ROOT/src" || exit 99\n'
            '  if [ "$FAIL_PYTEST" = 1 ]; then exit 23; fi\n'
            "fi\nexit 0\n"
        )
        tool.chmod(0o755)
    env = dict(
        os.environ,
        PATH=f"{tools}{os.pathsep}{os.environ['PATH']}",
        PYTHON=str(tools / "python"),
        PYTHONPATH="",
        CHECK_ROOT=str(tmp_path.resolve()),
        CHECK_LOG=str(log),
        FAIL_PYTEST=str(int(fail_pytest)),
    )
    result = run("bash", "scripts/check.sh", "all", cwd=tmp_path, env=env)
    assert result.returncode == (23 if fail_pytest else 0), result.stderr
    expected = [
        "-m black --check src/ tests/",
        "-m flake8 src/ tests/",
        "-m pytest tests/",
    ]
    if not fail_pytest:
        expected += ["run types", "run check", "test"]
    assert log.read_text().splitlines() == expected
