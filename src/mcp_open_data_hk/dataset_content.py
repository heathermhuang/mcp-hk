"""Shared bilingual family descriptions; runtime coverage stays in source status."""

import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def families():
    return json.loads((Path(__file__).parent / "web/datasets.json").read_text())


def family(key):
    return next(row for row in families() if row["id"] == key)
