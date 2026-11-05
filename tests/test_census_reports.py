"""Report issue scope and original CSV values survive the browser-download adapter."""

import json

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def report_service(tmp_path, monkeypatch):
    service = Service(Store(str(tmp_path / "report.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "report",
                "title": "Report",
                "provider": "C&SD",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        [
            {
                "id": fmt,
                "datasetId": "report",
                "format": fmt,
                "url": "https://www.censtatd.gov.hk/tc/wbr.html?ecode=B10200052026MM08&download_excel=1",
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
            for fmt in ["XLSX", "CSV"]
        ],
        {},
    )
    state = {
        "manifest": {
            "tb_code_list": ["T1", "T2"],
            "Issue": "August 2026",
            "Element_Title": "Synthetic report",
        },
        "component": {
            "tb_code": "T1",
            "theme_id": "104",
            "table_component_list": [
                {"stat_var": "VALUE", "stat_pres": "Raw_%"},
                {"stat_var": "VALUE", "stat_pres": "Rate"},
            ],
        },
        "dictionary": {
            "sv_list": {
                "VALUE": {
                    "def_stat_desc": "Source label",
                    "sp_list": {
                        "Raw_%": {
                            "def_stat_pres_desc": "Original percent",
                            "def_unit": "",
                        },
                        "Rate": {},
                    },
                }
            },
            "cv_list": {"ID": {"def_class_desc": "Original identifier"}},
        },
        "csv": b"ID,CCYY,MM,obs_value,sd_value\n0001,2025,08,001.2000,**\n0002,2026,08,,\n",
        "change": False,
        "calls": [],
    }

    async def fetch(url, headers=None, **kwargs):
        state["calls"].append(url)
        assert url.startswith(
            "https://www.censtatd.gov.hk/wbr/B1020005/B10200052026MM08/data/"
        )
        if url.endswith("tc/wbr.json"):
            value = dict(state["manifest"])
            if state["change"] and state["calls"].count(url) > 1:
                value["Issue"] = "changed"
        elif url.endswith("table_T1_comp.json"):
            value = state["component"]
        elif url.endswith("tc/table_T1_lang.json"):
            value = state["dictionary"]
        else:
            assert url.endswith("MDT_104_T1_VALUE_Raw_percent.csv")
            return state["csv"], {}, url, 200
        return json.dumps(value).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    return service, state


@pytest.mark.asyncio
@pytest.mark.parametrize("fmt", ["XLSX", "CSV"])
async def test_explicit_two_stage_report_series_and_original_values(
    report_service, fmt
):
    service, state = report_service
    service.resources.catalogue.failure(fmt, "SOURCE_UNAVAILABLE")
    discovered = await service.resources.schema(fmt)
    assert discovered["selections"][0]["options"][0]["value"] == "T1"
    assert service.resources.catalogue.check(fmt)["status"] == "unavailable"
    series = await service.resources.schema(fmt, record_path="T1")
    assert [o["value"] for o in series["selections"][0]["options"]] == [
        "T1/VALUE/Raw_%",
        "T1/VALUE/Rate",
    ]
    result = await service.resources.query(fmt, record_path="T1/VALUE/Raw_%")
    assert result["meta"]["total"] == 2
    assert result["data"]["items"][0] == {
        "ID": "0001",
        "CCYY": "2025",
        "MM": "08",
        "obs_value": "001.2000",
        "sd_value": "**",
    }
    context = result["schema"]["sourceContext"]
    assert context["Issue"] == "August 2026"
    assert context["presentationDictionary"]["def_unit"] == ""
    assert result["schema"]["sourceSelection"]["recordPath"] == "T1/VALUE/Raw_%"
    assert result["schema"]["scope"] == "complete_selected_report_series_file"
    assert len(result["schema"]["sourceFiles"]) == 5


@pytest.mark.asyncio
async def test_unpublished_series_and_sheet_do_not_override_scope(report_service):
    service, state = report_service
    for options in [
        {"record_path": "T1/VALUE/missing"},
        {"record_path": "T1/VALUE/../../../"},
        {"sheet": "T1"},
    ]:
        with pytest.raises(DomainError) as error:
            await service.resources.schema("XLSX", **options)
        assert error.value.code in {"INVALID_QUERY", "INVALID_RECORD_PATH"}
    assert not any(url.endswith(".csv") for url in state["calls"])


@pytest.mark.asyncio
async def test_changed_manifest_rejects_selected_source_and_retains_failure(
    report_service,
):
    service, state = report_service
    state["change"] = True
    with pytest.raises(DomainError, match="SOURCE_CHANGED"):
        await service.resources.query("XLSX", record_path="T1/VALUE/Raw_%")
    assert service.resources.catalogue.check("XLSX")["status"] != "queryable"
