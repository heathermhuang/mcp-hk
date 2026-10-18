"""Lossless bounded readers. No guessed units, dates, identifiers or table joins."""

import csv
import io
import json
import math
import subprocess
import sys
import tempfile
import zipfile
from datetime import date, datetime

from defusedxml import ElementTree

from .contracts import DomainError
from .resource_fields import inspect_nested
from .source_contracts import CSV_DATE_PREAMBLE, date_only_header

MAX_ROWS = 100_000
MAX_FIELDS = 1000


def document_limits():
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8_000_000, 8_000_000))
    if sys.platform.startswith("linux"):
        resource.setrlimit(resource.RLIMIT_AS, (512_000_000, 512_000_000))


def invalid(message, code="SOURCE_SCHEMA_CHANGED"):
    raise DomainError(code, message, 422)


def text(body):
    for encoding in ("utf-8-sig", "utf-16", "big5hkscs"):
        if encoding == "utf-16" and not body.startswith((b"\xff\xfe", b"\xfe\xff")):
            continue
        try:
            return body.decode(encoding), encoding
        except UnicodeError:
            continue
    invalid("Unknown text encoding", "UNSUPPORTED_ENCODING")


def at_path(value, path):
    for part in path.split("/") if path else []:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list) and part.isdigit() and int(part) < len(value):
            value = value[int(part)]
        elif isinstance(value, dict) and part in value:
            value = value[part]
        else:
            invalid(
                "Record path is absent; inspect available paths", "INVALID_RECORD_PATH"
            )
    return value


def paths(value, prefix="", depth=0):
    if depth > 8:
        return []
    if isinstance(value, list):
        return [prefix] + (
            paths(value[0], prefix + "/0", depth + 1)
            if len(value) == 1 and isinstance(value[0], dict)
            else []
        )
    if isinstance(value, dict):
        return [
            p
            for k, v in value.items()
            for p in paths(v, prefix + ("/" if prefix else "") + k, depth + 1)
        ]
    return []


def safe_json(value, depth=0):
    if depth > 30:
        invalid("Nested data exceeds depth budget", "SOURCE_TOO_COMPLEX")
    if isinstance(value, float) and not math.isfinite(value):
        invalid("Nonfinite numeric value")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): safe_json(v, depth + 1) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(v, depth + 1) for v in value]
    return value


