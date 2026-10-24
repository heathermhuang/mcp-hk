"""Bounded official observations, separate from the immutable Webb archive."""

import csv
import hashlib
import io
from itertools import product
import json
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime


CATALOGUE = "https://data.gov.hk/en-data/dataset/hk-cr-crdata-list-newly-registered-companies-2526"
TERMS = "https://data.gov.hk/en/terms-and-conditions"
ATTRIBUTION = "Government of the HKSAR / Companies Registry / DATA.GOV.HK"
ML_BASE = "https://www.cr.gov.hk/datagovhk/psi/"
ML_FILES = ("ml_licensees", "ml_list1", "ml_list2", "ml_list3")
LIMITATIONS = [
    "Observed official subset; not a complete current company-status register",
    "Dissolution events are not covered; absence never establishes dissolution",
    "Local weekly dates combine incorporation and re-domiciliation unless the address source distinguishes them",
    "No inferred CRN/BRN crosswalk, name-based join, current officers or SFC/HKEX update coverage",
    "Money-lender MLR identities are separate from company BRNs; source cutoff can precede collection",
]
DDL = """
CREATE SCHEMA IF NOT EXISTS curated;
CREATE TABLE IF NOT EXISTS curated.official_runs(
 run_id text PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz, status text NOT NULL, receipt jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS curated.official_captures(
 capture_id text PRIMARY KEY, source_key text NOT NULL, sha256 text NOT NULL,
 body bytea NOT NULL, verification_body bytea, receipt jsonb NOT NULL,
 valid boolean NOT NULL DEFAULT false);
CREATE TABLE IF NOT EXISTS curated.official_records(
 capture_id text NOT NULL REFERENCES curated.official_captures,
 fact_id text NOT NULL, entity_id text NOT NULL, name_key text NOT NULL,
 name2_key text NOT NULL, record jsonb NOT NULL,
 PRIMARY KEY(capture_id,fact_id));
CREATE INDEX IF NOT EXISTS official_record_entity ON curated.official_records(entity_id,capture_id);
CREATE INDEX IF NOT EXISTS official_record_name ON curated.official_records(name_key text_pattern_ops);
CREATE INDEX IF NOT EXISTS official_record_name2 ON curated.official_records(name2_key text_pattern_ops);
CREATE TABLE IF NOT EXISTS curated.official_versions(
 version text PRIMARY KEY, manifest jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS curated.official_members(
 version text NOT NULL REFERENCES curated.official_versions,
 source_key text NOT NULL, capture_id text NOT NULL REFERENCES curated.official_captures,
 PRIMARY KEY(version,source_key));
CREATE TABLE IF NOT EXISTS curated.official_pointer(
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 version text NOT NULL REFERENCES curated.official_versions);
"""


class SourceRejected(ValueError):
    """No accepted data may be replaced by an unqualified source response."""


def digest(value):
    return hashlib.sha256(value).hexdigest()


def encoded(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9]{1,20}", value):
        raise SourceRejected("INVALID_SOURCE_IDENTIFIER")
    return value


def day(value, formats=("%d-%m-%Y", "%d/%m/%Y")):
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise SourceRejected("INVALID_SOURCE_DATE")


