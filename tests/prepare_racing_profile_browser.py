"""Seed invented facts in the local/CI preview only; zero provider requests."""

import os
from pathlib import Path
import tempfile

import pytest

from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.sources import DISTRICTS
from test_racing_profile_public import prepared, observations, accept_profile


def main():
    store = Store(os.environ["MCP_HK_DATABASE"])
    store.publish(
        "restaurants", [{"id": "fixture", "latitude": 22.3, "longitude": 114.1}], None
    )
    store.publish(
        "population",
        [{"id": d["id"] + ":2024", "districtId": d["id"]} for d in DISTRICTS],
        None,
    )
    service = Service(store)
    with (
        tempfile.TemporaryDirectory(prefix="racing-browser-fixture-") as folder,
        pytest.MonkeyPatch.context() as patch,
    ):
        root = Path(folder)
        prepared.__wrapped__(service, root, patch)
        candidate = service.racing.store.profiles.stage(*observations())
        accept_profile(service, root, candidate)


if __name__ == "__main__":
    main()
