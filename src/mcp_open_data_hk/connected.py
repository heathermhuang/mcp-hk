"""First-class discovery of connected query services; never a government mirror."""

import unicodedata

from .sources import SOURCES, available_packs
from .dataset_content import family


def entries():
    result = []
    for pack in available_packs():
        key = pack["id"]
        copy = family(key)
        result.append(
            {
                **pack,
                "id": "mcp:" + key,
                "packId": key,
                "title": copy["title"]["en"],
                "titleZhHant": copy["title"]["zh-Hant"],
                "description": copy["question"]["en"] + " " + copy["limits"]["en"],
                "descriptionZhHant": copy["question"]["zh-Hant"]
                + " "
                + copy["limits"]["zh-Hant"],
                "keywords": copy["keywords"],
                "entryKind": "connected_service",
                "catalogue": "mcp.hk",
                "capability": "connected_query",
                "sourceUrl": SOURCES[key]["sourceUrl"],
                "attribution": SOURCES[key]["attribution"],
                "action": {
                    "url": copy["path"],
                    "label": copy["action"]["en"],
                    "labelZhHant": copy["action"]["zh-Hant"],
                },
                "access": {
                    "http": pack["http"],
                    "tools": pack["tools"],
                    "scope": "Connected query interface; source freshness is checked separately.",
                },
            }
        )
    return result


def normalise(text):
    return unicodedata.normalize("NFKC", text).casefold().strip()


def matching(q):
    terms = normalise(q).split()
    return [
        entry
        for entry in entries()
        if all(
            t
            in normalise(
                " ".join(
                    str(entry.get(k, ""))
                    for k in (
                        "id",
                        "title",
                        "titleZhHant",
                        "provider",
                        "description",
                        "descriptionZhHant",
                        "keywords",
                    )
                )
            )
            for t in terms
        )
    ]


def get(dataset_id):
    return next((e for e in entries() if e["id"] == dataset_id), None)
