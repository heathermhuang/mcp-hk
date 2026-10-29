"""Documentation localization and labels do not change the public API contract."""

import json

import pytest
from fastapi.testclient import TestClient

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.discovery import Document, WEB
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.mark.parametrize("lang", ["en", "zh-Hant"])
def test_docs_localize_before_javascript_with_no_inline_scripts(tmp_path, lang):
    client = TestClient(create_app(Service(Store(str(tmp_path / "docs.sqlite3")))))
    response = client.get("/docs", params={"lang": lang})
    assert response.status_code == 200
    assert response.headers["content-language"] == lang
    nodes = list(Document(response.text).elements())
    assert next(n for n in nodes if n.tag == "html").attrs["lang"] == lang
    assert any(n.attrs.get("id") == "docs-first-code" for n in nodes)
    assert (
        "data.population" in response.text and "data.referencePeriod" in response.text
    )
    strings = json.loads(
        (WEB / "translations.js").read_text().split("=", 1)[1].strip().rstrip(";")
    )["en" if lang == "en" else "zh"]
    assert any(n.children == [strings["docsHero"]] for n in nodes if n.tag == "h1")
    assert any(
        n.attrs.get("href") == "/guides/hong-kong-open-data-api?lang=" + lang
        for n in nodes
    )
    assert not any(n.tag == "script" and "src" not in n.attrs for n in nodes)
    assert "script-src 'self'" in response.headers["content-security-policy"]
    assert not any(n.attrs.get("src") == "/assets/swagger-ui-bundle.js" for n in nodes)
    filtered = client.get("/docs", params={"lang": lang, "q": "private-docs-query"})
    assert filtered.headers["x-robots-tag"] == "noindex, follow"
    assert "private-docs-query" not in filtered.text
    assert client.get("/redoc", follow_redirects=False).headers["location"] == "/docs"


def test_documentation_labels_cover_every_configured_operation(tmp_path, monkeypatch):
    monkeypatch.setenv("WEBB_SDI_ARCHIVE_ENABLED", "true")
    monkeypatch.setenv("HKEX_DAILY_ENABLED", "true")
    spec = create_app(Service(Store(str(tmp_path / "configured.sqlite3")))).openapi()
    labels = json.loads((WEB / "api-docs-labels.json").read_text())
    operations = {
        method.upper() + " " + path
        for path, item in spec["paths"].items()
        for method in item
        if method
        in {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    }
    assert operations <= labels.keys()
    assert all(
        set(row) == {"en", "zh-Hant"} and all(row.values()) for row in labels.values()
    )
    assert not any(path.startswith("/__ops") for path in spec["paths"])
