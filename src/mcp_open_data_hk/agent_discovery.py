"""Public, read-only agent discovery. No new authentication or agent protocols."""

import hashlib
import json
import re
from functools import lru_cache
from urllib.parse import urljoin

ORIGIN = "https://mcp.hk"
LINKS = ", ".join(
    [
        f'<{ORIGIN}/.well-known/api-catalog>; rel="api-catalog"; type="application/linkset+json"',
        f'<{ORIGIN}/openapi.json>; rel="service-desc"; type="application/json"',
        f'<{ORIGIN}/guides>; rel="service-doc"; type="text/html"',
        f'<{ORIGIN}/.well-known/mcp/server-card.json>; rel="describedby"; type="application/json"',
        f'<{ORIGIN}/llms.txt>; rel="describedby"; type="text/plain"',
    ]
)


def prefers_markdown(accept):
    """Honor exact ranges and q=0; wildcards alone retain the HTML default."""
    ranges = []
    for part in (accept or "").lower().split(","):
        pieces = [piece.strip() for piece in part.split(";")]
        quality = 1.0
        for parameter in pieces[1:]:
            if parameter.startswith("q="):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0
        if not 0 <= quality <= 1:
            quality = 0
        ranges.append((pieces[0], quality))

    def effective(media):
        for candidate in (media, "text/*", "*/*"):
            matches = [q for name, q in ranges if name == candidate]
            if matches:
                return max(matches)
        return 0

    return any(name == "text/markdown" for name, _ in ranges) and (
        effective("text/markdown") > 0
        and effective("text/markdown") >= effective("text/html")
    )


def markdown_path(path):
    return "/index.md" if path == "/" else path + ".md"


def markdown_document(discovery, path, lang="en", filtered=False):
    """Render the same visible article, excluding other hidden app screens."""
    doc = discovery.Document(discovery.render_page(path, lang, filtered))
    main = next(n for n in doc.elements() if n.tag == "main")

    def render(node):
        if isinstance(node, str):
            return re.sub(r"\s+", " ", node)
        if "hidden" in node.attrs or node.attrs.get("aria-hidden") == "true":
            return ""
        if node.tag in {
            "script",
            "style",
            "nav",
            "footer",
            "form",
            "button",
            "input",
            "select",
            "textarea",
        }:
            return ""
        if "aria-live" in node.attrs or node.attrs.get("role") == "status":
            return ""
        if node.tag == "br":
            return "\n"
        if node.tag == "pre":

            def raw(element):
                return (
                    element
                    if isinstance(element, str)
                    else "".join(raw(c) for c in element.children)
                )

            return "\n\n```\n" + raw(node).strip() + "\n```\n\n"
        text = "".join(render(child) for child in node.children).strip()
        if not text:
            return ""
        if re.fullmatch("h[1-6]", node.tag):
            return "\n\n" + "#" * int(node.tag[1]) + " " + text + "\n\n"
        if node.tag == "a" and node.attrs.get("href"):
            return "[" + text + "](" + urljoin(ORIGIN, node.attrs["href"]) + ") "
        if node.tag == "li":
            return "\n- " + text + "\n"
        if node.tag in {
            "p",
            "section",
            "article",
            "div",
            "aside",
            "ol",
            "ul",
            "details",
        }:
            return "\n\n" + text + "\n\n"
        return text + " "

    body = re.sub(r"\n[ \t]+", "\n", render(main))
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body + "\n\nCanonical: " + discovery.canonical(path, lang) + "\n"


