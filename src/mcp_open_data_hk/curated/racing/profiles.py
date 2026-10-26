"""Dated professional profile facts from fixed public HKJC profile pages.

No biographies, contact information, media or current values copied into old races.
"""

import re
import copy
from datetime import datetime
from decimal import Decimal
from urllib.parse import parse_qs, urlsplit, urljoin

from .normalize import decimal_text, participant, race
from .policy import RacingRejected, checksum, utc
from .public_results import Document, cells

PATHS = {"horse": "horse", "jockey": "jockeyprofile", "trainer": "trainerprofile"}
LABELS = {
    "originAge": ("Country of Origin / Age", "出生地 / 馬齡"),
    "colourSex": ("Colour / Sex", "毛色 / 性別"),
    "importType": ("Import Type", "進口類別"),
    "seasonStakes": ("Season Stakes*", "今季獎金*"),
    "totalStakes": ("Total Stakes*", "總獎金*"),
    "careerPlacings": ("No. of 1-2-3-Starts*", "冠-亞-季-總出賽次數*"),
    "recentStarts": (
        "No. of starts in past 10 race meetings",
        "最近十個賽馬日 出賽場數",
    ),
    "locationArrival": ("Current Location (Arrival Date)", "現在位置 (到達日期)"),
    "importDate": ("Import Date", "進口日期"),
    "trainer": ("Trainer", "練馬師"),
    "owner": ("Owner", "馬主"),
    "rating": ("Current Rating", "現時評分"),
    "seasonStartRating": ("Start of Season Rating", "季初評分"),
    "sire": ("Sire", "父系"),
    "dam": ("Dam", "母系"),
    "damsSire": ("Dam's Sire", "外祖父"),
    "nationality": ("Nationality", "國籍"),
    "seasonWins": ("No. of Wins", "冠軍次數", "冠"),
    "seasonSeconds": ("No. of 2nds", "亞軍次數", "亞"),
    "seasonThirds": ("No. of 3rds", "季軍次數", "季"),
    "seasonFourths": ("No. of 4ths", "殿軍次數", "殿"),
    "seasonRides": ("Total Rides", "總出賽次數"),
    "seasonRunners": ("Total Runners", "出賽馬匹總數", "出馬總數"),
    "stakesWon": ("Stakes won", "所贏獎金"),
    "winPercentage": ("Win %", "勝出率"),
    "recentWins": (
        "No. of Wins in past 10 race days",
        "最近十個賽馬日頭馬次數",
        "過去10個賽馬日獲勝次數",
    ),
}
NUMBERS = {
    "age",
    "recentStarts",
    "rating",
    "seasonStartRating",
    "seasonWins",
    "seasonSeconds",
    "seasonThirds",
    "seasonFourths",
    "seasonRides",
    "seasonRunners",
    "recentWins",
    "winPercentage",
}
MONEY = {"seasonStakes", "totalStakes", "stakesWon"}
HISTORY_LABELS = (
    "Race Index",
    "Pla.",
    "Date",
    "RC /Track/ Course",
    "Dist.",
    "Going",
    "G",
    "Class",
    "Race Class",
    "Dr.",
    "Rating",
    "Rtg.",
    "Trainer",
    "Jockey",
    "LBW",
    "Win Odds",
    "Act. Wt.",
    "Running Position",
    "Finish Time",
    "Declar. Horse Wt.",
    "Gear",
    "場次",
    "名次",
    "日期",
    "馬場/跑道/ 賽道",
    "途程",
    "場地 狀況",
    "賽事 班次",
    "檔位",
    "評分",
    "練馬師",
    "騎師",
    "頭馬 距離",
    "獨贏 賠率",
    "實際 負磅",
    "沿途 走位",
    "完成 時間",
    "排位 體重",
    "配備",
)
MEDIA_LABELS = ("Video Replay", "賽事重溫", "賽事片段", "賽事重播")


def label_key(value):
    return re.sub(r"\s+", "", value).strip(":：*").casefold()


LOOKUP = {label_key(label): key for key, labels in LABELS.items() for label in labels}


