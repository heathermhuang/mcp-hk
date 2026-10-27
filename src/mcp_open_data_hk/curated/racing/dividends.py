"""Factual final-dividend table; never odds history or a stake-normalized return.

The inspected table labels HK dollars but does not state its stake basis. Keep
that basis unknown. A combination is source text, never a numeric identifier.
"""

import re
from decimal import Decimal

from .policy import RacingRejected, checksum
from .public_results import cells

POOLS = {
    "WIN",
    "PLACE",
    "QUINELLA",
    "QUINELLA PLACE",
    "FORECAST",
    "TIERCE",
    "TRIO",
    "FIRST 4",
    "QUARTET",
    "SIX UP",
    "TRIPLE TRIO(Consolation)",
}
HEADERS = ["Pool", "Winning Combination", "Dividend (HK$)"]
ZH_HEADERS = ["彩池", "勝出組合", "派彩 (HK$)"]
ZH_POOLS = {
    "獨贏": "WIN",
    "位置": "PLACE",
    "連贏": "QUINELLA",
    "位置Q": "QUINELLA PLACE",
    "二重彩": "FORECAST",
    "三重彩": "TIERCE",
    "單T": "TRIO",
    "四連環": "FIRST 4",
    "四重彩": "QUARTET",
    "六環彩": "SIX UP",
    "三T(安慰獎)": "TRIPLE TRIO(Consolation)",
}


def canonical_pool(value, language):
    if language == "en":
        if value in POOLS:
            return value
        match = re.fullmatch(
            r"([1-9][0-9]?)(ST|ND|RD|TH) (DOUBLE TRIO|DOUBLE|TREBLE)", value
        )
        if match and 1 <= int(match[1]) <= 20:
            n = int(match[1])
            suffix = (
                "TH"
                if 10 < n % 100 < 14
                else {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
            )
            if match[2] == suffix:
                return value
    else:
        if value in ZH_POOLS:
            return ZH_POOLS[value]
        match = re.fullmatch(r"第([一二三四五六七八九十]{1,3})口(孖寶|三寶|孖T)", value)
        if match:
            digits = {v: i for i, v in enumerate("一二三四五六七八九", 1)}
            text = match[1]
            if text == "十":
                n = 10
            elif text in digits:
                n = digits[text]
            elif text.startswith("十") and text[1:] in digits:
                n = 10 + digits[text[1:]]
            elif text == "二十":
                n = 20
            else:
                n = 0
            if 1 <= n <= 20:
                suffix = (
                    "TH"
                    if 10 < n % 100 < 14
                    else {1: "ST", 2: "ND", 3: "RD"}.get(n % 10, "TH")
                )
                return (
                    str(n)
                    + suffix
                    + " "
                    + {"孖寶": "DOUBLE", "三寶": "TREBLE", "孖T": "DOUBLE TRIO"}[
                        match[2]
                    ]
                )
    raise RacingRejected("DIVIDEND_POOL_UNQUALIFIED")


def outer_rows(table):
    result = []
    for row in table.all("tr"):
        parent = row.parent
        while parent and parent.tag != "table":
            parent = parent.parent
        if parent is table:
            result.append(cells(row))
    return result


def amount(raw):
    if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)(?:\.[0-9]{1,8})?", raw):
        raise RacingRejected("DIVIDEND_AMOUNT_UNQUALIFIED")
    return raw.replace(",", "")


