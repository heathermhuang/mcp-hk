"""Parse factual public results pages for the private development prototype.

This module does not grant a source licence or enable any production data mode.
It deliberately excludes commentary, media, profiles and betting functionality.
"""

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlsplit

from .normalize import decimal_text, meeting, participant, race, result_row
from .policy import RacingRejected, checksum

ORIGIN = "https://racing.hkjc.com"
PATHS = {f"/{lang}/local/information/localresults" for lang in ("en-us", "zh-hk")}
ARCHIVE_PATHS = {
    f"/{lang}/local/information/archive/localresults" for lang in ("en-us", "zh-hk")
}
COLUMNS = (
    ("Pla.", "名次"),
    ("Horse No.", "馬號"),
    ("Horse", "馬名"),
    ("Jockey", "騎師"),
    ("Trainer", "練馬師"),
    ("Act. Wt.", "實際負磅"),
    ("Declar. Horse Wt.", "排位體重"),
    ("Dr.", "檔位"),
    ("LBW", "頭馬距離"),
    ("Running Position", "沿途走位"),
    ("Finish Time", "完成時間"),
    ("Win Odds", "獨贏賠率"),
)
VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent, self.children = tag, dict(attrs), parent, []

    def all(self, tag=None, cls=None):
        found = []
        for child in self.children:
            if isinstance(child, Node):
                if (tag is None or child.tag == tag) and (
                    cls is None or cls in child.attrs.get("class", "").split()
                ):
                    found.append(child)
                found.extend(child.all(tag, cls))
        return found

    def one(self, tag=None, cls=None):
        found = self.all(tag, cls)
        if len(found) != 1:
            raise RacingRejected("PUBLIC_RESULTS_LAYOUT_DRIFT")
        return found[0]

    def text(self):
        return " ".join(
            " ".join(
                c.text() if isinstance(c, Node) else c for c in self.children
            ).split()
        )


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        if len(text.encode("utf-8")) > 400 * 1024:
            raise RacingRejected("RESULT_BODY_LIMIT")
        self.root = self.current = Node("document")
        self.feed(text)
        self.close()

    def handle_starttag(self, tag, attrs):
        child = Node(tag, attrs, self.current)
        self.current.children.append(child)
        if tag not in VOID:
            self.current = child

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def result_url(value):
    """Exact public results route only; no credentials, fragments or arbitrary URLs."""
    url = urlsplit(value)
    query = parse_qs(url.query, keep_blank_values=True)
    lowered = {k.lower(): v for k, v in query.items()}
    if (
        url.scheme != "https"
        or url.netloc != "racing.hkjc.com"
        or url.fragment
        or url.path not in PATHS | ARCHIVE_PATHS
        or len(lowered) != len(query)
        or set(lowered) - {"racedate", "racecourse", "raceno"}
        or any(len(v) != 1 for v in lowered.values())
        or not re.fullmatch(r"\d{4}/\d{2}/\d{2}", lowered.get("racedate", [""])[0])
        or lowered.get("racecourse", ["HV"])[0] not in {"HV", "ST"}
        or not re.fullmatch(r"[1-9]|1[0-9]|20", lowered.get("raceno", ["1"])[0])
    ):
        raise RacingRejected("DEVELOPMENT_ROUTE_REJECTED")
    return value


def archive_redirect(original, location):
    """The observed public archive redirect, with identical meeting/race/language.

    No arbitrary redirect, credential, fragment, extra query or second hop is
    accepted. The actual 15 July redirect was independently hash-matched to this
    route; this does not qualify any other provider redirect or source family.
    """
    result_url(original)
    source = urlsplit(original)
    if (
        source.path not in PATHS
        or not isinstance(location, str)
        or len(location) > 1000
    ):
        raise RacingRejected("RACING_ARCHIVE_REDIRECT_REJECTED")
    target = urljoin(original, location)
    result_url(target)
    dest = urlsplit(target)
    source_query = {k.lower(): v for k, v in parse_qs(source.query).items()}
    target_query = {k.lower(): v for k, v in parse_qs(dest.query).items()}
    if (
        dest.path != source.path.replace("/localresults", "/archive/localresults")
        or source_query != target_query
    ):
        raise RacingRejected("RACING_ARCHIVE_REDIRECT_REJECTED")
    return target


def cells(row):
    return [c for c in row.children if isinstance(c, Node) and c.tag in {"td", "th"}]


def nullable(value):
    return None if value in {"", "---", "--", "-"} else value


def identity(cell, kind):
    path, key = {
        "horse": ("horse", "horseid"),
        "jockey": ("jockeyprofile", "jockeyid"),
        "trainer": ("trainerprofile", "trainerid"),
    }[kind]
    links = []
    for node in cell.all("a"):
        href = urljoin(ORIGIN, node.attrs.get("href", ""))
        parsed = urlsplit(href)
        query = {k.lower(): v for k, v in parse_qs(parsed.query).items()}
        if (
            parsed.scheme == "https"
            and parsed.netloc == "racing.hkjc.com"
            and parsed.path.endswith("/" + path)
            and key in query
            and len(query[key]) == 1
        ):
            links.append((node, query[key][0], href))
    if len(links) != 1:
        raise RacingRejected("PUBLIC_PARTICIPANT_ID_REQUIRED")
    node, source_id, href = links[0]
    if not node.text() or len(node.text()) > 200:
        raise RacingRejected("PUBLIC_PARTICIPANT_NAME_REQUIRED")
    return {
        "id": participant(kind, source_id),
        "sourceId": source_id,
        "name": node.text(),
        "sourceUrl": href,
    }