def profile_url(kind, source_id, lang="en-us"):
    if kind not in PATHS or lang not in {"en-us", "zh-hk"}:
        raise RacingRejected("PROFILE_ROUTE_UNQUALIFIED")
    pattern = r"HK_[0-9]{4}_[A-Z][0-9]{3}" if kind == "horse" else r"[A-Z0-9]{1,16}"
    if not isinstance(source_id, str) or not re.fullmatch(pattern, source_id):
        raise RacingRejected("INVALID_PROFILE_ID")
    suffix = "" if kind == "horse" else "&Season=Current"
    return f"https://racing.hkjc.com/{lang}/local/information/{PATHS[kind]}?{kind}id={source_id}{suffix}"


def profile_selection(url):
    parsed = urlsplit(url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    lowered = {key.lower(): value for key, value in query.items()}
    if (
        parsed.scheme != "https"
        or parsed.netloc != "racing.hkjc.com"
        or parsed.fragment
        or len(lowered) != len(query)
        or any(len(v) != 1 for v in lowered.values())
    ):
        raise RacingRejected("PROFILE_ROUTE_UNQUALIFIED")
    for kind, path in PATHS.items():
        for lang in ("en-us", "zh-hk"):
            if parsed.path != f"/{lang}/local/information/{path}":
                continue
            if set(lowered) != (
                {kind + "id"} if kind == "horse" else {kind + "id", "season"}
            ) or lowered.get("season", ["Current"]) != ["Current"]:
                break
            source_id = lowered[kind + "id"][0]
            profile_url(kind, source_id, lang)
            return kind, source_id, lang
    raise RacingRejected("PROFILE_ROUTE_UNQUALIFIED")


def numeric(raw, percentage=False):
    if raw in {"", "-", "--", "---"}:
        return None
    value = raw.rstrip("%") if percentage else raw
    if not re.fullmatch(r"(?:[0-9]{1,3}(?:,[0-9]{3})*|[0-9]+)(?:\.[0-9]+)?", value):
        raise RacingRejected("PROFILE_NUMBER_SCHEMA")
    return decimal_text(value.replace(",", ""))


def chinese_number(raw):
    digits = {char: str(index) for index, char in enumerate("零一二三四五六七八九")}
    digits.update({"〇": "0", "兩": "2"})
    if not raw or len(raw) > 32:
        raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
    parts = raw.split("點")
    if not parts[0] or len(parts) == 2 and not parts[1]:
        raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
    if len(parts) > 2 or any(c not in digits for c in parts[-1]) and len(parts) == 2:
        raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
    text = parts[0]
    if all(c in digits for c in text):
        integer = int("".join(digits[c] for c in text))
    else:
        total = section = number = 0
        seen_wan = False
        last_unit = 10000
        for char in text:
            if char in digits:
                if number:
                    raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
                number = int(digits[char])
            elif char in {"十", "百", "千"}:
                unit = {"十": 10, "百": 100, "千": 1000}[char]
                if unit >= last_unit:
                    raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
                section += (number or 1) * unit
                number = 0
                last_unit = unit
            elif char == "萬":
                if seen_wan or section + number == 0:
                    raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
                total += (section + number) * 10000
                seen_wan = True
                section = number = 0
                last_unit = 10000
            else:
                raise RacingRejected("PROFILE_NUMERAL_SCHEMA")
        integer = total + section + number
    fraction = "." + "".join(digits[c] for c in parts[1]) if len(parts) == 2 else ""
    return decimal_text(str(integer) + fraction)


def history_identity(href):
    href = urljoin("https://racing.hkjc.com", href)
    parsed = urlsplit(href)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "racing.hkjc.com"
        or parsed.fragment
    ):
        return None
    if not (
        parsed.path.endswith("/localresults")
        or parsed.path.endswith("/Racing/LocalResults.aspx")
    ):
        return None
    original = parse_qs(parsed.query, keep_blank_values=True)
    query = {key.lower(): value for key, value in original.items()}
    if (
        len(original) != len(query)
        or set(query) - {"racedate", "racecourse", "raceno"}
        or any(len(v) != 1 for v in query.values())
    ):
        return None
    try:
        day = datetime.strptime(query["racedate"][0], "%Y/%m/%d").date().isoformat()
        venue, number = query["racecourse"][0], int(query["raceno"][0])
        return {
            "raceId": race(day, venue, number),
            "date": day,
            "venue": venue,
            "raceNumber": number,
            "sourceUrl": href,
        }
    except (ValueError, KeyError):
        return None