def no_duplicates(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            invalid("Duplicate JSON object key")
        result[k] = v
    return result


def table(matrix, info=None, positional_date_header=False):
    matrix = iter(matrix)
    header = next(matrix, None)
    if header is None:
        invalid("No table header")
    raw = [str(x) if x is not None else "" for x in header]
    dated = positional_date_header and date_only_header(raw)
    if not raw or len(raw) > MAX_FIELDS:
        invalid("Table field budget exceeded", "SOURCE_TOO_COMPLEX")
    header = []
    mapping = []
    for i, name in enumerate(raw):
        field = (
            name
            if not dated and name and raw.count(name) == 1
            else "_column_" + str(i + 1)
        )
        while field in header or (field in raw and field != name):
            field = "_" + field
        header.append(field)
        mapping.append({"name": field, "sourceHeader": name, "columnIndex": i + 1})
    rows = []
    for values in matrix:
        if len(rows) >= MAX_ROWS:
            invalid("Source exceeds row budget", "SOURCE_TOO_LARGE")
        if len(values) > MAX_FIELDS:
            invalid("Table field budget exceeded", "SOURCE_TOO_COMPLEX")
        if all(x is None or x == "" for x in values):
            continue
        while len(values) > len(header):
            i = len(header)
            field = "_column_" + str(i + 1)
            while field in header:
                field = "_" + field
            header.append(field)
            mapping.append({"name": field, "sourceHeader": None, "columnIndex": i + 1})
        rows.append(dict(zip(header, values)))
    if info is not None:
        if dated:
            info["readerContract"] = CSV_DATE_PREAMBLE
            info["rowMeaning"] = (
                "The dated first row is retained as header metadata; remaining raw rows may include source header/description rows. Row counts are not verified counts of real-world entities."
            )
        info["sourceColumns"] = mapping
        info["headerVerification"] = (
            "First row retained as source header metadata; blank/duplicate/extra columns have explicit positional names. No semantic table interpretation."
        )
    return rows


def parse(body, fmt, record_path="", sheet=""):
    fmt = fmt.upper()
    if body.startswith(b"PK\x03\x04") and fmt not in {"XLSX", "XLSM"}:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            members = [m for m in archive.infolist() if not m.is_dir()]
            if len(members) > 1000 or sum(m.file_size for m in members) > 32_000_000:
                invalid("Archive expansion exceeds budget", "SOURCE_TOO_LARGE")
            allowed = {
                "CSV",
                "JSON",
                "GEOJSON",
                "XML",
                "RSS",
                "GML",
                "KML",
                "XLS",
                "XLSX",
                "PDF",
            }
            selected = [
                m for m in members if m.filename.rsplit(".", 1)[-1].upper() in allowed
            ]
            if not selected:
                invalid(
                    "Archive contains no supported record files", "UNSUPPORTED_FORMAT"
                )
            if any(m.flag_bits & 1 for m in selected):
                invalid("Encrypted archive", "ACCESS_RESTRICTED")
            all_rows = []
            member_info = []
            for m in selected:
                child_format = m.filename.rsplit(".", 1)[-1].upper()
                child_rows, child_schema = parse(
                    archive.read(m), child_format, record_path, sheet
                )
                member_info.append(
                    {
                        "name": m.filename,
                        "format": child_format,
                        "recordCount": len(child_rows),
                    }
                )
                for row in child_rows:
                    if "_sourceArchiveMember" in row:
                        invalid("Reserved archive provenance field collision")
                    all_rows.append({**row, "_sourceArchiveMember": m.filename})
                if len(all_rows) > MAX_ROWS:
                    invalid("Archive exceeds row budget", "SOURCE_TOO_LARGE")
            rows, info = parse(
                json.dumps(all_rows, ensure_ascii=False).encode(), "JSON"
            )
            info.update(
                format=fmt,
                scope="supported_archive_members",
                archiveMembers=member_info,
                unreadMembers=[m.filename for m in members if m not in selected],
                datasetCompleteness="Only the listed supported archive members; binary/other members remain unqueried.",
            )
            info["queryFields"] = inspect_nested(rows)
            return rows, info
    info = {
        "format": fmt,
        "recordPath": record_path or None,
        "sheet": sheet or None,
        "normalization": "Source values retained; no inferred units or reference periods.",
    }
    if fmt == "CSV":
        decoded, encoding = text(body)
        info["encoding"] = encoding
        if "\x00" in decoded or decoded.lstrip().lower().startswith(
            ("<!doctype html", "<html")
        ):
            invalid("Source returned binary or HTML rather than CSV")
        sample = decoded[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        rows = table(
            csv.reader(io.StringIO(decoded, newline=""), dialect, strict=True),
            info,
            positional_date_header=True,
        )
    elif fmt in {"JSON", "GEOJSON", "API"}:
        decoded, encoding = text(body)
        value = json.loads(
            decoded,
            object_pairs_hook=no_duplicates,
            parse_constant=lambda _: invalid("Nonfinite JSON number"),
        )
        info["encoding"] = encoding
        candidates = paths(value)
        info["availableRecordPaths"] = candidates[:100]

        def context(v, depth=0):
            if depth > 8:
                return {"omitted": "depth limit"}
            if isinstance(v, list):
                return {"sourceArrayLength": len(v)}
            if isinstance(v, dict):
                return {k: context(x, depth + 1) for k, x in v.items()}
            return v

        if isinstance(value, dict):
            info["sourceContext"] = context(value)
        if isinstance(value, dict) and (
            value.get("success") is False
            or isinstance(value.get("error"), dict)
            and "code" in value["error"]
        ):
            invalid("Source API returned an error envelope", "SOURCE_API_ERROR")
        if (
            isinstance(value, dict)
            and set(value) == {"message"}
            and str(value["message"]).strip().casefold()
            in {"no record found", "no records found", "no data found", "no data"}
        ):
            info["sourceContext"] = dict(value)
            info["sourceResult"] = "empty"
            value = []
        calendar = value.get("vcalendar") if isinstance(value, dict) else None
        calendar = (
            calendar[0]
            if isinstance(calendar, list)
            and len(calendar) == 1
            and isinstance(calendar[0], dict)
            and isinstance(calendar[0].get("vevent"), list)
            and "prodid" in calendar[0]
            and "version" in calendar[0]
            else None
        )
        if calendar is not None:
            info["calendarMetadata"] = {
                k: v for k, v in calendar.items() if k != "vevent"
            }
        if calendar is not None and record_path in {"", "vcalendar/0/vevent"}:
            info["recordPath"] = "vcalendar/0/vevent"
            info["scope"] = "calendar_events"
            info["rowMeaning"] = (
                "One source iCalendar event; calendar metadata retained separately."
            )
            value = calendar["vevent"]
        elif isinstance(value, dict) and value.get("type") == "FeatureCollection":
            info["sourceCrs"] = value.get("crs")
            value = value.get("features")
            info["recordPath"] = "features"
            info["coordinateReferenceSystem"] = (
                "crs is preserved as source metadata; absent crs follows GeoJSON specification"
            )
        elif record_path:
            value = at_path(value, record_path)
        elif (
            not isinstance(value, list)
            and len([p for p in candidates if "/0/" not in p]) == 1
        ):
            chosen = next(p for p in candidates if "/0/" not in p)
            info["recordPath"] = chosen
            value = at_path(value, chosen)
        elif not isinstance(value, list):
            # Keep a nested API object intact; choosing a nested array is explicit.
            value = [value]
            info["scope"] = "source_response_object"
        if not isinstance(value, list):
            invalid("Record path must select an array", "INVALID_RECORD_PATH")
        rows = [v if isinstance(v, dict) else {"value": v} for v in value]
    elif fmt in {"XLSX", "XLSM"}:
        from openpyxl import load_workbook

        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            if (
                sum(m.file_size for m in archive.infolist()) > 32_000_000
                or len(archive.infolist()) > 2000
            ):
                invalid("Workbook expansion exceeds budget", "SOURCE_TOO_LARGE")
        book = load_workbook(
            io.BytesIO(body), read_only=True, data_only=False, keep_links=False
        )
        try:
            info["availableSheets"] = book.sheetnames
            if not sheet and len(book.sheetnames) != 1:
                invalid(
                    "Select a workbook sheet: " + ", ".join(book.sheetnames)[:500],
                    "SHEET_REQUIRED",
                )
            if sheet and sheet not in book.sheetnames:
                invalid("Workbook sheet not found", "INVALID_SHEET")
            ws = book[sheet or book.sheetnames[0]]
            info["sheet"] = ws.title
            # Preserve formulas rather than presenting unverified cached results.
            rows = table(ws.values, info)
        finally:
            book.close()
    elif fmt == "XLS":
        import xlrd

        book = xlrd.open_workbook(file_contents=body, on_demand=True)
        try:
            info["availableSheets"] = book.sheet_names()
            if not sheet and book.nsheets != 1:
                invalid(
                    "Select a workbook sheet: " + ", ".join(book.sheet_names())[:500],
                    "SHEET_REQUIRED",
                )
            ws = book.sheet_by_name(sheet) if sheet else book.sheet_by_index(0)
            info["sheet"] = ws.name
            info["warning"] = (
                "Legacy XLS exposes stored cell results; original workbook remains authoritative."
            )
            rows = table((ws.row_values(i) for i in range(ws.nrows)), info)
        finally:
            book.release_resources()
    elif fmt in {"XML", "RSS", "GML", "KML"}:
        root = ElementTree.fromstring(body)
        info["rootTag"] = root.tag
        if fmt == "RSS":
            local = root.tag.rsplit("}", 1)[-1]
            valid = (
                (
                    local == "rss"
                    and any(e.tag.rsplit("}", 1)[-1] == "channel" for e in root)
                )
                or root.tag == "{http://www.w3.org/2005/Atom}feed"
                or (
                    root.tag == "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}RDF"
                    and any(
                        e.tag
                        in {
                            "{http://purl.org/rss/1.0/}channel",
                            "{http://purl.org/rss/1.0/}item",
                        }
                        for e in root
                    )
                )
            )
            if not valid:
                invalid("Published RSS source returned a non-feed document")
            info["readerContract"] = "rss-feed-root-1"
            info["fieldCompatibility"] = (
                "RSS/Atom fields are optional and extensible; observed types are retained, not a fixed analytical schema."
            )
            info["rowMeaning"] = (
                "Raw XML elements under the selected path; default selection is the direct feed container, not a count of all catalogue books."
            )

        def node(e):
            if not len(e) and not e.attrib:
                return e.text or ""
            result = {"@" + k: v for k, v in e.attrib.items()}
            for child in e:
                key = child.tag
                if key in result:
                    if not isinstance(result[key], list):
                        result[key] = [result[key]]
                    result[key].append(node(child))
                else:
                    result[key] = node(child)
            if e.text and e.text.strip():
                result["#text"] = e.text
            return result

        if record_path:
            if ".." in record_path or len(record_path) > 300:
                invalid("Use a simple XML element path", "INVALID_RECORD_PATH")
            elements = root.findall(record_path)
        else:
            elements = list(root)
            if len({e.tag for e in elements}) > 1:
                elements = [root]
                info["scope"] = "source_response_object"
        rows = [v if isinstance(v := node(e), dict) else {e.tag: v} for e in elements]
    elif fmt == "PDF":
        with tempfile.TemporaryFile() as output:
            try:
                subprocess.run(
                    [sys.executable, "-m", "mcp_open_data_hk.document_reader"],
                    input=body,
                    stdout=output,
                    stderr=subprocess.DEVNULL,
                    timeout=10,
                    check=True,
                )
                output.seek(0)
                extracted = output.read(8_000_001)
                if len(extracted) > 8_000_000:
                    invalid("Extracted text exceeds budget", "SOURCE_TOO_LARGE")
                rows = json.loads(extracted)
            except (subprocess.SubprocessError, ValueError):
                invalid(
                    "PDF extraction failed or exceeded its isolated resource budget",
                    "DOCUMENT_EXTRACTION_FAILED",
                )
        info.update(
            scope="document_pages",
            verification="unverified_text_extraction",
            structuredQueryable=False,
            emptyPages=[r["page"] for r in rows if not r["text"].strip()],
        )
    else:
        invalid("No reader for this source format", "UNSUPPORTED_FORMAT")
    if len(rows) > MAX_ROWS:
        invalid("Source exceeds row budget", "SOURCE_TOO_LARGE")
    if sum(len(r) for r in rows) > 2_000_000:
        invalid("Source exceeds cell budget", "SOURCE_TOO_COMPLEX")
    rows = safe_json(rows)
    fields = sorted({k for r in rows for k in r})
    if len(fields) > MAX_FIELDS:
        invalid("Source exceeds field budget", "SOURCE_TOO_COMPLEX")

    def types(v):
        if v is None:
            return "null"
        if isinstance(v, bool):
            return "boolean"
        if isinstance(v, (int, float)):
            return "number"
        if isinstance(v, dict):
            return "object"
        if isinstance(v, list):
            return "array"
        return "string"

    info["fields"] = [
        {
            "name": k,
            "types": sorted({types(r.get(k)) for r in rows}),
            "missingCount": sum(k not in r or r[k] is None for r in rows),
            "unit": None,
        }
        for k in fields
    ]
    info["queryFields"] = inspect_nested(rows)
    return rows, info
