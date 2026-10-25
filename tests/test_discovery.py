"""Crawlers and people receive the same localized, source-backed public pages."""

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.robotparser import RobotFileParser

import pytest
from fastapi.testclient import TestClient

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.discovery import (
    Document,
    WEB,
    asset_path,
    canonical,
    content,
    public_paths,
    render_page,
    text_response,
)
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Service(Store(str(tmp_path / "empty.sqlite3")))))


@pytest.mark.parametrize("path", public_paths())
@pytest.mark.parametrize("lang", ["en", "zh-Hant"])
def test_pages_are_localized_before_javascript(client, path, lang):
    response = client.get(path + "?lang=" + lang)
    assert response.status_code == 200
    assert response.headers["content-language"] == lang
    doc = Document(response.text)
    nodes = list(doc.elements())
    assert next(n for n in nodes if n.tag == "html").attrs["lang"] == lang
    assert next(n for n in nodes if n.tag == "title").children == [
        content()["pages"][path][lang]["title"]
    ]
    assert [n.attrs["href"] for n in nodes if n.attrs.get("rel") == "canonical"] == [
        canonical(path, lang)
    ]
    alternates = {
        n.attrs["hreflang"]: n.attrs["href"]
        for n in nodes
        if n.attrs.get("hreflang") and n.tag == "link"
    }
    assert alternates == {
        "en": canonical(path),
        "zh-Hant": canonical(path, "zh-Hant"),
        "x-default": canonical(path),
    }
    description = [
        n.attrs["content"] for n in nodes if n.attrs.get("name") == "description"
    ]
    assert description == [content()["pages"][path][lang]["description"]]
    schema = json.loads(
        next(n for n in nodes if n.attrs.get("type") == "application/ld+json").children[
            0
        ]
    )
    assert any(
        n.get("url") == canonical(path, lang) and n.get("inLanguage") == lang
        for n in schema["@graph"]
    )
    if path in {"/", "/connect", "/demo", "/plates", "/sources"}:
        active = [
            n for n in nodes if "data-page" in n.attrs and "hidden" not in n.attrs
        ]
        assert len(active) == 1
        expected = {
            "/": "home",
            "/connect": "connect",
            "/demo": "explore",
            "/plates": "plates",
            "/sources": "sources",
        }
        assert active[0].attrs["data-page"] == expected[path]
    if path.startswith("/guides/"):
        assert (
            content()["pages"][path][lang]["sections"][0]["paragraphs"][0]
            in response.text
        )


def test_sitemap_only_lists_canonical_indexable_pages_with_reciprocal_languages(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    root = ET.fromstring(response.text)
    ns = {
        "sm": "http://www.sitemaps.org/schemas/sitemap/0.9",
        "x": "http://www.w3.org/1999/xhtml",
    }
    entries = root.findall("sm:url", ns)
    expected = {
        canonical(p, lang)
        for p, data in content()["pages"].items()
        if not data.get("noindex")
        for lang in ("en", "zh-Hant")
    }
    assert {n.find("sm:loc", ns).text for n in entries} == expected
    assert len(entries) == len(expected) == 28
    for entry in entries:
        assert len(entry.findall("x:link", ns)) == 3
        for link in entry.findall("x:link", ns):
            assert link.attrib["href"] in expected


def test_query_urls_do_not_create_indexable_pages_or_echo_private_input(client):
    response = client.get(
        "/coverage?q=%3Cscript%3Eprivate%3C/script%3E&access=all&lang=zh-Hant"
    )
    assert response.headers["x-robots-tag"] == "noindex, follow"
    assert '<meta name="robots" content="noindex, follow">' in response.text
    assert "private" not in response.text and "<script>" not in response.text
    assert 'href="https://mcp.hk/coverage?lang=zh-Hant"' in response.text
    assert (
        client.get("/coverage?utm_source=test")
        .headers["x-robots-tag"]
        .startswith("index")
    )
    alias = client.get("/data?lang=zh-Hant&q=weather", follow_redirects=False)
    assert (
        alias.status_code == 308
        and alias.headers["location"] == "/coverage?lang=zh-Hant&q=weather"
    )


def test_faq_schema_matches_visible_answers_and_has_no_unverified_claims():
    for lang in ("en", "zh-Hant"):
        html = render_page("/", lang)
        nodes = list(Document(html).elements())
        data = json.loads(
            next(
                n.children[0]
                for n in nodes
                if n.attrs.get("type") == "application/ld+json"
            )
        )
        faq = next(n for n in data["@graph"] if n["@type"] == "FAQPage")
        for item in faq["mainEntity"]:
            assert any(n.tag == "h3" and n.children == [item["name"]] for n in nodes)
            assert any(
                n.tag == "p" and n.children == [item["acceptedAnswer"]["text"]]
                for n in nodes
            )
        assert not any("aggregateRating" in n or "review" in n for n in data["@graph"])


def test_robots_allow_search_and_answer_crawlers_but_exclude_operations(client):
    response = client.get("/robots.txt")
    robot = RobotFileParser()
    robot.parse(response.text.splitlines())
    for agent in (
        "Googlebot",
        "bingbot",
        "OAI-SearchBot",
        "PerplexityBot",
        "Claude-SearchBot",
    ):
        assert robot.can_fetch(
            agent, "https://mcp.hk/guides/data-sources-and-freshness"
        )
        assert not robot.can_fetch(agent, "https://mcp.hk/__ops/status")
        assert not robot.can_fetch(agent, "https://mcp.hk/api/v1/resources")
    assert robot.site_maps() == ["https://mcp.hk/sitemap.xml"]
    llms = client.get("/llms.txt")
    assert (
        llms.status_code == 200
        and "Catalogue inclusion does not mean every resource is queryable" in llms.text
    )


def test_static_edge_build_matches_self_hosted_renderer():
    root = Path(__file__).resolve().parents[1]
    subprocess.run(
        [sys.executable, "scripts/build_discovery.py"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    routes = json.loads((root / "deploy/cloudflare/discovery-routes.json").read_text())
    for path in public_paths():
        for lang in ("en", "zh-Hant"):
            assert routes[path][lang] == asset_path(path, lang)
            assert (
                WEB / asset_path(path, lang).lstrip("/")
            ).read_text() == render_page(path, lang)
    for path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
        assert (WEB / path.lstrip("/")).read_text() == text_response(path)[0]


def test_company_explorer_is_bilingual_and_query_state_is_not_indexed(client):
    for lang, heading in [("en", "Company archive"), ("zh-Hant", "公司歷史資料")]:
        response = client.get("/companies", params={"lang": lang})
        assert response.status_code == 200 and heading in response.text
        assert 'id="company-search"' in response.text
        assert 'id="company-snapshot-download"' in response.text
        assert "/assets/companies.js" in response.text
    response = client.get("/companies?entity=341&version=archive-v1")
    assert response.headers["x-robots-tag"] == "noindex, follow"
    assert '<meta name="robots" content="noindex, follow">' in response.text
