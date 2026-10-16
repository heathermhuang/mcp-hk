"""Upstream live probes are explicit; new deterministic tests never skip failures."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--live",
        action="store_true",
        help="Include optional upstream live source probes",
    )


def pytest_collection_modifyitems(config, items):
    for item in items:
        if item.path.name in {"test_client.py", "test_data_gov_hk.py"}:
            item.add_marker(pytest.mark.live)
            if not config.getoption("--live"):
                item.add_marker(
                    pytest.mark.skip(
                        reason="Pass --live for upstream government integration probes"
                    )
                )
