"""Shared relevance and bounded stream merge, independent of source freshness."""

import itertools
from contextlib import contextmanager
import json
import sqlite3
import re

import pytest

from mcp_open_data_hk import connected, transport
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.api import create_app
from fastapi.testclient import TestClient
from fastmcp import Client


@pytest.mark.parametrize("query", ["weather", "school", "天氣", "學校"])
def test_subject_before_gateway(tmp_path, query):
    c = Service(Store(str(tmp_path / "rank.sqlite3"))).resources.catalogue
    c.publish([{"id": "subject", "title": query, "provider": "Department"}], [], {})
    result = c.search(query)
    assert result["items"][0]["id"] == "subject"
    assert "mcp:catalogue" in [d["id"] for d in result["items"]]


@pytest.mark.parametrize("count", [0, 8, 13])
def test_global_pages_equal_oracle_and_enrich_only_visible(
    tmp_path, monkeypatch, count
):
    from mcp_open_data_hk.search_ranking import relevance_key

    c = Service(Store(str(tmp_path / "rank.sqlite3"))).resources.catalogue
    rows = [
        {"id": str(i), "title": title, "description": "school", "provider": "School"}
        for i, title in enumerate(
            ["Zulu", "school", "School locations", "A school", "Ａ school", "Beta"]
        )
    ]
    guided = [
        {"id": f"mcp:{i}", "title": f"{i} school", "description": "school"}
        for i in range(count)
    ]
    monkeypatch.setattr(connected, "entries", lambda: guided)
    c.publish(rows, [], {})
    statements = []
    connect = c.store.connect

    @contextmanager
    def traced():
        with connect() as db:
            db.set_trace_callback(statements.append)
            yield db

    monkeypatch.setattr(c.store, "connect", traced)
    calls = []
    original = c.dataset_capabilities

    def enrich(*args):
        calls.append(args[0])
        return original(*args)

    monkeypatch.setattr(c, "dataset_capabilities", enrich)
    oracle = sorted(rows + guided, key=lambda d: relevance_key(d, "school"))
    for limit in [1, 2, 5, 10]:
        pages = []
        for offset in range(0, len(oracle) + limit, limit):
            calls.clear()
            statements.clear()
            page = c.search("school", limit=limit, offset=offset)
            assert len(calls) <= limit
            windows = [
                s
                for s in statements
                if s.startswith("SELECT payload FROM inventory_datasets")
            ]
            assert len(windows) <= 1
            assert all(
                int(re.search(r" LIMIT (\d+)", s)[1]) <= limit + count for s in windows
            )
            assert page["total"] == len(oracle)
            pages.extend(d["id"] for d in page["items"])
        assert pages == [d["id"] for d in oracle]


def test_sql_adapter_and_comparator_share_policy():
    from mcp_open_data_hk.search_ranking import register_sql, relevance_key

    rows = [
        {"id": "exact", "title": "Ｓchool  DATA"},
        {"id": "missing"},
        {"id": "provider", "provider": "School data"},
        {"id": "mcp:catalogue", "packId": "catalogue", "title": "School data"},
        {"id": "alias", "title": "School locations"},
    ]
    aliases = {"alias": ["school data"]}
    for query in ["school   data", "mcp:catalogue", "catalogue", "學校", "%", "_"]:
        with sqlite3.connect(":memory:") as db:
            register_sql(db, query, aliases)
            db.execute("CREATE TABLE candidates(payload TEXT)")
            db.executemany(
                "INSERT INTO candidates VALUES(?)", [(json.dumps(d),) for d in rows]
            )
            ordered = [
                json.loads(r[0])["id"]
                for r in db.execute(
                    "SELECT payload FROM candidates ORDER BY relevance_bucket(payload), relevance_title(payload), json_extract(payload,'$.id')"
                )
            ]
        assert ordered == [
            d["id"]
            for d in sorted(rows, key=lambda d: relevance_key(d, query, aliases))
        ]


def test_bounded_merge_exhaustive():
    # Exercise arbitrary interleavings, including connected items above/below a page.
    for n in range(8):
        for mask in itertools.product([False, True], repeat=n):
            guided = [i for i in range(n) if mask[i]]
            native = [i for i in range(n) if not mask[i]]
            for limit in range(1, 5):
                for offset in range(n + 2):
                    start = max(0, offset - len(guided))
                    window = native[start : start + limit + len(guided)]
                    assert len(window) <= limit + len(guided)
                    page = sorted(guided + window)[
                        offset - start : offset - start + limit
                    ]
                    assert page == list(range(n))[offset : offset + limit]