def parse_profile(text, url, observed_at):
    kind, source_id, lang = profile_selection(url)
    observed = utc(observed_at)
    root = Document(text).root
    # The provider's exact resource key must occur in the returned document.
    if not re.search(
        r"(?<![A-Za-z0-9_])" + re.escape(source_id) + r"(?![A-Za-z0-9_])", text
    ):
        raise RacingRejected("PROFILE_IDENTITY_UNQUALIFIED")
    rows = [(tr, [c.text() for c in cells(tr)]) for tr in root.all("tr")]
    small = [
        values[0]
        for _, values in rows
        if len(values) == 1 and 0 < len(values[0]) <= 200
    ]
    if kind == "horse":
        code = source_id.rsplit("_", 1)[1]
        candidates = [
            m[1].strip()
            for value in small
            if (m := re.fullmatch(r"(.{1,180})\s+\(" + re.escape(code) + r"\)", value))
        ]
    else:
        candidates = [
            small[i - 1]
            for i, value in enumerate(small)
            if i and re.fullmatch(r"(?:Age|年齡)\s*[:：]\s*[0-9]{1,2}(?:歲)?", value)
        ]
    if len(set(candidates)) != 1:
        raise RacingRejected("PROFILE_NAME_SCHEMA")
    attributes = {}
    for _, values in rows:
        for i, label in enumerate(values):
            key = LOOKUP.get(label_key(label))
            if not key or i + 1 >= len(values):
                continue
            raw = values[i + 1]
            if raw in {":", "："} and i + 2 < len(values):
                raw = values[i + 2]
            elif not re.match(r"^[:：]", raw):
                # Column headings such as Trainer also occur in form tables.
                # Only the source's colon-paired attribute cells define a field.
                continue
            raw = re.sub(r"^[:：]\s*", "", raw).strip()
            if len(raw) > 500 or key in attributes and attributes[key]["raw"] != raw:
                raise RacingRejected("PROFILE_ATTRIBUTE_CONFLICT")
            field = {"raw": raw, "sourceLabel": label, "value": None}
            if key in NUMBERS:
                field["value"] = numeric(raw, key == "winPercentage")
            elif key in MONEY:
                money = re.fullmatch(r"(HK\$|\$|HKD\s*)(.*)", raw)
                if money:
                    field.update(
                        value=numeric(money[2]),
                        currency="HKD" if money[1].strip() in {"HK$", "HKD"} else None,
                        currencySymbol=money[1].strip(),
                    )
            elif key == "careerPlacings":
                match = re.fullmatch(r"([0-9]+)-([0-9]+)-([0-9]+)-([0-9]+)", raw)
                if not match or sum(map(int, match.groups()[:3])) > int(match[4]):
                    raise RacingRejected("PROFILE_CAREER_COUNTS")
                field["value"] = dict(
                    zip(
                        ("wins", "seconds", "thirds", "starts"),
                        map(int, match.groups()),
                    )
                )
            attributes[key] = field
    for value in small:
        age = re.fullmatch(r"(?:Age|年齡)\s*[:：]\s*([0-9]{1,2})(?:歲)?", value)
        if age:
            attributes["age"] = {
                "raw": age[1],
                "value": numeric(age[1]),
                "sourceLabel": "Age" if lang == "en-us" else "年齡",
            }
    required = (
        {"originAge", "colourSex", "careerPlacings", "rating"}
        if kind == "horse"
        else {"seasonWins", "winPercentage"}
    )
    if not required <= attributes.keys():
        raise RacingRejected("PROFILE_REQUIRED_FIELDS")
    if any(
        bool(re.search(r"[\u3400-\u9fff]", attributes[key]["sourceLabel"]))
        != (lang == "zh-hk")
        for key in required
    ):
        raise RacingRejected("PROFILE_LANGUAGE_SCHEMA")
    periods = [
        value
        for value in small
        if re.search(r"Season.*Race Meeting|馬季.*(?:賽馬日|賽事日)", value, re.I)
    ]
    cutoff = {
        "raw": None,
        "value": None,
        "precision": "unknown",
        "basis": "source_statistics_cutoff",
    }
    if periods:
        if len(set(periods)) != 1:
            raise RacingRejected("PROFILE_PERIOD_CONFLICT")
        cutoff["raw"] = periods[0]
        dates = re.findall(r"[0-3]?[0-9]/[01]?[0-9]/20[0-9]{2}", periods[0])
        if len(dates) == 1:
            cutoff.update(
                value=datetime.strptime(dates[0], "%d/%m/%Y").date().isoformat(),
                precision="day",
            )
    history, header = [], None
    for node, values in rows:
        if len(values) >= 10 and values[0] in {"Race Index", "場次"}:
            header = values
            continue
        if (
            header is None
            or len(values) != len(header)
            or not re.fullmatch(r"[0-9]{1,4}", values[0])
        ):
            continue
        links = [
            identity
            for link in node.all("a")
            if (identity := history_identity(link.attrs.get("href", ""))) is not None
        ]
        unique = {link["raceId"]: link for link in links}
        if len(unique) > 1:
            raise RacingRejected("PROFILE_HISTORY_IDENTITY")
        fields = {
            key: value
            for key, value in zip(header, values)
            if label_key(key) not in {label_key(k) for k in MEDIA_LABELS}
        }
        if any(
            label_key(key) not in {label_key(k) for k in HISTORY_LABELS}
            for key in fields
        ):
            raise RacingRejected("PROFILE_HISTORY_SCHEMA")
        history.append(
            {
                "sourceAnnualIndex": values[0],
                "fields": fields,
                "race": next(iter(unique.values())) if unique else None,
            }
        )
    if len(history) > 500 or len({checksum(r) for r in history}) != len(history):
        raise RacingRejected("PROFILE_HISTORY_BOUNDS")
    career = None
    for value in small:
        english = re.fullmatch(
            r"Hong Kong Career Wins \(at start of (20[0-9]{2}/[0-9]{2}) season\): ([0-9,]+) \(win strike rate:? ([0-9.]+)%\)\.",
            value,
        )
        chinese = re.fullmatch(
            r"在港累積頭馬（截至(20[0-9]{2}/[0-9]{2})馬季開始時）： (.+)場（勝出率：百分之(.+)）。",
            value,
        )
        if english or chinese:
            matched = english or chinese
            career = {
                "raw": value,
                "season": matched[1],
                "asOf": "source_season_start",
                "effectiveDate": None,
                "hongKongWins": (
                    numeric(matched[2]) if english else chinese_number(matched[2])
                ),
                "winPercentage": (
                    numeric(matched[3]) if english else chinese_number(matched[3])
                ),
            }
    facts = {
        "participantId": participant(kind, source_id),
        "kind": kind,
        "sourceId": source_id,
        "language": lang,
        "name": candidates[0],
        "attributes": attributes,
        "statisticsCutoff": cutoff,
        "careerAtSeasonStart": career,
        "formHistory": history,
    }
    observation = dict(
        facts,
        observedAt=observed.isoformat(),
        effectiveAt=None,
        sourceUrl=url,
        factsSha256=checksum(facts),
        coverage={
            "scope": "professional_profile_fields_and_displayed_form_rows",
            "historyRows": len(history),
            "completeCareerHistory": False,
            "currentValuesAppliedToPastRaces": False,
            "rawHtmlRetained": False,
            "biographyAndMediaRepublished": False,
        },
    )
    validate_observation(observation)
    return observation


