"""Explicit issue/table/series access to C&SD browser-generated reports.

The publisher's web_report_init.js and cnds_cdm.js define these fixed paths.
Rows are one original MDT CSV series, never a synthesized workbook or latest API.
"""

import asyncio
import hashlib
import json
import re
from urllib.parse import parse_qs, urlsplit

from .contracts import DomainError
from .resource_formats import parse


def location(url):
    parts = urlsplit(url)
    match = re.fullmatch(r"/(en|tc|sc)/wbr\.html", parts.path)
    codes = parse_qs(parts.query).get("ecode", [])
    if (
        parts.hostname != "www.censtatd.gov.hk"
        or not match
        or len(codes) != 1
        or not re.fullmatch(r"[A-Z][A-Z0-9]{7,15}", codes[0])
    ):
        return None
    return match[1], codes[0]


def pointer(value):
    return value.replace("~", "~0").replace("/", "~1")


def safe(value):
    return (
        isinstance(value, str)
        and ".." not in value
        and re.fullmatch(r"[A-Za-z0-9_/%$.-]{1,100}", value)
    )


async def report(url, selection, fetch):
    lang, issue = location(url)
    root = "https://www.censtatd.gov.hk/wbr/" + issue[:8] + "/" + issue + "/data/"
    sources, used = [], 0

    async def read(path, json_value=True):
        nonlocal used
        body, headers, final, status = await fetch(root + path)
        used += len(body)
        if status != 200 or used > 8_000_000:
            raise DomainError(
                "SOURCE_TOO_LARGE" if used > 8_000_000 else "INVALID_SOURCE",
                "Report source exceeds its read bound or failed",
                422,
            )
        sources.append({"sourceUrl": final, "sha256": hashlib.sha256(body).hexdigest()})
        return await asyncio.to_thread(json.loads, body) if json_value else body

    manifest_path = lang + "/wbr.json"
    manifest = await read(manifest_path)
    tables = manifest.get("tb_code_list")
    if (
        not isinstance(tables, list)
        or not tables
        or len(tables) > 1000
        or any(not safe(t) for t in tables)
        or len(tables) != len(set(tables))
    ):
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Report table inventory is invalid", 422
        )
    context = {
        "issueCode": issue,
        "language": lang,
        **{
            k: manifest.get(k)
            for k in (
                "Element_ID",
                "Element_Title",
                "Issue",
                "Release_Date_Soft",
                "schedule_time",
            )
        },
    }
    if not selection:
        return {
            "schema": {"availableRecordPaths": tables, "sourceContext": context},
            "selectionRequired": "recordPath",
            "recordCount": None,
            "structuredQueryable": False,
            "selectionMeaning": "Published report table; then explicitly choose one statistic series.",
        }
    parts = [p.replace("~1", "/").replace("~0", "~") for p in selection.split("/")]
    if len(parts) not in {1, 3} or parts[0] not in tables:
        raise DomainError(
            "INVALID_RECORD_PATH",
            "Choose an exact published report table/variable/presentation",
            400,
        )
    table = parts[0]
    component = await read("table_" + table + "_comp.json")
    components = component.get("table_component_list")
    if (
        component.get("tb_code") != table
        or not isinstance(components, list)
        or not components
        or len(components) > 1000
        or any(
            not isinstance(c, dict)
            or not safe(c.get("stat_var"))
            or not safe(c.get("stat_pres"))
            for c in components
        )
    ):
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Report series inventory is invalid", 422
        )
    choices = [
        table + "/" + pointer(c["stat_var"]) + "/" + pointer(c["stat_pres"])
        for c in components
    ]
    if len(choices) != len(set(choices)):
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Report series identities repeat", 422
        )
    if len(parts) == 1:
        return {
            "schema": {"availableRecordPaths": choices, "sourceContext": context},
            "selectionRequired": "recordPath",
            "recordCount": None,
            "structuredQueryable": False,
            "selectionMeaning": "One original report-scoped MDT CSV series; no unit, period or presentation conversion.",
        }
    if selection not in choices:
        raise DomainError(
            "INVALID_RECORD_PATH", "Series is not in the published table", 400
        )
    variable, presentation = parts[1:]
    theme = component.get("theme_id")
    if not re.fullmatch(r"[0-9]{1,6}", str(theme)):
        raise DomainError("SOURCE_SCHEMA_CHANGED", "Report theme identity changed", 422)
    dictionary = await read(lang + "/table_" + table + "_lang.json")
    try:
        statistic = dictionary["sv_list"][variable]
        form = statistic["sp_list"][presentation]
    except (KeyError, TypeError):
        raise DomainError(
            "SOURCE_SCHEMA_CHANGED", "Selected series has no published dictionary", 422
        ) from None
    filename = (
        (
            "MDT_"
            + str(theme)
            + "_"
            + table
            + "_"
            + variable.replace("/", "slash")
            + "_"
            + presentation.replace("/", "slash")
            + ".csv"
        )
        .replace("%", "percent")
        .replace("$", "dollar")
    )
    body = await read(filename, False)
    rows, raw_schema = await asyncio.to_thread(parse, body, "CSV")
    # Re-read the bounded manifest; no claim of an atomic multi-file publication.
    if await read(manifest_path) != manifest:
        raise DomainError(
            "SOURCE_CHANGED", "Report inventory changed during the selected read", 409
        )
    context.update(
        {
            "tableId": table,
            "tableTitle": dictionary.get("tb_title"),
            "tableFootnotes": dictionary.get("tb_fn"),
            "tableSource": dictionary.get("tb_src"),
            "statisticVariable": variable,
            "statisticPresentation": presentation,
            "statisticDictionary": {
                k: v for k, v in statistic.items() if k != "sp_list"
            },
            "presentationDictionary": form,
            "classificationDictionary": dictionary.get("cv_list"),
            "reportPublicationSnapshot": "not_atomic_across_files",
        }
    )
    encoded = (
        await asyncio.to_thread(
            json.dumps, {"records": rows, "context": context}, ensure_ascii=False
        )
    ).encode()
    if len(encoded) > 8_000_000:
        raise DomainError(
            "SOURCE_TOO_LARGE",
            "Selected series and context exceed the representation bound",
            422,
        )
    extra = {
        "apiFamily": "C&SD published report",
        "accessMethod": "official_issue_scoped_mdt_csv_series",
        "originalResourceUrl": url,
        "sourceContext": context,
        "scope": "complete_selected_report_series_file",
        "sourceMatched": len(rows),
        "sourceFiles": sources,
        "sourceColumns": raw_schema.get("sourceColumns"),
        "headerVerification": raw_schema.get("headerVerification"),
        "datasetCompleteness": "One explicitly selected original series file, not the entire report, generated workbook or current statistical series.",
    }
    return encoded, {"content-type": "application/json"}, root + filename, extra