def header(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def csv_rows(body):
    if not body or not body.endswith((b"\n", b"\r")) or len(body) > 8 * 1024 * 1024:
        raise SourceRejected("EMPTY_TRUNCATED_OR_OVERSIZE_CSV")
    try:
        reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig")), strict=True)
        fields = reader.fieldnames
        rows = list(reader)
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise SourceRejected("INVALID_CSV") from exc
    if not fields or not rows or len(rows) > 20000 or len(set(fields)) != len(fields):
        raise SourceRejected("EMPTY_OR_INVALID_CSV_SCHEMA")
    if any(None in row or any(v is None for v in row.values()) for row in rows):
        raise SourceRejected("PARTIAL_CSV_ROW")
    return fields, rows


def verify_xls(body, xls, normalizations=None):
    """Reconcile all CSV rows with the independently fetched XLS representation."""
    import xlrd

    fields, rows = csv_rows(body)
    try:
        book = xlrd.open_workbook(file_contents=xls, formatting_info=True)
        sheet = book.sheet_by_index(0)
        normalized = [header(f) for f in fields]
        start = next(
            i
            for i in range(min(30, sheet.nrows))
            if [header(str(v)) for v in sheet.row_values(i)[: len(fields)]]
            == normalized
            and not any(str(v).strip() for v in sheet.row_values(i)[len(fields) :])
        )
    except Exception as exc:
        raise SourceRejected("XLS_SCHEMA_CHANGED") from exc

    def canonical(values):
        out = []
        for field, value in zip(fields, values):
            value = str(value).strip()
            if field in {"BR Number", "MLR_No"} and value.isdigit():
                # XLS numeric cells discard zero padding; CSV remains authoritative.
                value = value.lstrip("0") or "0"
            if "date" in field.lower() and value:
                formats = ("%d-%m-%Y", "%d/%m/%Y", "%d-%b-%y", "%d-%b-%Y")
                value = day(value, formats)
            out.append(value)
        return tuple(out)

    expected = Counter(canonical([row[f] for f in fields]) for row in rows)
    actual = []
    prefix_columns = []
    for i in range(start + 1, sheet.nrows):
        # Formatting-aware xlrd exposes trailing styled blank columns. Ignore
        # only empty cells; extra source values must still fail qualification.
        if any(str(v).strip() for v in sheet.row_values(i)[len(fields) :]):
            raise SourceRejected("XLS_EXTRA_SOURCE_COLUMNS")
        values = []
        prefixed = []
        for col, field in enumerate(fields):
            cell = sheet.cell(i, col)
            if cell.ctype == xlrd.XL_CELL_DATE:
                value = xlrd.xldate_as_datetime(cell.value, book.datemode).strftime(
                    "%d-%m-%Y"
                )
            elif cell.ctype == xlrd.XL_CELL_NUMBER:
                if cell.value != int(cell.value):
                    raise SourceRejected("NON_INTEGER_XLS_VALUE")
                value = str(int(cell.value))
            else:
                value = str(cell.value)
            if cell.ctype == xlrd.XL_CELL_TEXT and getattr(
                book.xf_list[cell.xf_index], "lotus_123_prefix", 0
            ):
                prefixed.append(col)
            values.append(value)
        if any(v.strip() for v in values):
            actual.append(canonical(values))
            prefix_columns.append(prefixed)
    restored_prefixes = 0
    if Counter(actual) != expected:
        remaining = expected.copy()
        for row, prefixed in zip(actual, prefix_columns):
            if remaining[row]:
                remaining[row] -= 1
                continue
            if not prefixed or len(prefixed) > 8:
                raise SourceRejected("CSV_XLS_ROWS_DIFFER")
            candidates = []
            for choices in product((False, True), repeat=len(prefixed)):
                candidate = list(row)
                for col, enabled in zip(prefixed, choices):
                    if enabled:
                        candidate[col] = "'" + candidate[col]
                candidate = tuple(candidate)
                if remaining[candidate] > 0:
                    candidates.append((candidate, sum(choices)))
            if len(candidates) != 1:
                raise SourceRejected("CSV_XLS_ROWS_DIFFER")
            candidate, count = candidates[0]
            remaining[candidate] -= 1
            restored_prefixes += count
        if any(remaining.values()):
            raise SourceRejected("CSV_XLS_ROWS_DIFFER")
    if normalizations is not None:
        normalizations.update(
            excelQuotePrefixCells=restored_prefixes, sourceCsvTextPreserved=True
        )
    return len(rows)


def weekly(body, scope, week):
    fields, rows = csv_rows(body)
    foreign = scope == "foreign"
    names = (
        [
            "Current Corporate Name / Other Corporate Name",
            "Current Approved Name for Carrying on Business in H.K.",
        ]
        if foreign
        else ["Current Company Name in English", "Current Company Name in Chinese"]
    )
    date_field = (
        "Date of Registration"
        if foreign
        else next(
            (
                f
                for f in fields
                if f
                in (
                    "Date of Incorporation",
                    "Date of Incorporation / Re-domiciliation Date",
                )
            ),
            "",
        )
    )
    if (
        fields != ["Seq", *names, "BR Number", date_field, "Date of Change of name"]
        or not date_field
    ):
        raise SourceRejected("WEEKLY_SCHEMA_CHANGED")
    start = datetime.strptime(week, "%Y%m%d").date()
    end = start + timedelta(days=6)
    output = []
    for row in rows:
        brn = identifier(row["BR Number"])
        if not row["Seq"].isdigit() or not any(row[n] for n in names):
            raise SourceRejected("INVALID_WEEKLY_ROW")
        events = []
        for field, kind in [
            (
                date_field,
                (
                    "registration"
                    if foreign
                    else (
                        "incorporation_or_redomiciliation"
                        if "/" in date_field
                        else "incorporation"
                    )
                ),
            ),
            ("Date of Change of name", "name_change"),
        ]:
            if row[field]:
                effective = day(row[field])
                if not start.isoformat() <= effective <= end.isoformat():
                    raise SourceRejected("DATE_OUTSIDE_SOURCE_WEEK")
                events.append(
                    {
                        "type": kind,
                        "date": effective,
                        "dateRaw": row[field],
                        "precision": "day",
                    }
                )
        if not events:
            raise SourceRejected("WEEKLY_ROW_WITHOUT_EVENT")
        output.append(
            {
                "entity_id": f"cr:{scope}:{brn}",
                "kind": "company_event",
                "name1": row[names[0]],
                "chinese_name": row[names[1]] if not foreign else "",
                "names": [row[n] for n in names if row[n]],
                "identifier": {"namespace": f"cr:{scope}:brn", "value": brn},
                "events": events,
                "raw": row,
                "coverageStart": start.isoformat(),
                "coverageEnd": end.isoformat(),
            }
        )
    return output


def lenders(body, file):
    fields, rows = csv_rows(body)
    expected = {
        "ml_licensees": [
            "MLR_No",
            "ML_Lic_No",
            "Period",
            "Name_Eng",
            "Name_Chi",
            "Expiry_Date",
            "Remarks",
        ],
        "ml_list1": ["MLR_No", "Period", "Name_Eng", "Name_Chi"],
        "ml_list2": [
            "MLR_No",
            "Period",
            "Name_Eng",
            "Name_Chi",
            "Expiry_Date",
            "Eng_Remarks",
            "Chi_Remarks",
        ],
        "ml_list3": ["MLR_No", "Period", "Name_Eng", "Name_Chi", "Remarks"],
    }
    if fields != expected[file]:
        raise SourceRejected("MONEY_LENDER_SCHEMA_CHANGED")
    output = []
    for row in rows:
        mlr = row["MLR_No"]
        if not mlr.isdigit() or not any(row[n] for n in ("Name_Eng", "Name_Chi")):
            raise SourceRejected("INVALID_MONEY_LENDER_ROW")
        try:
            cutoff = (
                datetime.strptime(row["Period"], "As at %d %B %Y").date().isoformat()
            )
        except ValueError as exc:
            raise SourceRejected("UNKNOWN_MONEY_LENDER_PERIOD") from exc
        expiry = row.get("Expiry_Date")
        if expiry:
            day(expiry, ("%d-%b-%y", "%d-%b-%Y"))
        output.append(
            {
                "entity_id": "cr:mlr:" + mlr,
                "kind": "money_lender",
                "name1": row["Name_Eng"],
                "chinese_name": row["Name_Chi"],
                "names": [row[n] for n in ("Name_Eng", "Name_Chi") if row[n]],
                "identifier": {"namespace": "cr:mlr", "value": mlr},
                "register": {
                    "ml_licensees": "existing_licensees",
                    "ml_list1": "applications",
                    "ml_list2": "expired_licences",
                    "ml_list3": "dismissed_or_withdrawn_applications",
                }[file],
                "coverageEnd": cutoff,
                "licenceExpiry": (
                    {
                        "dateRaw": expiry,
                        "date": day(expiry, ("%d-%b-%y", "%d-%b-%Y")),
                        "precision": "day",
                    }
                    if expiry
                    else None
                ),
                "raw": row,
            }
        )
    if len({r["coverageEnd"] for r in output}) != 1:
        raise SourceRejected("MIXED_MONEY_LENDER_PERIODS")
    return output


def address(body, scope, brn):
    identifier(brn)
    try:
        rows = json.loads(body)
    except (ValueError, UnicodeError) as exc:
        raise SourceRejected("INVALID_ADDRESS_JSON") from exc
    if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], dict):
        raise SourceRejected("ADDRESS_NO_MATCH_OR_PARTIAL")
    row = rows[0]
    field = (
        "Address_of_Registered_Office"
        if scope == "local"
        else "Principal_Place_of_Business_in_H.K."
    )
    if (
        row.get("Brn") != brn
        or not isinstance(row.get(field), str)
        or not row[field].strip()
    ):
        raise SourceRejected("ADDRESS_IDENTITY_OR_SCHEMA_CHANGED")
    names = (
        [row.get("English_Company_Name"), row.get("Chinese_Company_Name")]
        if scope == "local"
        else [row.get("Corporate_Name"), row.get("Other_Corporate_Name_s")]
    )
    names = [n for n in names if n and n != "NULL"]
    if not names:
        raise SourceRejected("ADDRESS_NAME_MISSING")
    events = []
    for date_field, kind in [
        ("Date_of_Incorporation", "incorporation"),
        ("Date_of_Registration", "registration"),
        ("Re-domiciliation_Date", "redomiciliation"),
    ]:
        raw = row.get(date_field)
        if raw and raw != "NULL":
            events.append(
                {"type": kind, "date": day(raw), "dateRaw": raw, "precision": "day"}
            )
    return [
        {
            "entity_id": f"cr:{scope}:{brn}",
            "kind": "address_observation",
            "events": events,
            "name1": names[0],
            "chinese_name": (
                row.get("Chinese_Company_Name")
                if row.get("Chinese_Company_Name") != "NULL"
                else None
            ),
            "names": names,
            "identifier": {"namespace": f"cr:{scope}:brn", "value": brn},
            "address": row[field],
            "effectiveFrom": None,
            "raw": row,
        }
    ]


