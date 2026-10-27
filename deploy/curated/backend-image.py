#!/usr/bin/env python3
"""Resolve the serving image, excluding one-off jobs and stopped containers."""

import json
import re
import subprocess
import sys


class ImageResolutionError(ValueError):
    pass


def docker(arguments):
    return subprocess.run(
        ["docker", *arguments],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    ).stdout


def resolve_serving_image(command=docker):
    labels = {
        "com.docker.compose.project": "curated",
        "com.docker.compose.service": "backend",
        "com.docker.compose.oneoff": "False",
    }
    arguments = ["ps", "--quiet", "--no-trunc"]
    for name, value in labels.items():
        arguments.extend(["--filter", "label=" + name + "=" + value])
    ids = command(arguments).split()
    if not ids:
        raise ImageResolutionError("SOURCE_BACKEND_CONTAINER_MISSING")
    if len(ids) != 1:
        raise ImageResolutionError("SOURCE_BACKEND_CONTAINER_AMBIGUOUS")
    if not re.fullmatch(r"[a-f0-9]{12,64}", ids[0]):
        raise ImageResolutionError("SOURCE_BACKEND_CONTAINER_INVALID")
    inspected = json.loads(command(["inspect", "--type", "container", ids[0]]))
    if not isinstance(inspected, list) or len(inspected) != 1:
        raise ImageResolutionError("SOURCE_BACKEND_INSPECTION_INVALID")
    container = inspected[0]
    if (
        not isinstance(container, dict)
        or not isinstance(container.get("Config"), dict)
        or not isinstance(container.get("State"), dict)
        or not isinstance(container["Config"].get("Labels"), dict)
    ):
        raise ImageResolutionError("SOURCE_BACKEND_INSPECTION_INVALID")
    if (
        not container.get("Id", "").startswith(ids[0])
        or container.get("State", {}).get("Running") is not True
        or any(
            container.get("Config", {}).get("Labels", {}).get(k) != v
            for k, v in labels.items()
        )
    ):
        raise ImageResolutionError("SOURCE_BACKEND_RUNTIME_MISMATCH")
    image = container.get("Image", "")
    if not isinstance(image, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", image):
        raise ImageResolutionError("SOURCE_BACKEND_IMAGE_INVALID")
    return image


def main():
    try:
        image = resolve_serving_image()
    except ImageResolutionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        # Inspection can contain runtime credentials; never echo it or stderr.
        print("SOURCE_BACKEND_DOCKER_QUERY_FAILED", file=sys.stderr)
        return 1
    print(image)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
