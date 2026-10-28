"""Public navigation and discovery must describe the same source views."""

import json
import re
from urllib.parse import parse_qsl, urlsplit

import pytest

from mcp_open_data_hk.connected import entries, matching
from mcp_open_data_hk.dataset_content import families
from mcp_open_data_hk.discovery import (
    Document,
    public_paths,
    render_page,
    text_response,
)
from mcp_open_data_hk.sources import available_packs
from mcp_open_data_hk.contracts import (
    CompanySearchQuery,
    PlateSearchQuery,
    PropertySearchQuery,
    RestaurantQuery,
)
from mcp_open_data_hk.hkex_daily import DailyQuery
from mcp_open_data_hk.webb_sdi import IssuerQuery


@pytest.mark.parametrize("lang", ["en", "zh-Hant"])
def test_every_family_has_a_reachable_directory_entry_and_reading_contract(lang):
    rows = families()
    assert len({r["id"] for r in rows}) == 13
    html = render_page("/datasets", lang)
    nodes = list(Document(html).elements())
    for row in rows:
        assert row["title"][lang] in html
        assert row["limits"][lang] in html
        assert row["dates"][lang] in html
        assert row["download"][lang] in html
        assert urlsplit(row["path"]).path in public_paths()
        assert urlsplit(row["statusPage"]).path in public_paths()
        assert any(n.attrs.get("id") == "dataset-" + row["id"] for n in nodes)
    assert ("remains incomplete" if lang == "en" else "須待所有必要關卡通過") in html
    home = render_page("/", lang)
    assert all(row["title"][lang] in home for row in rows)
    for path in public_paths():
        nav = next(
            n for n in Document(render_page(path, lang)).elements() if n.tag == "nav"
        )
        assert any(
            n.tag == "a" and urlsplit(n.attrs.get("href", "")).path == "/datasets"
            for n in nav.children
            if not isinstance(n, str)
        )
    assert "/datasets" in text_response("/llms.txt")[0]


def test_optional_archive_discovery_respects_existing_configuration(monkeypatch):
    monkeypatch.delenv("MCP_HK_CURATED_ORIGIN", raising=False)
    monkeypatch.delenv("MCP_HK_CURATED_TOKEN", raising=False)
    assert not {"sfc_archive", "webb_sdi", "hkex_daily"} & {
        p["id"] for p in available_packs()
    }
    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://archive.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "fixture-token-" + "x" * 32)
    monkeypatch.setenv("MCP_HK_WEBB_SDI_ENABLED", "true")
    monkeypatch.setenv("MCP_HK_HKEX_DAILY_ENABLED", "true")
    for term, key in [
        ("SFC", "sfc_archive"),
        ("證監會", "sfc_archive"),
        ("HKEX", "hkex_daily"),
        ("權益", "webb_sdi"),
    ]:
        assert key in {r["packId"] for r in matching(term)}
    copies = {r["id"]: r for r in families()}
    for entry in entries():
        assert entry["title"] == copies[entry["packId"]]["title"]["en"]
        assert entry["titleZhHant"] == copies[entry["packId"]]["title"]["zh-Hant"]
        assert "hk_sfc_verify" not in entry["access"]["tools"]
    monkeypatch.setenv("MCP_HK_WEBB_SDI_ENABLED", "false")
    assert "webb_sdi" not in {p["id"] for p in available_packs()}


@pytest.mark.parametrize(
    "key,contract",
    [
        ("company_registry", CompanySearchQuery),
        ("enigma", CompanySearchQuery),
        ("sfc_archive", CompanySearchQuery),
        ("hkex_daily", DailyQuery),
        ("webb_sdi", IssuerQuery),
        ("restaurants", RestaurantQuery),
        ("platehk", PlateSearchQuery),
        ("seehouse", PropertySearchQuery),
    ],
)
def test_examples_use_the_actual_http_and_mcp_parameter_contracts(key, contract):
    row = next(r for r in families() if r["id"] == key)
    http_args = dict(parse_qsl(urlsplit(row["httpExample"]).query))
    mcp_args = json.loads(re.fullmatch(r"\w+\((.*)\)", row["mcpExample"])[1])
    assert contract.model_validate(http_args) == contract.model_validate(mcp_args)
