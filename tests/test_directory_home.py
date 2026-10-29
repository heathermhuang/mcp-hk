"""Directory discovery preserves provenance and orders every provider equally."""

import json

import pytest
from fastapi.testclient import TestClient

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.discovery import Document, WEB, dataset_families, render_page
from mcp_open_data_hk.services import DomainError, Service
from mcp_open_data_hk.storage import Store


@pytest.mark.parametrize(
    "provider",
    [
        "all",
        "government",
        "independent",
        "independent_or_public_corporation",
        "unclassified",
    ],
)
def test_title_pages_merge_sources_and_connected_entries_before_pagination(
    tmp_path, provider
):
    service = Service(Store(str(tmp_path / "directory.sqlite3")))
    catalogue = service.resources.catalogue
    rows = [
        {"id": str(i), "title": title, "providerType": kind}
        for i, (title, kind) in enumerate(
            [
                ("Zulu", "independent"),
                ("Public corporation", "independent_or_public_corporation"),
                ("Alpha", "government"),
                ("Hong Kong addresses", "government"),
                ("Beta", "unclassified"),
                ("alpha", "independent"),
                ("Éducation", "government"),
            ]
        )
    ]
    catalogue.publish(rows, [], {})
    result = catalogue.search(order="title", provider=provider, limit=100)
    lower = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
    assert result["items"] == sorted(
        result["items"], key=lambda d: (d["title"].translate(lower), d["id"])
    )
    if provider != "all":
        assert all(d["providerType"] == provider for d in result["items"])
    for limit in [1, 2, 5]:
        pages = [
            catalogue.search(
                order="title", provider=provider, limit=limit, offset=offset
            )
            for offset in range(0, result["total"], limit)
        ]
        assert [d["id"] for p in pages for d in p["items"]] == [
            d["id"] for d in result["items"]
        ]
        assert pages[-1]["nextOffset"] is None
    with TestClient(create_app(service)) as client:
        http = client.get(
            "/api/v1/catalogue/datasets",
            params={"order": "title", "provider": provider},
        ).json()
        assert http["items"] == result["items"]
        assert (
            client.get("/api/v1/catalogue/datasets?provider=promoted").status_code
            == 400
        )
    assert catalogue.search(q="Alpha", order="title", access="sources")["total"] == 2
    assert catalogue.search(q="%", order="title")["total"] == 0
    for kwargs in [{"provider": "promoted"}, {"order": "sponsored"}]:
        with pytest.raises(DomainError, match="Invalid search"):
            catalogue.search(**kwargs)


@pytest.mark.parametrize("lang", ["en", "zh-Hant"])
def test_directory_is_server_rendered_with_every_family_and_broad_subjects(lang):
    nodes = list(Document(render_page("/", lang)).elements())
    topics = [n for n in nodes if "data-topic-query" in n.attrs]
    assert len(topics) == 12
    assert [n.children[0] for n in topics] == [
        row[lang] + " ↗" for row in json.loads((WEB / "topics.json").read_text())
    ]
    for family in dataset_families():
        assert any(n.attrs.get("id") == "dataset-" + family["id"] for n in nodes)
        assert family["limits"][lang] in render_page("/", lang)
    assert any(n.attrs.get("action") == "/coverage" and n.tag == "form" for n in nodes)
    assert any(n.attrs.get("id") == "directory-access" for n in nodes)
    assert not any("data-concept" in n.attrs for n in nodes)
