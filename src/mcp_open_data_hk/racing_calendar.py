"""Official public fixture inventory; programme counts are distinct from results."""

import re
from datetime import date
from urllib.parse import parse_qs, urlsplit

from .curated.racing.public_results import Document, result_url
from .curated.racing.prototype_store import PilotCollector
from .curated.racing.policy import RacingRejected

FIXTURE = "https://racing.hkjc.com/en-us/local/information/fixture"


def source_url(url):
    p = urlsplit(url)
    if p.path.endswith(("/horse", "/jockeyprofile", "/trainerprofile")):
        from .curated.racing.profiles import profile_selection

        profile_selection(url)
        return url
    if p.path.endswith("/local/information/fixture"):
        q = parse_qs(p.query)
        if (
            p.scheme != "https"
            or p.netloc != "racing.hkjc.com"
            or p.path != "/en-us/local/information/fixture"
            or p.fragment
            or set(q) - {"calyear", "calmonth"}
            or any(len(v) != 1 for v in q.values())
        ):
            raise RacingRejected("RACING_FIXTURE_ROUTE")
        if q and (
            set(q) != {"calyear", "calmonth"}
            or not re.fullmatch(r"20\d{2}", q["calyear"][0])
            or not re.fullmatch(r"0[1-9]|1[0-2]", q["calmonth"][0])
        ):
            raise RacingRejected("RACING_FIXTURE_PERIOD")
        return url
    return result_url(url)


def parse_fixture(text, url):
    source_url(url)
    root = Document(text).root
    periods = {
        n.text()
        for n in root.all()
        if re.fullmatch(r"(?:[1-9]|1[0-2])/20\d{2}", n.text())
    }
    if len(periods) != 1:
        raise RacingRejected("RACING_FIXTURE_LAYOUT")
    month, year = map(int, next(iter(periods)).split("/"))
    q = parse_qs(urlsplit(url).query)
    expected = (int(q["calyear"][0]), int(q["calmonth"][0])) if q else (year, month)
    if expected != (year, month):
        return {
            "kind": "fixture",
            "state": "period_unavailable",
            "requested": list(expected),
            "observed": [year, month],
            "meetings": [],
        }
    meetings = []
    for cell in root.all("td", "calendar"):
        venues = [
            n.attrs.get("alt")
            for n in cell.all("img")
            if n.attrs.get("alt") in {"HV", "ST"}
        ]
        if not venues:
            continue
        day = re.match(r"^(\d{1,2})\b", cell.text())
        if not day or len(venues) != 1:
            raise RacingRejected("RACING_FIXTURE_LAYOUT")
        value = date(year, month, int(day[1]))
        meetings.append(
            {
                "date": value.isoformat(),
                "venue": venues[0],
                "plannedRaces": sum(map(int, re.findall(r"\((\d+)\)", cell.text()))),
                "basis": "official_fixture_programme",
                "programmeStatusRaw": (
                    cell.text()[:500]
                    if not re.findall(r"\((\d+)\)", cell.text())
                    else None
                ),
            }
        )
    if not meetings or len({(m["date"], m["venue"]) for m in meetings}) != len(
        meetings
    ):
        raise RacingRejected("RACING_FIXTURE_INVENTORY")
    return {
        "kind": "fixture",
        "state": "available",
        "year": year,
        "month": month,
        "meetings": meetings,
    }


class CalendarCollector(PilotCollector):
    validate_url = staticmethod(source_url)
    parse_page = staticmethod(parse_fixture)

    def month(self, year, month, client=None):
        import httpx

        url = FIXTURE + f"?calyear={year:04d}&calmonth={month:02d}"
        with (
            self.store.collector_lock(),
            client
            or httpx.Client(
                timeout=15,
                follow_redirects=False,
                headers={"User-Agent": "mcp.hk-racing/1.0"},
            ) as transport,
        ):
            return self.fetch(url, transport)