@lru_cache(maxsize=1)
def agent_documents(discovery):
    """Fixed, inspectable documents describing only implemented capabilities."""
    card = {
        "version": "1.0",
        "protocolVersion": "2025-06-18",
        "serverInfo": {
            "name": "mcp.hk",
            "title": "Hong Kong public data",
            "version": "2.14.7",
        },
        "description": "Public read-only Hong Kong data over MCP. Catalogue coverage is not universal query access. Preserve original provenance, warnings and reference periods.",
        "documentationUrl": ORIGIN + "/connect",
        "transport": {"type": "streamable-http", "endpoint": ORIGIN + "/mcp"},
        "capabilities": {"tools": {"listChanged": True}},
    }
    skill = """---
name: hong-kong-public-data
description: Discover Hong Kong datasets, inspect supported records and cite original providers through the public read-only mcp.hk MCP server or HTTP API.
---
# Hong Kong public data

Connect a Streamable HTTP MCP client to https://mcp.hk/mcp. No mcp.hk account,
API key, OAuth flow or registration is required. Allow 120 seconds for startup.
Your AI client or model provider may charge separately. Request limits apply.

1. Discover datasets with hk_catalogue_search. For HTTP use:
   GET https://mcp.hk/api/v1/catalogue/datasets?q=public%20holidays&access=all&limit=5
2. List source resources with hk_dataset_resources. Inspect a selected source
   with hk_resource_schema before calling hk_resource_query with a bounded limit.
   Some sources require a record path, worksheet, layer or source parameters.
3. Preserve source URLs, attribution, reference periods, warnings, stale flags
   and snapshot identifiers. Catalogue discovery is not a claim that every
   resource is queryable or semantically qualified. Do not turn source failure
   into an empty dataset. Source-read time is not observation time.

Use hk_data_packs for the supported packs. Plate.hk historical auction results
are not current valuations, ownership or availability. SeeHouse asking prices
are not completed transactions. District statistics apply to the whole district.
Do not request or expose operator credentials. Public read tools cannot modify
source records. Provider terms remain authoritative; MIT covers software only.

Reference: https://mcp.hk/openapi.json
Sources and freshness: https://mcp.hk/guides/data-sources-and-freshness
Client setup: https://mcp.hk/connect
"""
    skill_path = "/.well-known/agent-skills/hong-kong-public-data/SKILL.md"
    skills = {
        "$schema": "https://schemas.agentskills.io/discovery/0.2.0/schema.json",
        "skills": [
            {
                "name": "hong-kong-public-data",
                "type": "skill-md",
                "description": "Discover and query supported Hong Kong public data with original citations and explicit access/freshness limits.",
                "url": ORIGIN + skill_path,
                "digest": "sha256:" + hashlib.sha256(skill.encode()).hexdigest(),
            }
        ],
    }
    catalog = {
        "linkset": [
            {
                "anchor": ORIGIN + "/api/v1/",
                "service-desc": [
                    {"href": ORIGIN + "/openapi.json", "type": "application/json"}
                ],
                "service-doc": [
                    {
                        "href": ORIGIN + "/guides/hong-kong-open-data-api",
                        "type": "text/html",
                    }
                ],
                "status": [{"href": ORIGIN + "/healthz", "type": "application/json"}],
            },
            {
                "anchor": ORIGIN + "/mcp",
                "service-desc": [
                    {
                        "href": ORIGIN + "/.well-known/mcp/server-card.json",
                        "type": "application/json",
                    }
                ],
                "service-doc": [{"href": ORIGIN + "/connect", "type": "text/html"}],
            },
        ]
    }
    ard = {
        "specVersion": "1.0",
        "host": {"displayName": "mcp.hk", "identifier": ORIGIN + "/#organization"},
        "entries": [
            {
                "identifier": "urn:air:mcp.hk:server:public-data",
                "displayName": "Hong Kong public data MCP",
                "type": "application/mcp-server-card+json",
                "url": ORIGIN + "/.well-known/mcp/server-card.json",
                "representativeQueries": [
                    "Find Hong Kong public holiday data with source links",
                    "查詢香港公共數據並保留原始來源",
                ],
            },
            {
                "identifier": "urn:air:mcp.hk:api:public-data",
                "displayName": "Hong Kong public data HTTP API",
                "type": "application/vnd.oai.openapi+json",
                "url": ORIGIN + "/openapi.json",
                "representativeQueries": [
                    "Search Hong Kong data catalogues and inspect source schemas",
                    "搜尋香港數據目錄及查看來源欄位",
                ],
            },
        ],
    }
    auth = """# mcp.hk auth.md

## Agent audience and access
Public data agents can use https://mcp.hk/mcp (Streamable HTTP) or the HTTP API.
Authentication method: none. Account registration and credential provisioning:
not required and not offered for public reads. There is no public registration,
claim, token or OAuth endpoint to call. Do not invent a sign-up step or send an
Authorization header. No API key, bearer token or OAuth scope is needed.

## Public interfaces
- MCP: https://mcp.hk/mcp
- HTTP contracts: https://mcp.hk/openapi.json
- Connection guide: https://mcp.hk/connect
- Rate limits: https://mcp.hk/api/v1/limits

## Boundaries
These are read-only public-data interfaces. Resource query/schema POST requests
read data; they do not modify provider records. Request counters and caches are
maintained by the service. Provider availability and terms still apply. Respect
429 responses and Retry-After. A cold start can need a 120-second client window.

Operator maintenance endpoints are private and are not agent tools. Never ask
for, infer, store or transmit operator credentials. Optional browser analytics
consent is not required for data access. Source failure is not an empty result.
"""
    documents = {
        "/.well-known/mcp/server-card.json": (
            json.dumps(card, ensure_ascii=False, indent=2) + "\n",
            "application/json",
        ),
        "/.well-known/api-catalog": (
            json.dumps(catalog, indent=2) + "\n",
            "application/linkset+json",
        ),
        "/.well-known/agent-skills/index.json": (
            json.dumps(skills, indent=2) + "\n",
            "application/json",
        ),
        skill_path: (skill, "text/markdown"),
        "/.well-known/ai-catalog.json": (
            json.dumps(ard, ensure_ascii=False, indent=2) + "\n",
            "application/json",
        ),
        "/auth.md": (auth, "text/markdown"),
    }
    full = discovery.text_response("/llms.txt")[0] + "\n# Expanded documentation\n\n"
    full += "\n\n".join(
        markdown_document(discovery, path)
        for path, page in discovery.content()["pages"].items()
        if not page.get("noindex")
    )
    documents["/llms-full.txt"] = (full, "text/plain")
    return documents