@pytest.mark.asyncio
async def test_rank_filters_http_mcp_normalization_and_literal_matching(tmp_path):
    service = Service(Store(str(tmp_path / "parity.sqlite3")))
    c = service.resources.catalogue
    c.publish(
        [
            {"id": "weather", "title": "Weather", "providerType": "government"},
            {"id": "unicode", "title": "ＳCHOOL   DATA", "providerType": "government"},
            {"id": "literal", "title": "100%_", "provider": "Observatory"},
        ],
        [
            {
                "id": "r",
                "datasetId": "weather",
                "format": "CSV",
                "url": "https://example.gov.hk/data",
            }
        ],
        {},
    )
    app = create_app(service)
    with TestClient(app) as http:
        assert http.get("/api/v1/resources/r").json()["datasetId"] == "weather"
        assert http.get("/api/v1/resources/absent").status_code == 404
        async with Client(app.state.mcp) as mcp:
            for q in [
                "weather",
                "school data",
                "unicode",
                "Observatory",
                "%",
                "_",
                "no match",
                "mcp:catalogue",
                "catalogue",
            ]:
                for access, provider, capability, entity in [
                    ("all", "all", "all", "all"),
                    ("sources", "government", "all", "all"),
                    ("connected", "all", "all", "all"),
                    ("all", "all", "unqualified", "unqualified"),
                    ("all", "all", "records", "all"),
                    ("all", "all", "requires_selection", "school"),
                ]:
                    args = dict(
                        q=q,
                        access=access,
                        provider=provider,
                        capability=capability,
                        entityKind=entity,
                    )
                    response = http.get(
                        "/api/v1/catalogue/datasets",
                        params=args,
                        headers={"X-Test-Case": q},
                    )
                    assert response.status_code == 200
                    native = json.loads(
                        (await mcp.call_tool("hk_catalogue_search", args))
                        .content[0]
                        .text
                    )
                    assert native == response.json()
    assert c.search("school data")["items"][0]["id"] == "unicode"
    assert c.search("unicode")["items"][0]["id"] == "unicode"
    assert c.search("catalogue")["items"][0]["id"] == "mcp:catalogue"
    for q in ["%", "_"]:
        assert [d["id"] for d in c.search(q)["items"]] == ["literal"]


def test_empty_overview_retains_legacy_order_for_optional_metadata(
    tmp_path, monkeypatch
):
    c = Service(Store(str(tmp_path / "overview.sqlite3"))).resources.catalogue
    monkeypatch.setattr(
        connected, "entries", lambda: [{"id": "mcp:view", "title": "View"}]
    )
    c.publish(
        [
            {"id": "z", "title": ""},
            {"id": "b", "title": "Beta"},
            {"id": "c", "provider": "Provider"},
            {"id": "a"},
        ],
        [],
        {},
    )
    assert [d["id"] for d in c.search("")["items"]] == ["mcp:view", "z", "b", "c", "a"]


@pytest.mark.parametrize(
    "query,expected",
    [
        ("weather", "hk-hko-rss-current-weather-report"),
        ("天氣", "hk-hko-rss-current-weather-report"),
        ("school", "hk-edb-schinfo-school-location-and-information"),
        ("學校", "hk-edb-schinfo-school-location-and-information"),
    ],
)
def test_reviewed_bilingual_task_ids_without_translated_source_metadata(
    tmp_path, query, expected
):
    c = Service(Store(str(tmp_path / "tasks.sqlite3"))).resources.catalogue
    c.publish(
        [
            {
                "id": "hk-hko-rss-current-weather-report",
                "title": "Current weather report",
            },
            {
                "id": "hk-edb-schinfo-school-location-and-information",
                "title": "School Location and Information",
            },
        ],
        [],
        {},
    )
    result = c.search(query)
    assert result["items"][0]["id"] == expected
    assert result["items"][0].get("titleZhHant") is None


@pytest.fixture
def arrival_catalogue(tmp_path):
    service = Service(Store(str(tmp_path / "arrivals.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": identifier,
                "title": title,
                "providerType": "independent_or_public_corporation",
            }
            for identifier, title in (
                (transport.MTR_RAIL_DATASET, "Real-time MTR train information"),
                (
                    transport.MTR_LIGHT_RAIL_DATASET,
                    "Real-time Light Rail train information",
                ),
                (transport.MTR_BUS_DATASET, "Real-time MTR Bus Schedule"),
            )
        ],
        [],
        {},
    )
    return service