def combination_key(raw, pool, language):
    """Preserve numeric order and one qualified literal source marker.

    Any Combination is source text in the third leg of the inspected consolation
    row. Translate its label for identity only; never enumerate or infer winners.
    Existing numeric quote identities remain unchanged.
    """
    if not isinstance(raw, str) or not 1 <= len(raw) <= 100:
        raise RacingRejected("DIVIDEND_COMBINATION_UNQUALIFIED")
    if re.fullmatch(r"[0-9]+(?:[ ,/-]*[0-9]+)*", raw):
        return re.sub(r"\s+", "", raw)
    markers = {"en": "Any Combination", "zhHant": "任何組合"}
    legs = raw.split("/")
    if (
        pool == "TRIPLE TRIO(Consolation)"
        and language in markers
        and len(legs) == 3
        and legs[2].strip() == markers[language]
        and all(
            re.fullmatch(r"[0-9]+(?:\s*,\s*[0-9]+){2}", leg.strip()) for leg in legs[:2]
        )
    ):
        return re.sub(r"\s+", "", "/".join(legs[:2])) + "/AnyCombination"
    raise RacingRejected("DIVIDEND_COMBINATION_UNQUALIFIED")


def parse_dividend_table(root, race_id, language="en"):
    """Use a race ID already validated by the factual results parser.

    Missing/unqualified is distinct from a verified empty dividend table.
    HTML rowspan is expanded only when the source explicitly declares it.
    """
    if language not in {"en", "zhHant"}:
        raise RacingRejected("DIVIDEND_LANGUAGE_UNQUALIFIED")
    headers = HEADERS if language == "en" else ZH_HEADERS
    found = []
    for table in root.all("table"):
        rows = outer_rows(table)
        matches = [
            i for i, row in enumerate(rows) if [c.text() for c in row] == headers
        ]
        if matches:
            if len(matches) != 1:
                raise RacingRejected("DIVIDEND_LAYOUT_UNQUALIFIED")
            found.append((rows, matches[0]))
    if not found:
        return {
            "state": "not_present",
            "sourceBasis": "final_results_page",
            "quotes": None,
        }
    if len(found) != 1:
        raise RacingRejected("DIVIDEND_LAYOUT_UNQUALIFIED")
    rows, start = found[0]
    data = rows[start + 1 :]
    if not data or len(data) > 200:
        raise RacingRejected("DIVIDEND_LAYOUT_UNQUALIFIED")
    pool, remaining, quotes, seen, deferred = None, 0, [], set(), 0
    for index, row in enumerate(data, 1):
        if remaining:
            if len(row) != 2:
                raise RacingRejected("DIVIDEND_ROWSPAN_UNQUALIFIED")
            remaining -= 1
            values = row
        else:
            if len(row) != 3:
                raise RacingRejected("DIVIDEND_ROWSPAN_UNQUALIFIED")
            cell, *values = row
            source_pool = cell.text()
            challenge = (
                r"(?:JOCKEY CHALLENGE|TRAINER CHALLENGE) [1-9][0-9]*"
                if language == "en"
                else r"(?:騎師王|練馬師王) [1-9][0-9]*"
            )
            if re.fullmatch(challenge, source_pool) and values[-1].text() == (
                "Details" if language == "en" else "詳情"
            ):
                if cell.attrs.get("rowspan", "1") != "1":
                    raise RacingRejected("DIVIDEND_ROWSPAN_UNQUALIFIED")
                deferred += 1
                continue
            pool = canonical_pool(source_pool, language)
            span = cell.attrs.get("rowspan", "1")
            if (
                not re.fullmatch(r"[1-9][0-9]?", span)
                or int(span) > len(data) - index + 1
            ):
                raise RacingRejected("DIVIDEND_ROWSPAN_UNQUALIFIED")
            remaining = int(span) - 1
        combination, raw_amount = (cell.text() for cell in values)
        combination_id = combination_key(combination, pool, language)
        identity = (pool, combination_id)
        if identity in seen:
            raise RacingRejected("DIVIDEND_DUPLICATE_COMBINATION")
        seen.add(identity)
        quotes.append(
            {
                "id": "hkjc:dividend:v1:" + checksum([race_id, pool, combination_id]),
                "raceId": race_id,
                "pool": pool,
                "poolSource": source_pool,
                "winningCombinationRaw": combination,
                "combinationKey": combination_id,
                "amount": amount(raw_amount),
                "amountRaw": raw_amount,
                "currency": "HKD",
                "stakeAmount": None,
                "stakeCurrency": None,
                "stakeBasis": "not_stated_in_captured_table",
                "sourceRow": index,
                "sourceLanguage": language,
            }
        )
    if remaining:
        raise RacingRejected("DIVIDEND_ROWSPAN_UNQUALIFIED")
    if not quotes:
        raise RacingRejected("DIVIDEND_NO_QUOTED_AMOUNTS")
    return {
        "state": "observed",
        "sourceBasis": "final_results_page",
        "reportedCurrency": "HKD",
        "stakeNormalized": False,
        "quotes": quotes,
        "sourceRows": len(quotes),
        "tableDataRows": len(data),
        "deferredNonmonetaryRows": deferred,
    }