def parse_results(text, url):
    result_url(url)
    root = Document(text).root
    content = root.one(cls="localResults")
    selected = content.one(cls="raceMeeting_select").all("span")[0].text()
    day_match = re.search(r"(\d{2})/(\d{2})/(\d{4})", selected)
    if not day_match:
        raise RacingRejected("MEETING_DATE_REQUIRED")
    day = "-".join((day_match[3], day_match[2], day_match[1]))
    venue = (
        "HV"
        if any(v in selected for v in ("Happy Valley", "跑馬地"))
        else "ST" if any(v in selected for v in ("Sha Tin", "沙田")) else None
    )
    if (
        venue is None
        or day.replace("-", "/")
        != {k.lower(): v for k, v in parse_qs(urlsplit(url).query).items()}["racedate"][
            0
        ]
    ):
        raise RacingRejected("MEETING_IDENTITY_MISMATCH")
    info = content.one(cls="race_tab").all("table")[0]
    heading = info.one("thead").text()
    number = re.search(r"(?:RACE\s+|第\s*)(\d+)\s*(?:場\s*)?\((\d+)\)", heading)
    if not number:
        raise RacingRejected("PUBLIC_RACE_ID_REQUIRED")
    number, annual_index = int(number[1]), int(number[2])
    query_number = {k.lower(): v for k, v in parse_qs(urlsplit(url).query).items()}.get(
        "raceno"
    )
    if query_number and number != int(query_number[0]):
        raise RacingRejected("RACE_IDENTITY_MISMATCH")
    race_id = race(day, venue, number)
    inventory = {number: url}
    for node in content.one(cls="top_races").all("a"):
        href = urljoin(ORIGIN, node.attrs.get("href", ""))
        p = urlsplit(href)
        q = {k.lower(): v for k, v in parse_qs(p.query).items()}
        if (
            p.path in PATHS | ARCHIVE_PATHS
            and q.get("racecourse") == [venue]
            and q.get("racedate") == [day.replace("-", "/")]
        ):
            result_url(href)
            inventory[int(q["raceno"][0])] = href
    if sorted(inventory) != list(range(1, max(inventory) + 1)):
        raise RacingRejected("MEETING_INVENTORY_GAP")
    table = content.one("table", "draggable")
    lookup = {
        re.sub(r"\s+", "", alias): i
        for i, aliases in enumerate(COLUMNS)
        for alias in aliases
    }
    header = [re.sub(r"\s+", "", c.text()) for c in cells(table.one("thead").one("tr"))]
    if (
        len(header) != 12
        or any(value not in lookup for value in header)
        or len({lookup[value] for value in header}) != 12
    ):
        raise RacingRejected("PUBLIC_RESULTS_LAYOUT_DRIFT")
    rows = []
    for tr in table.one("tbody").all("tr"):
        cols = cells(tr)
        if len(cols) != 12:
            raise RacingRejected("PUBLIC_RESULTS_LAYOUT_DRIFT")
        ordered = {lookup[h]: col for h, col in zip(header, cols)}
        cols = [ordered[i] for i in range(12)]
        values = [c.text() for c in cols]
        horse, jockey, trainer = (
            identity(cols[i], kind)
            for i, kind in ((2, "horse"), (3, "jockey"), (4, "trainer"))
        )
        row = result_row(
            {
                "horseId": horse["sourceId"],
                "horseNumber": nullable(values[1]),
                "draw": nullable(values[7]),
                "placing": values[0],
                "time": nullable(values[10]),
                "weightLb": nullable(values[5]),
                "claimLb": None,
                "marginRaw": values[8],
            },
            race_id,
        )
        row.update(
            horse=horse,
            jockey=jockey,
            trainer=trainer,
            bodyWeightLb=decimal_text(nullable(values[6]), nullable=True),
            winOddsFinal=decimal_text(nullable(values[11]), nullable=True),
            runningPositionsRaw=values[9],
        )
        row.pop("revision")
        row["revision"] = checksum(row)
        rows.append(row)
    if (
        not rows
        or len(rows) > 30
        or len({r["participantId"] for r in rows}) != len(rows)
    ):
        raise RacingRejected("DUPLICATE_OR_EMPTY_RUNNERS")
    winners = [r for r in rows if r["placing"] == 1]
    void = all(r["status"] == "race_void" for r in rows)
    if (not winners and not void) or any(r["status"] != "finished" for r in winners):
        raise RacingRejected("COMPLETED_RESULTS_REQUIRED")
    details = [cells(tr) for tr in info.one("tbody").all("tr")]
    details = [c for c in details if len(c) >= 3 and c[0].text()]
    distance = re.search(r"(\d{3,4})(?:M|米)", details[0][0].text())
    if not distance:
        raise RacingRejected("RACE_DISTANCE_REQUIRED")
    return {
        "meeting": {"id": meeting(day, venue), "date": day, "venue": venue},
        "inventory": inventory,
        "race": {
            "id": race_id,
            "number": number,
            "annualIndex": annual_index,
            "status": "void" if void else "completed",
            "distanceM": int(distance[1]),
            "classRaw": details[0][0].text(),
            "goingRaw": details[0][2].text(),
            "name": details[1][0].text(),
            "courseRaw": details[1][2].text(),
            "results": rows,
            "sourceUrl": url,
        },
    }