@pytest.mark.parametrize(
    "phrase, expected",
    [
        ("next train at Central", transport.MTR_RAIL_DATASET),
        ("next train at Central?", transport.MTR_RAIL_DATASET),
        (
            "When is the next Tsuen Wan line train from Central?",
            transport.MTR_RAIL_DATASET,
        ),
        ("How soon does the train arrive at Admiralty?", transport.MTR_RAIL_DATASET),
        ("next train from Mei Foo", transport.MTR_RAIL_DATASET),
        ("When does the Airport Express depart?", transport.MTR_RAIL_DATASET),
        ("中環 港鐵 到站", transport.MTR_RAIL_DATASET),
        ("中環港鐵到站？", transport.MTR_RAIL_DATASET),
        ("中環站下一班往荃灣的港鐵幾點到", transport.MTR_RAIL_DATASET),
        ("港鐵金鐘站仲有幾多分鐘到", transport.MTR_RAIL_DATASET),
        ("荃湾线下一班几点到", transport.MTR_RAIL_DATASET),
        (
            "When does the next Light Rail train arrive at Tuen Mun?",
            transport.MTR_LIGHT_RAIL_DATASET,
        ),
        ("屯門輕鐵下一班何時到站", transport.MTR_LIGHT_RAIL_DATASET),
        ("天水围轻铁实时到站", transport.MTR_LIGHT_RAIL_DATASET),
        ("When is the next MTR feeder bus?", transport.MTR_BUS_DATASET),
        ("show live arrivals for MTR buses", transport.MTR_BUS_DATASET),
        ("下一班港鐵接駁巴士幾時到", transport.MTR_BUS_DATASET),
        ("港铁巴士实时到站", transport.MTR_BUS_DATASET),
    ],
)
def test_arrival_questions_route_to_the_correct_catalogue_dataset(
    arrival_catalogue, phrase, expected
):
    catalogue = arrival_catalogue.resources.catalogue
    page = catalogue.search(phrase, limit=1, access="sources")
    assert [item["id"] for item in page["items"]] == [expected]
    assert page["total"] == 1 and page["nextOffset"] is None
    assert catalogue.search(phrase, limit=1, offset=1, access="sources")["items"] == []
    assert catalogue.search(phrase, access="connected")["sourceTotal"] == 0
    assert (
        catalogue.search(phrase, provider="government", access="sources")["items"] == []
    )


@pytest.mark.parametrize(
    "phrase",
    [
        "next flight at Central",
        "when is the next ferry from Central?",
        "next Citybus outside Central MTR station",
        "next KMB from Admiralty MTR station",
        "下一班九巴幾時到港鐵站",
        "MTR station entrances and accessibility",
        "historical MTR arrivals last week",
        "next high-speed train at West Kowloon",
        "MTR timetable and fares at Central",
        "What is the next stop on the MTR?",
        "When does the MTR train arrive at Central tomorrow?",
        "明天中環站下一班港鐵幾點到",
        "港鐵站外下一班小巴幾時到",
        "香港西九龍下一班高鐵幾點到",
        "中環去荃灣港鐵車程幾多分鐘",
    ],
)
def test_arrival_matching_does_not_admit_other_intents(arrival_catalogue, phrase):
    assert transport.arrival_dataset(connected.normalise(phrase)) is None
    assert (
        arrival_catalogue.resources.catalogue.search(phrase, access="sources")["items"]
        == []
    )


def test_arrival_matching_keeps_existing_literal_mode_searches(arrival_catalogue):
    catalogue = arrival_catalogue.resources.catalogue
    for phrase, expected in (
        ("Light Rail", transport.MTR_LIGHT_RAIL_DATASET),
        ("MTR Bus", transport.MTR_BUS_DATASET),
    ):
        assert [
            item["id"] for item in catalogue.search(phrase, access="sources")["items"]
        ] == [expected]


@pytest.mark.asyncio
async def test_arrival_question_catalogue_parity_over_mcp_and_http(arrival_catalogue):
    app = create_app(arrival_catalogue)
    with TestClient(app) as http:
        async with Client(app.state.mcp) as mcp:
            for phrase, expected in (
                (
                    "When is the next Tsuen Wan line train from Central?",
                    transport.MTR_RAIL_DATASET,
                ),
                ("中環站下一班往荃灣的港鐵幾點到", transport.MTR_RAIL_DATASET),
                (
                    "When does the next Light Rail train arrive at Tuen Mun?",
                    transport.MTR_LIGHT_RAIL_DATASET,
                ),
                ("下一班港鐵接駁巴士幾時到", transport.MTR_BUS_DATASET),
            ):
                args = {"q": phrase, "limit": 3, "access": "sources"}
                result = await mcp.call_tool("hk_catalogue_search", args)
                response = http.get("/api/v1/catalogue/datasets", params=args)
                assert response.status_code == 200
                page = result.structured_content
                assert page == response.json() == json.loads(result.content[0].text)
                assert page["items"][0]["id"] == expected
