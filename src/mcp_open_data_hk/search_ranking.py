"""Pure deterministic relevance; SQLite calls the same primitives as guided views.

No source I/O or volatile capability state belongs in this ordering contract.
"""

import json
import unicodedata


# Existing qualified HKO measurement shortcuts; aliases describe a task, not
# translated source metadata or a new semantic/source binding.
TASK_ALIASES = {
    "hk-hko-rss-current-weather-report": [
        "weather",
        "current weather",
        "天氣",
        "現時天氣",
    ]
}

CATALOGUE_INTENT = frozenset(
    [
        "mcp:catalogue",
        "catalogue",
        "catalog",
        "data catalogue",
        "dataset catalogue",
        "government dataset catalogue",
        "數據目錄",
        "資料目錄",
        "政府數據目錄",
    ]
)


def normalise(text):
    return " ".join(unicodedata.normalize("NFKC", str(text or "")).casefold().split())


def bucket(item, query, aliases=None):
    phrase = normalise(query)
    gateway = item.get("packId") == "catalogue" or item.get("id") == "mcp:catalogue"
    if gateway:
        return -1 if phrase in CATALOGUE_INTENT else 5
    if phrase in [normalise(item.get(k)) for k in ("id", "title", "titleZhHant")]:
        return 0
    if phrase in [normalise(a) for a in (aliases or {}).get(item.get("id"), [])]:
        return 1
    terms = phrase.split()
    if any(
        all(t in normalise(item.get(k)) for t in terms)
        for k in ("title", "titleZhHant")
    ):
        return 2
    if all(t in normalise(item.get("provider")) for t in terms):
        return 3
    return 4


def relevance_key(item, query, aliases=None):
    return bucket(item, query, aliases), normalise(item.get("title")), item["id"]


def register_sql(db, query, aliases):
    # Payloads stay in SQLite; only the final bounded window is materialized.
    db.create_function("search_normalise", 1, normalise, deterministic=True)
    db.create_function(
        "relevance_bucket",
        1,
        lambda payload: bucket(json.loads(payload), query, aliases),
        deterministic=True,
    )
    db.create_function(
        "relevance_title",
        1,
        lambda payload: normalise(json.loads(payload).get("title")),
        deterministic=True,
    )
