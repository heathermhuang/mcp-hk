"""Host image discovery never treats job/candidate images as the serving image."""

import copy
import importlib.util
import json
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "source_backend_image", ROOT / "deploy/curated/backend-image.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
CID = "b" * 64
IMAGE = "sha256:" + "a" * 64
LABELS = {
    "com.docker.compose.project": "curated",
    "com.docker.compose.service": "backend",
    "com.docker.compose.oneoff": "False",
}


def record():
    return {
        "Id": CID,
        "Image": IMAGE,
        "State": {"Running": True},
        "Config": {"Labels": dict(LABELS), "Env": ["PRIVATE_TEST_SENTINEL"]},
    }


def test_resolution_filters_runtime_service_and_uses_immutable_image():
    calls = []

    def docker(args):
        calls.append(args)
        if args[0] == "ps":
            assert "--no-trunc" in args
            assert all("label=" + k + "=" + v in args for k, v in LABELS.items())
            return CID + "\n"
        assert args == ["inspect", "--type", "container", CID]
        return json.dumps([record()])

    assert module.resolve_serving_image(docker) == IMAGE
    assert len(calls) == 2
    assert not any("compose" in call for call in calls)


@pytest.mark.parametrize(
    "ids,code",
    [
        ("", "MISSING"),
        (CID + "\n" + "c" * 64, "AMBIGUOUS"),
        ("bad-reference", "INVALID"),
    ],
)
def test_missing_ambiguous_or_invalid_runtime_never_reaches_image_inspection(ids, code):
    calls = []

    def docker(args):
        calls.append(args)
        return ids

    with pytest.raises(module.ImageResolutionError, match=code):
        module.resolve_serving_image(docker)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "change",
    [
        "stopped",
        "oneoff",
        "wrong-service",
        "wrong-id",
        "multiline-image",
        "tagged-image",
        "wrong-shape",
    ],
)
def test_stale_or_unqualified_inspection_is_rejected(change):
    data = copy.deepcopy(record())
    if change == "stopped":
        data["State"]["Running"] = False
    elif change == "oneoff":
        data["Config"]["Labels"]["com.docker.compose.oneoff"] = "True"
    elif change == "wrong-service":
        data["Config"]["Labels"]["com.docker.compose.service"] = "other"
    elif change == "wrong-id":
        data["Id"] = "c" * 64
    elif change == "multiline-image":
        data["Image"] = IMAGE + "\n" + "d" * 64
    elif change == "tagged-image":
        data["Image"] = "fixture:mutable-tag"
    else:
        data = "invalid"

    def docker(args):
        return CID if args[0] == "ps" else json.dumps([data])

    with pytest.raises(module.ImageResolutionError):
        module.resolve_serving_image(docker)


def test_cli_failure_does_not_expose_runtime_inspection_or_credentials(tmp_path):
    docker = tmp_path / "docker"
    docker.write_text("#!/bin/sh\nprintf 'PRIVATE_TEST_SENTINEL' >&2\nexit 125\n")
    docker.chmod(0o755)
    import os
    import sys

    result = subprocess.run(
        [sys.executable, str(ROOT / "deploy/curated/backend-image.py")],
        env=dict(os.environ, PATH=str(tmp_path) + ":" + os.environ["PATH"]),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1 and not result.stdout
    assert "SOURCE_BACKEND_DOCKER_QUERY_FAILED" in result.stderr
    assert "PRIVATE_TEST_SENTINEL" not in result.stderr