def validate_observation(value):
    """Imports admit the same bounded factual fields as the provider parser."""
    if set(value) != {
        "participantId",
        "kind",
        "sourceId",
        "language",
        "name",
        "attributes",
        "statisticsCutoff",
        "careerAtSeasonStart",
        "formHistory",
        "observedAt",
        "effectiveAt",
        "sourceUrl",
        "factsSha256",
        "coverage",
    }:
        raise RacingRejected("PROFILE_FIELDS_UNQUALIFIED")
    kind, source_id, language = profile_selection(value["sourceUrl"])
    if (
        (kind, source_id, language)
        != (value["kind"], value["sourceId"], value["language"])
        or value["participantId"] != participant(kind, source_id)
        or value["effectiveAt"] is not None
        or not isinstance(value["name"], str)
        or not 1 <= len(value["name"]) <= 180
    ):
        raise RacingRejected("PROFILE_CAPTURE_IDENTITY")
    cutoff = value["statisticsCutoff"]
    if (
        set(cutoff) != {"raw", "value", "precision", "basis"}
        or cutoff["basis"] != "source_statistics_cutoff"
        or cutoff["precision"] not in {"day", "unknown"}
    ):
        raise RacingRejected("PROFILE_PERIOD_SCHEMA")
    if cutoff["raw"] is not None and (
        not isinstance(cutoff["raw"], str) or len(cutoff["raw"]) > 200
    ):
        raise RacingRejected("PROFILE_PERIOD_SCHEMA")
    if (
        cutoff["value"] is not None
        and datetime.fromisoformat(cutoff["value"]).date()
        > utc(value["observedAt"]).date()
    ):
        raise RacingRejected("PROFILE_PERIOD_FUTURE")
    for key, field in value["attributes"].items():
        if (
            key not in LABELS
            and key != "age"
            or not {"raw", "sourceLabel", "value"} <= set(field)
            or set(field)
            - {"raw", "sourceLabel", "value", "currency", "currencySymbol"}
            or not isinstance(field["raw"], str)
            or len(field["raw"]) > 500
            or (key != "age" and LOOKUP.get(label_key(field["sourceLabel"])) != key)
            or key == "age"
            and field["sourceLabel"] not in {"Age", "年齡"}
        ):
            raise RacingRejected("PROFILE_FIELDS_UNQUALIFIED")
        if key in NUMBERS and field["value"] != numeric(
            field["raw"], key == "winPercentage"
        ):
            raise RacingRejected("PROFILE_NUMBER_SCHEMA")
        if (
            key == "winPercentage"
            and field["value"] is not None
            and Decimal(field["value"]) > 100
        ):
            raise RacingRejected("PROFILE_NUMBER_SCHEMA")
        if key in MONEY:
            match = re.fullmatch(r"(HK\$|\$|HKD\s*)(.*)", field["raw"])
            expected = numeric(match[2]) if match else None
            currency = "HKD" if match and match[1].strip() in {"HK$", "HKD"} else None
            if field["value"] != expected or field.get("currency") != currency:
                raise RacingRejected("PROFILE_MONEY_SCHEMA")
        elif key == "careerPlacings":
            match = re.fullmatch(r"([0-9]+)-([0-9]+)-([0-9]+)-([0-9]+)", field["raw"])
            if (
                not match
                or field["value"]
                != dict(
                    zip(
                        ("wins", "seconds", "thirds", "starts"),
                        map(int, match.groups()),
                    )
                )
                or sum(map(int, match.groups()[:3])) > int(match[4])
            ):
                raise RacingRejected("PROFILE_CAREER_COUNTS")
        elif key not in NUMBERS and field["value"] is not None:
            raise RacingRejected("PROFILE_FIELDS_UNQUALIFIED")
    career = value["careerAtSeasonStart"]
    if career is not None:
        if (
            set(career)
            != {
                "raw",
                "season",
                "asOf",
                "effectiveDate",
                "hongKongWins",
                "winPercentage",
            }
            or not isinstance(career["raw"], str)
            or len(career["raw"]) > 500
            or not re.fullmatch(r"20[0-9]{2}/[0-9]{2}", career["season"])
            or career["asOf"] != "source_season_start"
            or career["effectiveDate"] is not None
            or numeric(career["hongKongWins"]) != career["hongKongWins"]
            or not re.fullmatch("[0-9]+", career["hongKongWins"])
            or numeric(career["winPercentage"]) != career["winPercentage"]
            or Decimal(career["winPercentage"]) > 100
        ):
            raise RacingRejected("PROFILE_CAREER_SCHEMA")
    history = value["formHistory"]
    if not isinstance(history, list) or len(history) > 500:
        raise RacingRejected("PROFILE_HISTORY_BOUNDS")
    if len({checksum(row) for row in history}) != len(history):
        raise RacingRejected("PROFILE_HISTORY_BOUNDS")
    for row in history:
        if (
            set(row) != {"sourceAnnualIndex", "fields", "race"}
            or not re.fullmatch("[0-9]{1,4}", row["sourceAnnualIndex"])
            or any(
                label_key(k) not in {label_key(label) for label in HISTORY_LABELS}
                or not isinstance(v, str)
                or len(v) > 500
                for k, v in row["fields"].items()
            )
        ):
            raise RacingRejected("PROFILE_HISTORY_SCHEMA")
        if (
            row["race"] is not None
            and history_identity(row["race"]["sourceUrl"]) != row["race"]
        ):
            raise RacingRejected("PROFILE_HISTORY_IDENTITY")
    coverage = value["coverage"]
    if coverage != {
        "scope": "professional_profile_fields_and_displayed_form_rows",
        "historyRows": len(history),
        "completeCareerHistory": False,
        "currentValuesAppliedToPastRaces": False,
        "rawHtmlRetained": False,
        "biographyAndMediaRepublished": False,
    }:
        raise RacingRejected("PROFILE_COVERAGE_SCHEMA")
    facts = {
        k: v
        for k, v in value.items()
        if k
        not in {"observedAt", "effectiveAt", "sourceUrl", "factsSha256", "coverage"}
    }
    if checksum(facts) != value["factsSha256"]:
        raise RacingRejected("PROFILE_FACT_CHECKSUM")
    return value


