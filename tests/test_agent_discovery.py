"""Published capability metadata and negotiated content describe real public reads."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk import discovery
from mcp_open_data_hk.agent_discovery import agent_documents, prefers_markdown
from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def app(tmp_path):
    return create_app(Service(Store(str(tmp_path / "empty.sqlite3"))))


@pytest.mark.parametrize(
    "accept,markdown",
    [
        ("", False),
        ("*/*", False),
        ("text/html,application/xhtml+xml,*/*;q=0.8", False),
        ("text/markdown", True),
        ("TEXT/MARKDOWN; charset=utf-8", True),
        ("text/markdown;q=0,*/*;q=1", False),
        ("text/markdown;q=0.4,text/html;q=1", False),
        ("text/html;q=0.4,text/markdown;q=1", True),
        ("text/*;q=1,text/markdown;q=0.5", False),
        ("text/markdown;q=1,text/html;q=1", True),
        ("text/markdown;q=bogus", False),
    ],
)
def test_negotiation_respects_explicit_media_ranges_and_quality(app, accept, markdown):
    assert prefers_markdown(accept) is markdown
    response = TestClient(app).get("/", headers={"Accept": accept})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(
        "text/markdown" if markdown else "text/html"
    )
    assert "Accept" in {value.strip() for value in response.headers["vary"].split(",")}
    assert 'rel="api-catalog"' in response.headers["link"]


def test_markdown_preserves_selected_locale_and_excludes_hidden_app_screens(app):
    client = TestClient(app)
    home = client.get("/", headers={"Accept": "text/markdown"})
    assert "Canonical: https://mcp.hk/" in home.text
    assert discovery.content()["faq"]["en"][0][0] in home.text
    assert (
        '[mcp_servers."mcp.hk"]' not in home.text
    )  # Hidden Connect panel is not homepage content.
    connect = client.get("/connect.md?lang=zh-Hant")
    assert connect.headers["content-language"] == "zh-Hant"
    assert connect.headers["x-robots-tag"] == "noindex, follow"
    assert (
        '[mcp_servers."mcp.hk"]' in connect.text
        and "https://mcp.hk/mcp" in connect.text
    )
    assert "lang=zh-Hant" in connect.text and "如何" not in home.text
    coverage = client.get(
        "/coverage?q=UNIQUE-PRIVATE-QUERY-471", headers={"Accept": "text/markdown"}
    )
    assert "UNIQUE-PRIVATE-QUERY-471" not in coverage.text
    assert coverage.headers["x-robots-tag"] == "noindex, follow"
    assert (
        client.get("/privacy", headers={"Accept": "text/markdown"})
        .headers["content-type"]
        .startswith("text/html")
    )
    assert client.get("/unknown.md").status_code == 404


def test_public_catalogs_and_skill_integrity_do_not_advertise_fake_auth(app):
    client = TestClient(app)
    for path, (body, media) in agent_documents(discovery).items():
        response = client.get(path)
        assert response.status_code == 200 and response.text == body
        assert response.headers["content-type"].startswith(media)
        assert response.headers["access-control-allow-origin"] == "*"
        assert client.head(path).content == b""
    catalog = client.get("/.well-known/api-catalog").json()
    assert len(catalog["linkset"]) == 2
    assert all(
        entry["service-desc"][0]["href"].startswith("https://mcp.hk/")
        for entry in catalog["linkset"]
    )
    skills = client.get("/.well-known/agent-skills/index.json").json()
    artifact = client.get(skills["skills"][0]["url"].replace("https://mcp.hk", ""))
    assert (
        skills["skills"][0]["digest"]
        == "sha256:" + hashlib.sha256(artifact.content).hexdigest()
    )
    ard = client.get("/.well-known/ai-catalog.json").json()
    assert all(
        bool(item.get("url")) != bool(item.get("data")) for item in ard["entries"]
    )
    assert all(
        item["identifier"].startswith("urn:air:mcp.hk:") for item in ard["entries"]
    )
    assert "Authentication method: none" in client.get("/auth.md").text
    assert client.get("/.well-known/oauth-authorization-server").status_code == 404
    assert client.get("/.well-known/oauth-protected-resource").status_code == 404
    assert client.get("/__ops/status").status_code == 404
    assert "Expanded documentation" in client.get("/llms.txt").text
    assert (
        "Canonical: https://mcp.hk/guides/hong-kong-open-data-api"
        in client.get("/llms-full.txt").text
    )


@pytest.mark.asyncio
async def test_mcp_card_matches_real_initialization(app):
    card = TestClient(app).get("/.well-known/mcp/server-card.json").json()
    async with Client(app.state.mcp) as client:
        initialized = await client.initialize()
        assert card["serverInfo"]["name"] == initialized.serverInfo.name
        assert card["serverInfo"]["version"] == initialized.serverInfo.version
        assert card["capabilities"][
            "tools"
        ] == initialized.capabilities.tools.model_dump(exclude_none=True)
    assert card["transport"] == {
        "type": "streamable-http",
        "endpoint": "https://mcp.hk/mcp",
    }


def test_content_signals_publish_grounding_preference_without_changing_crawl_boundaries(
    app,
):
    robots = TestClient(app).get("/robots.txt").text
    assert "Content-Signal: search=yes, ai-input=yes, ai-train=no" in robots
    assert "Disallow: /__ops/" in robots and "Disallow: /mcp" in robots
    assert "Agentmap: https://mcp.hk/.well-known/ai-catalog.json" in robots
    html = TestClient(app).get("/").text
    assert "/assets/webmcp.js" in html and 'rel="ai-catalog"' in html


def test_generated_agent_assets_match_the_self_hosted_documents():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/build_discovery.py"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    routes = json.loads((root / "deploy/cloudflare/agent-routes.json").read_text())
    for path, (body, media) in agent_documents(discovery).items():
        assert routes[path]["contentType"] == media
        assert (discovery.WEB / routes[path]["asset"].lstrip("/")).read_text() == body
    pages = json.loads((root / "deploy/cloudflare/discovery-routes.json").read_text())
    from mcp_open_data_hk.agent_discovery import markdown_document

    for path, variants in pages.items():
        for key, asset in variants.items():
            if key.endswith("-markdown"):
                lang = "zh-Hant" if key.startswith("zh-Hant") else "en"
                assert (
                    discovery.WEB / asset.lstrip("/")
                ).read_text() == markdown_document(
                    discovery, path, lang, "-filtered-" in key
                )
