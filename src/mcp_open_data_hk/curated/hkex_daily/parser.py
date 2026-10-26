"""Strict, non-executing parser for HKEX's four published daily summary layouts."""

import hashlib
import json
import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

BASE = "https://di.hkex.com.hk"
MENU = "/di/summary/NSMSumMenu.htm"
MAX_BODY = 2 * 1024 * 1024
FORMS = {"1", "2", "3A", "3B", "3C", "3D"}
POSITIONS = {"L": "long", "S": "short", "P": "lending_pool"}
SERIAL = re.compile(r"(?:IS|CS|DA|DB|DC|DD)[0-9]{8}[EC][0-9]{5}")
TRANSFORM = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
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


def canonical(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


class Node:
    def __init__(self, tag, attrs=()):
        self.tag, self.attrs, self.children = tag, dict(attrs), []

    def walk(self, tag):
        for child in self.children:
            if isinstance(child, Node):
                if child.tag == tag:
                    yield child
                yield from child.walk(tag)

    def text(self):
        if self.tag in {"script", "style"}:
            return ""
        return "".join(
            c.text() if isinstance(c, Node) else c for c in self.children
        ) + ("\n" if self.tag in {"br", "tr"} else "")

    def cells(self):
        return [
            c for c in self.children if isinstance(c, Node) and c.tag in {"td", "th"}
        ]


class Document(HTMLParser):
    def __init__(self, body):
        super().__init__(convert_charrefs=True)
        if not isinstance(body, bytes) or len(body) > MAX_BODY:
            raise ValueError("SUMMARY_BODY_LIMIT")
        self.root = Node("document")
        self.stack, self.nodes = [self.root], 0
        decoded = body.decode("utf-8-sig", errors="strict")
        if not re.search(r"</html>\s*$", decoded, re.I):
            raise ValueError("SOURCE_INCOMPLETE_HTML")
        self.feed(decoded)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.nodes += 1
        if self.nodes > 60000 or len(self.stack) > 48:
            raise ValueError("SUMMARY_STRUCTURE_LIMIT")
        node = Node(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, value):
        self.stack[-1].children.append(value)


def text(node):
    return " ".join(node.text().split())


def report_path(day, category):
    if type(day) is not date or category not in (1, 2, 3, 4):
        raise ValueError("INVALID_SUMMARY_KEY")
    return "/di/summary/DSM" + day.strftime("%Y%m%d") + f"C{category}.htm"


def parse_menu(body):
    root = Document(body).root
    days, categories = set(), set()
    for link in root.walk("a"):
        href = link.attrs.get("href", "")
        m = re.fullmatch(r"(?:/di/summary/)?DSM([0-9]{8})C([1-4])\.htm", href)
        if m:
            days.add(datetime.strptime(m[1], "%Y%m%d").date())
            categories.add(int(m[2]))
    if len(days) != 1 or categories != {1, 2, 3, 4}:
        raise ValueError("SUMMARY_MENU_SCHEMA_CHANGED")
    return days.pop()


def decimal(value):
    value = value.strip().replace(",", "")
    if not re.fullmatch(r"[0-9]{1,40}(?:\.[0-9]{1,30})?", value):
        raise ValueError("SUMMARY_DECIMAL_SCHEMA_CHANGED")
    return value


def position_values(node, label):
    """The source's nested balance table keeps L/S/P as separate rows."""
    values = []
    for tr in node.walk("tr"):
        cells = tr.cells()
        if len(cells) != 2:
            raise ValueError("SUMMARY_BALANCE_SCHEMA_CHANGED")
        m = re.fullmatch(r"([0-9,]+(?:\.[0-9]+)?)\(([LSP])\)", text(cells[0]))
        if not m:
            raise ValueError("SUMMARY_POSITION_SCHEMA_CHANGED")
        percent = text(cells[1])
        values.append(
            {
                "phase": label,
                "position": POSITIONS[m[2]],
                "shares": decimal(m[1]),
                "percentage": decimal(percent) if percent else None,
            }
        )
    if not values and text(node):
        raise ValueError("SUMMARY_UNTYPED_BALANCE")
    return values


def parse_report(body, day, category):
    root = Document(body).root
    content = text(root)
    source_date = re.search(r"Date\s*:\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", content)
    if not source_date or datetime.strptime(source_date[1], "%d/%m/%Y").date() != day:
        raise ValueError("SUMMARY_PUBLICATION_DATE_MISMATCH")
    result, seen, expected, header_found = [], set(), set(), False
    for tr in root.walk("tr"):
        cells = tr.cells()
        if not cells:
            continue
        if text(cells[0]) == "Serial No":
            labels = [text(c) for c in cells]
            header_found = len(cells) == (12 if category == 4 else 13) and labels[
                :3
            ] == ["Serial No", "Name of listed corporation", "Stock code"]
        links = [
            a
            for a in cells[0].children
            if isinstance(a, Node)
            and a.tag == "a"
            and "/di/NSForm" in a.attrs.get("href", "")
        ]
        if not links:
            if len(cells) >= 3 and re.fullmatch(r"[0-9]{5}", text(cells[2])):
                raise ValueError("SUMMARY_UNRECOGNIZED_RECORD")
            continue
        if len(cells) != (12 if category == 4 else 11):
            raise ValueError("SUMMARY_COLUMNS_CHANGED")
        serial = text(links[0])
        if not SERIAL.fullmatch(serial):
            raise ValueError("SUMMARY_SERIAL_SCHEMA_CHANGED")
        expected.add(serial)
        u = urlsplit(links[0].attrs.get("href", ""))
        form = re.fullmatch(r"/di/NSForm(1|2|3A|3B|3C|3D)\.aspx", u.path)
        q = parse_qs(u.query, strict_parsing=True)
        if (
            (u.netloc and u.netloc != "di.hkex.com.hk")
            or not form
            or q.get("fn") != [serial]
            or len(q.get("sid", [])) != 1
            or not re.fullmatch(r"[0-9]{1,12}", q["sid"][0])
        ):
            raise ValueError("SUMMARY_FILING_IDENTITY_CHANGED")
        form = form[1]
        if form not in (
            {"1", "2"}
            if category == 1
            else {"3A"} if category == 2 else {"3B"} if category == 3 else {"3C", "3D"}
        ):
            raise ValueError("SUMMARY_FORM_CATEGORY_MISMATCH")
        code, event = text(cells[2]), text(cells[5])
        if not re.fullmatch(r"[0-9]{5}", code) or q.get("sc") != [code]:
            raise ValueError("SUMMARY_STOCK_IDENTITY_CHANGED")
        event_date = (
            datetime.strptime(event, "%d/%m/%Y").date().isoformat() if event else None
        )
        remarks = text(cells[0]).removeprefix(serial).strip()
        revised, superseded = re.search(
            r"Amendment to\s*(" + SERIAL.pattern + ")", remarks, re.I
        ), re.search(r"Superseded by\s*(" + SERIAL.pattern + ")", remarks, re.I)
        withdrawn = re.search(
            r"Withdrawn on\s*([0-9]{2}/[0-9]{2}/[0-9]{4})", remarks, re.I
        )
        values = [text(c) for c in cells]
        key = digest(
            {
                "serial": serial,
                "stockCode": code,
                "class": values[3],
                "party": values[4],
                "values": values,
            }
        )[:20]
        if key in seen:
            raise ValueError("SUMMARY_DUPLICATE_SOURCE_ROW")
        seen.add(key)
        result.append(
            {
                "id": f"hkex:daily:{day.isoformat()}:{category}:{key}",
                "filing_id": "hkex:di:" + serial,
                "serial": serial,
                "form": form,
                "issuer_id": "hkex:issuer:" + q["sid"][0],
                "issuer_name": values[1],
                "stock_code": code,
                "share_class": values[3] if category in (1, 2) else None,
                "associated_corporation": values[3] if category in (3, 4) else None,
                "instrument": (
                    "debenture"
                    if category == 4
                    else "associated_shares" if category == 3 else "issuer_shares"
                ),
                "currency_as_disclosed": values[7] if category == 4 else None,
                "discloser": values[4],
                "event_date": event_date,
                "summary_date": day.isoformat(),
                "filed_date": None,
                "published_timestamp": None,
                "category": category,
                "reason_as_disclosed": values[6],
                "shares_involved_as_disclosed": values[8 if category == 4 else 7],
                "average_price_as_disclosed": values[9 if category == 4 else 8] or None,
                "interests": position_values(
                    cells[10 if category == 4 else 9], "before"
                )
                + position_values(cells[11 if category == 4 else 10], "after"),
                "revision": {
                    "remarks": remarks or None,
                    "amends": revised[1] if revised else None,
                    "superseded_by": superseded[1] if superseded else None,
                    "withdrawn_date": (
                        datetime.strptime(withdrawn[1], "%d/%m/%Y").date().isoformat()
                        if withdrawn
                        else None
                    ),
                },
                "source": "hkex_daily_summary",
                "source_url": BASE + report_path(day, category),
                "detail_scope": "published_daily_summary_only",
            }
        )
        if len(result) > 5000:
            raise ValueError("SUMMARY_RECORD_LIMIT")
    # No source row may disappear just because its changed markup stopped parsing.
    if expected != {r["serial"] for r in result}:
        raise ValueError("SUMMARY_SERIAL_RECONCILIATION_FAILED")
    if not result and not header_found:
        raise ValueError("SUMMARY_EMPTY_NOT_ESTABLISHED")
    return {
        "day": day.isoformat(),
        "category": category,
        "sourceSha256": hashlib.sha256(body).hexdigest(),
        "sourceBytes": len(body),
        "rows": result,
        "count": len(result),
    }