def normalize_retained_observation(value):
    """Remove only known replay columns from earlier normalized captures.

    Preserve the original capture/time and validate the input fact checksum first.
    This never invents a new raw fetch or a raw-parser transform identity.
    """
    media = {label_key(k) for k in MEDIA_LABELS}
    if not any(
        label_key(k) in media for row in value["formHistory"] for k in row["fields"]
    ):
        return value
    facts = {
        k: v
        for k, v in value.items()
        if k
        not in {"observedAt", "effectiveAt", "sourceUrl", "factsSha256", "coverage"}
    }
    if checksum(facts) != value["factsSha256"]:
        raise RacingRejected("PROFILE_FACT_CHECKSUM")
    result = copy.deepcopy(value)
    for row in result["formHistory"]:
        row["fields"] = {
            k: v for k, v in row["fields"].items() if label_key(k) not in media
        }
    facts = {
        k: v
        for k, v in result.items()
        if k
        not in {"observedAt", "effectiveAt", "sourceUrl", "factsSha256", "coverage"}
    }
    result["factsSha256"] = checksum(facts)
    return result


def merge_profiles(english, chinese):
    if (
        english["language"] != "en-us"
        or chinese["language"] != "zh-hk"
        or any(
            english[key] != chinese[key]
            for key in ("participantId", "kind", "sourceId")
        )
    ):
        raise RacingRejected("PROFILE_BILINGUAL_IDENTITY")
    if english["statisticsCutoff"]["value"] != chinese["statisticsCutoff"]["value"]:
        raise RacingRejected("PROFILE_BILINGUAL_PERIOD")
    attributes = {}
    for key in english["attributes"].keys() | chinese["attributes"].keys():
        left, right = english["attributes"].get(key), chinese["attributes"].get(key)
        if key in NUMBERS | MONEY or key == "careerPlacings":
            if left is None or right is None or left["value"] != right["value"]:
                raise RacingRejected("PROFILE_BILINGUAL_FACTS")
        attributes[key] = {"en": left, "zhHant": right}
    left, right = english["careerAtSeasonStart"], chinese["careerAtSeasonStart"]
    if (
        bool(left) != bool(right)
        or left
        and (
            left["season"] != right["season"]
            or Decimal(left["hongKongWins"]) != Decimal(right["hongKongWins"])
            or Decimal(left["winPercentage"]) != Decimal(right["winPercentage"])
        )
    ):
        raise RacingRejected("PROFILE_BILINGUAL_CAREER")
    if len(english["formHistory"]) != len(chinese["formHistory"]):
        raise RacingRejected("PROFILE_BILINGUAL_HISTORY")

    def identities(rows):
        return sorted(row["race"]["raceId"] for row in rows if row["race"])

    if identities(english["formHistory"]) != identities(chinese["formHistory"]):
        raise RacingRejected("PROFILE_BILINGUAL_HISTORY")
    if sorted(r["sourceAnnualIndex"] for r in english["formHistory"]) != sorted(
        r["sourceAnnualIndex"] for r in chinese["formHistory"]
    ):
        raise RacingRejected("PROFILE_BILINGUAL_HISTORY")
    facts = {
        "participantId": english["participantId"],
        "kind": english["kind"],
        "sourceId": english["sourceId"],
        "name": english["name"],
        "nameZhHant": chinese["name"],
        "attributes": attributes,
        "careerAtSeasonStart": {"en": left, "zhHant": right},
        "statisticsCutoff": english["statisticsCutoff"],
        "formHistory": {"en": english["formHistory"], "zhHant": chinese["formHistory"]},
    }
    return dict(
        facts,
        factsSha256=checksum(facts),
        observations={"en": english["observedAt"], "zhHant": chinese["observedAt"]},
        effectiveAt=None,
        coverage=english["coverage"],
    )