def discover(body):
    try:
        links = sorted(
            set(
                re.findall(
                    r"https://www\.cr\.gov\.hk/docs/wrpt/RNC063/RNC063[LF]_[0-9]{8}\.csv",
                    body.decode("utf-8"),
                )
            )
        )
    except UnicodeError as exc:
        raise SourceRejected("INVALID_CATALOGUE") from exc
    if not 2 <= len(links) <= 1000:
        raise SourceRejected("EMPTY_OR_INVALID_CATALOGUE")
    pairs = {}
    for link in links:
        week = link[-12:-4]
        datetime.strptime(week, "%Y%m%d")
        pairs.setdefault(week, set()).add(link[-14])
    if any(k != {"L", "F"} for k in pairs.values()):
        raise SourceRejected("INCOMPLETE_WEEK_PAIR")
    return links


def capture_receipt(url, body, headers, records, fetched_at=None):
    fetched = fetched_at or now()
    modified = headers.get("last-modified")
    coverage = max((r.get("coverageEnd", "") for r in records), default="") or None
    result = {
        "sourceUrl": url,
        "sha256": digest(body),
        "bytes": len(body),
        "fetchedAt": fetched,
        "sourceLastModified": modified,
        "sourcePublicationAt": None,
        "rowCount": len(records),
        "coverageEnd": coverage,
        "publicationLagBasis": "HTTP Last-Modified minus covered-through date; proxy, publication time unavailable",
    }
    if coverage:
        end = datetime.fromisoformat(coverage).replace(tzinfo=timezone.utc) + timedelta(
            days=1
        )
        result["observedDelaySeconds"] = (
            datetime.fromisoformat(fetched) - end
        ).total_seconds()
        if modified:
            result["lastModifiedCoverageLagSeconds"] = (
                parsedate_to_datetime(modified) - end
            ).total_seconds()
    return result