def reconcile_dividends(english, chinese):
    """Reconcile all quotes without sorting combinations or rounding money."""
    if english["state"] == chinese["state"] == "not_present":
        return {"state": "not_present", "quotes": None, "stakeNormalized": False}
    if english["state"] != "observed" or chinese["state"] != "observed":
        raise RacingRejected("DIVIDEND_BILINGUAL_MISMATCH")
    if english.get("tableDataRows") != chinese.get("tableDataRows") or english.get(
        "deferredNonmonetaryRows"
    ) != chinese.get("deferredNonmonetaryRows"):
        raise RacingRejected("DIVIDEND_BILINGUAL_MISMATCH")
    other = {q["id"]: q for q in chinese["quotes"]}
    if len(other) != len(chinese["quotes"]) or set(other) != {
        q["id"] for q in english["quotes"]
    }:
        raise RacingRejected("DIVIDEND_BILINGUAL_MISMATCH")
    output = []
    for quote in english["quotes"]:
        translated = other[quote["id"]]
        if Decimal(quote["amount"]) != Decimal(translated["amount"]) or any(
            quote[k] != translated[k]
            for k in (
                "raceId",
                "pool",
                "combinationKey",
                "currency",
                "stakeAmount",
                "stakeCurrency",
                "stakeBasis",
            )
        ):
            raise RacingRejected("DIVIDEND_BILINGUAL_MISMATCH")
        output.append(
            {
                **quote,
                "sources": {
                    "en": {
                        "pool": quote["poolSource"],
                        "combination": quote["winningCombinationRaw"],
                        "amount": quote["amountRaw"],
                    },
                    "zhHant": {
                        "pool": translated["poolSource"],
                        "combination": translated["winningCombinationRaw"],
                        "amount": translated["amountRaw"],
                    },
                },
            }
        )
    return {
        "state": "observed",
        "quotes": output,
        "sourceRows": len(output),
        "reportedCurrency": "HKD",
        "stakeNormalized": False,
        "tableDataRows": english["tableDataRows"],
        "deferredNonmonetaryRows": english["deferredNonmonetaryRows"],
    }


def candidate(text, race_id, language):
    """Keep this field family unavailable on drift; preserve valid race results."""
    from .public_results import Document

    try:
        return parse_dividend_table(Document(text).root, race_id, language)
    except RacingRejected as error:
        return {"state": "unqualified", "quotes": None, "code": str(error)}


def qualified_pair(left, right):
    if left is None or right is None:
        return {"state": "not_extracted", "quotes": None}
    if left.get("state") == "unqualified" or right.get("state") == "unqualified":
        return {
            "state": "unqualified",
            "quotes": None,
            "code": "DIVIDEND_SOURCE_LAYOUT_UNQUALIFIED",
            "languageErrors": {
                k: v.get("code")
                for k, v in [("en", left), ("zhHant", right)]
                if v.get("state") == "unqualified"
            },
        }
    try:
        return reconcile_dividends(left, right)
    except RacingRejected as error:
        return {"state": "unqualified", "quotes": None, "code": str(error)}


