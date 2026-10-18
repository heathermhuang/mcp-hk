# Contributing to mcp-open-data-hk

Thank you for your interest in contributing to mcp-open-data-hk! Here are some guidelines to help you get started.

## Code of Conduct

By participating in this project, you are expected to uphold our Code of Conduct (TBD).

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue on our GitHub repository with:
1. A clear and descriptive title
2. A detailed description of the problem
3. Steps to reproduce the issue
4. Information about your environment (OS, Python version, etc.)

### Suggesting Enhancements

If you have an idea for an enhancement, please create an issue with:
1. A clear and descriptive title
2. A detailed explanation of the proposed enhancement
3. Examples of how the enhancement would be used

### Pull Requests

1. Fork the repository
2. Create a new branch for your feature or bug fix
3. Make your changes
4. Add tests if applicable
5. Run `bash scripts/check.sh all` after the final edit
6. Commit your changes with a clear and descriptive commit message
7. Push your branch to your fork
8. Create a pull request to the main repository

## Development Setup

Fork and clone the repository. Use Python 3.10–3.12, Node.js 22 and npm.
From the repository root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
npm --prefix deploy/cloudflare ci --ignore-scripts
git config --local core.hooksPath .githooks
bash scripts/check.sh all
```

If this checkout already uses custom hooks, integrate `.githooks/pre-push` into
that setup instead of replacing it. Git does not enable repository hooks on clone;
install the hook in each new checkout. Git Bash is required on Windows.

The pre-push hook checks formatting, lint, the full Python suite, and Worker types
and tests. It rejects an uncommitted working tree or a push of another commit so
results describe the actual pushed files. It also rejects changes made while
checks run. Commit the final edits before pushing; fix failures and commit again.
Branch deletions do not run checks. The hook does not install dependencies or call
live government APIs. CI remains authoritative for all three Python versions and
the distributable build. Local checks use `.venv/bin/python`; set `PYTHON` to an
alternative interpreter if needed.

The same entrypoint runs in CI. Run individual groups while iterating:

```bash
bash scripts/check.sh python
bash scripts/check.sh quality
bash scripts/check.sh worker
```

## Code Style

This project uses:
- Black for code formatting
- Flake8 for linting

Before submitting a pull request, please ensure your code adheres to these standards by running:
```bash
black src/ tests/
flake8 src/ tests/
```

## Testing

All contributions should include appropriate tests. We use pytest for testing.

Run all tests with:
```bash
bash scripts/check.sh python
```

## Questions?

If you have any questions, please create an issue or contact the maintainers.
