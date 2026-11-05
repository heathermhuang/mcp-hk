"""Small reviewed overlays; exact source identity and immutable revision hashes."""

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


@lru_cache(maxsize=1)
def profiles():
    return tuple(
        json.loads(p.read_text())
        for p in sorted(Path(__file__).with_name("profiles").glob("*.json"))
    )


def fingerprint(profile):
    return hashlib.sha256(
        json.dumps(profile, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def profile_for(resource):
    for profile in profiles():
        if (resource.get("id"), resource.get("datasetId"), resource.get("format")) != (
            profile["resourceId"],
            profile["datasetId"],
            profile["format"],
        ):
            continue
        try:
            url = urlsplit(resource.get("url", ""))
            if url.port is not None:
                return None
        except ValueError:
            return None
        if (
            url.scheme in {"http", "https"}
            and url.hostname == profile["host"]
            and url.path == profile["path"]
            and parse_qs(url.query, keep_blank_values=True) == profile["query"]
            and not url.username
            and not url.password
            and url.port is None
        ):
            return profile
    return None


def dataset_kind(dataset_id):
    return next(
        (p["entityKind"] for p in profiles() if p["datasetId"] == dataset_id), None
    )


def accepted_binding(resource, schema):
    profile = profile_for(resource)
    binding = schema.get("semanticBinding", {})
    if profile and binding.get("profileFingerprint") == fingerprint(profile):
        return binding
    return None


def manifest_fingerprint():
    return hashlib.sha256(
        "\n".join(fingerprint(p) for p in profiles()).encode()
    ).hexdigest()
