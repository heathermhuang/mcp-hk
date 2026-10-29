"""Python and generated Worker HTML agree; private queries never enter metadata."""

import json
from urllib.parse import unquote, urlsplit

import pytest
from fastapi.testclient import TestClient

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.discovery import Document, WEB, dataset_families, render_page
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.mark.parametrize("lang", ["en", "zh-Hant"])
def test_playground_static_locale_noscript_metadata_and_filter_policy(tmp_path, lang):
    app = create_app(Service(Store(str(tmp_path / "data.sqlite3"))))
    with TestClient(app) as client:
        page = client.get("/playground", params={"lang": lang})
        assert page.status_code == 200
        assert page.text == render_page("/playground", lang)
        asset = WEB / "discovery" / lang / "playground.html"
        assert asset.read_text() == page.text
        assert page.headers["content-language"] == lang
        assert "noindex" not in page.headers["x-robots-tag"]
        private = client.get(
            "/playground", params={"lang": lang, "q": "PRIVATE_FIXTURE_QUERY"}
        )
        assert "noindex" in private.headers["x-robots-tag"]
        assert "PRIVATE_FIXTURE_QUERY" not in private.text
        assert (
            private.text
            == (WEB / "discovery" / lang / "playground-filtered.html").read_text()
        )
    nodes = list(Document(page.text).elements())
    assert any(n.tag == "noscript" for n in nodes)
    assert any(
        n.attrs.get("rel") == "canonical" and "/playground" in n.attrs["href"]
        for n in nodes
    )
    assert len([n for n in nodes if n.tag == "main"]) == 1
    assert not any(n.tag == "iframe" for n in nodes)
    for family in dataset_families():
        assert any(n.attrs.get("id") == "dataset-" + family["id"] for n in nodes)
        assert any(
            n.tag == "a"
            and urlsplit(n.attrs.get("href", "")).path == urlsplit(family["path"]).path
            for n in nodes
        )
    directory = list(Document(render_page("/datasets", lang)).elements())
    recipes = [
        json.loads(unquote(urlsplit(n.attrs["href"]).fragment.removeprefix("p=")))
        for n in directory
        if n.tag == "a"
        and n.attrs.get("href", "").startswith("/playground?")
        and urlsplit(n.attrs["href"]).fragment.startswith("p=")
    ]
    assert {r["family"] for r in recipes} == {f["id"] for f in dataset_families()}
    assert all(r["lang"] == lang and r["v"] == 1 for r in recipes)