def validate_observation(value, race_id):
    if not isinstance(value, dict) or value.get("state") not in {
        "observed",
        "not_present",
        "not_extracted",
        "unqualified",
    }:
        raise RacingRejected("DIVIDEND_RECORD_INVALID")
    if set(value) - {
        "state",
        "quotes",
        "code",
        "sourceBasis",
        "stakeNormalized",
        "sourceRows",
        "reportedCurrency",
        "languageErrors",
        "tableDataRows",
        "deferredNonmonetaryRows",
    }:
        raise RacingRejected("DIVIDEND_RECORD_INVALID")
    if value["state"] != "observed":
        if value.get("quotes") is not None:
            raise RacingRejected("DIVIDEND_RECORD_INVALID")
        return value
    quotes = value.get("quotes")
    seen = set()
    source_rows = set()
    if (
        not isinstance(quotes, list)
        or not 1 <= len(quotes) <= 200
        or type(value.get("sourceRows")) is not int
        or value.get("sourceRows") != len(quotes)
        or value.get("stakeNormalized") is not False
        or value.get("reportedCurrency") != "HKD"
        or type(value.get("tableDataRows")) is not int
        or type(value.get("deferredNonmonetaryRows")) is not int
        or not 0 <= value["deferredNonmonetaryRows"] <= 200
        or not 1 <= value["tableDataRows"] <= 200
        or value["tableDataRows"] != len(quotes) + value["deferredNonmonetaryRows"]
    ):
        raise RacingRejected("DIVIDEND_RECORD_INVALID")
    for quote in quotes:
        try:
            if set(quote) != {
                "id",
                "raceId",
                "pool",
                "poolSource",
                "winningCombinationRaw",
                "combinationKey",
                "amount",
                "amountRaw",
                "currency",
                "stakeAmount",
                "stakeCurrency",
                "stakeBasis",
                "sourceRow",
                "sourceLanguage",
                "sources",
            }:
                raise ValueError()
            key = quote["pool"], quote["combinationKey"]
            if (
                key in seen
                or canonical_pool(quote["pool"], "en") != quote["pool"]
                or quote["raceId"] != race_id
                or quote["id"] != "hkjc:dividend:v1:" + checksum([race_id, *key])
                or quote["combinationKey"]
                != combination_key(quote["winningCombinationRaw"], quote["pool"], "en")
            ):
                raise ValueError()
            if (
                quote["currency"] != "HKD"
                or quote["stakeAmount"] is not None
                or quote["stakeCurrency"] is not None
                or quote["stakeBasis"] != "not_stated_in_captured_table"
                or amount(quote["amountRaw"]) != quote["amount"]
            ):
                raise ValueError()
            source = quote["sources"]
            en, zh = source["en"], source["zhHant"]
            if set(source) != {"en", "zhHant"} or any(
                set(v) != {"pool", "combination", "amount"} for v in source.values()
            ):
                raise ValueError()
            if (
                en["pool"] != quote["pool"]
                or quote["poolSource"] != en["pool"]
                or quote["winningCombinationRaw"] != en["combination"]
                or quote["amountRaw"] != en["amount"]
                or quote["sourceLanguage"] != "en"
                or type(quote["sourceRow"]) is not int
                or not 1 <= quote["sourceRow"] <= value["tableDataRows"]
                or quote["sourceRow"] in source_rows
                or canonical_pool(zh["pool"], "zhHant") != quote["pool"]
                or any(
                    combination_key(r["combination"], quote["pool"], lang) != key[1]
                    or Decimal(amount(r["amount"])) != Decimal(quote["amount"])
                    for lang, r in (("en", en), ("zhHant", zh))
                )
            ):
                raise ValueError()
        except (KeyError, TypeError, ValueError, ArithmeticError) as error:
            raise RacingRejected("DIVIDEND_RECORD_INVALID") from error
        seen.add(key)
        source_rows.add(quote["sourceRow"])
    return value
