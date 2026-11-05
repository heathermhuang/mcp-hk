"""Identify inventoried access protocols and shared reader contracts."""

from urllib.parse import parse_qs, urlsplit

from .contracts import DomainError

HKMA_PAGING_CONTRACT = "hkma-pages-2"


def protocol(resource):
    fmt = resource.get("format", "").upper()
    if fmt in {"WFS", "WMS"}:
        return fmt
    url = urlsplit(resource.get("url", ""))
    query = {k.lower(): v for k, v in parse_qs(url.query).items()}
    for name in ("WFS", "WMS"):
        if url.path.rstrip("/").lower().endswith("/" + name.lower() + "server") or any(
            v.upper() == name for v in query.get("service", [])
        ):
            return name
    return None


def pinned_feature_type(resource):
    if protocol(resource) != "WFS":
        return ""
    query = {k.lower(): v for k, v in parse_qs(urlsplit(resource["url"]).query).items()}
    if [v.lower() for v in query.get("request", [])] != ["getfeature"]:
        return ""
    names = query.get("typenames", query.get("typename", []))
    if (
        len(names) != 1
        or "," in names[0]
        or set(query)
        - {"service", "request", "typename", "typenames", "version", "outputformat"}
    ):
        raise DomainError(
            "UNSUPPORTED_API",
            "Inventoried WFS query scope needs a reviewed adapter; it cannot be broadened",
            422,
        )
    return names[0]
