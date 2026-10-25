"""Strict bilingual synthetic HTML contract parser, not a qualified HKJC collector.

Provider layouts and field dictionaries require retained, permitted real captures
before activation. Invented fixtures exercise table order and Unicode handling.
"""

from html.parser import HTMLParser

from .normalize import result_row
from .policy import RacingRejected

HEADERS = {
    "Horse ID": "horseId",
    "馬匹編號": "horseId",
    "Horse number": "horseNumber",
    "馬號": "horseNumber",
    "Draw": "draw",
    "檔位": "draw",
    "Placing": "placing",
    "名次": "placing",
    "Time": "time",
    "完成時間": "time",
    "Weight (lb)": "weightLb",
    "負磅（磅）": "weightLb",
    "Claim (lb)": "claimLb",
    "減磅（磅）": "claimLb",
    "Margin": "marginRaw",
    "勝負距離": "marginRaw",
}


class ContractTable(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.rows, self.current, self.cell, self.depth, self.done = (
            [],
            None,
            None,
            0,
            False,
        )
        self.feed(text)
        self.close()
        if self.depth or self.cell is not None or self.current is not None:
            raise RacingRejected("RESULT_LAYOUT_DRIFT")

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth > 1 or self.done:
                raise RacingRejected("RESULT_LAYOUT_DRIFT")
        elif tag == "tr" and self.depth:
            if self.current is not None:
                raise RacingRejected("RESULT_LAYOUT_DRIFT")
            self.current = []
        elif tag in {"td", "th"} and self.depth:
            if self.cell is not None or self.current is None:
                raise RacingRejected("RESULT_LAYOUT_DRIFT")
            self.cell = []

    def handle_endtag(self, tag):
        if tag in {"td", "th"} and self.cell is not None:
            self.current.append("".join(self.cell).strip())
            self.cell = None
        elif tag == "tr" and self.current is not None:
            self.rows.append(self.current)
            self.current = None
        elif tag == "table":
            self.depth -= 1
            self.done = True

    def handle_data(self, value):
        if self.cell is not None:
            self.cell.append(value)


def parse_contract_html(text, race_id):
    if not isinstance(text, str) or len(text.encode()) > 400 * 1024:
        raise RacingRejected("RESULT_BODY_LIMIT")
    table = ContractTable(text)
    if len(table.rows) < 2 or len(table.rows) > 31 or not table.done:
        raise RacingRejected("RESULT_LAYOUT_DRIFT")
    headers = table.rows[0]
    if (
        len(headers) != 8
        or len(set(headers)) != 8
        or any(header not in HEADERS for header in headers)
    ):
        raise RacingRejected("RESULT_LAYOUT_DRIFT")
    keys = [HEADERS[header] for header in headers]
    if len(set(keys)) != 8:
        raise RacingRejected("RESULT_LAYOUT_DRIFT")
    results = []
    for values in table.rows[1:]:
        if len(values) != len(keys):
            raise RacingRejected("RESULT_LAYOUT_DRIFT")
        row = dict(zip(keys, values))
        for key in ("time", "draw", "weightLb", "claimLb", "marginRaw"):
            if row[key] in {"", "--"}:
                row[key] = None
        results.append(result_row(row, race_id))
    if len({row["participantId"] for row in results}) != len(results):
        raise RacingRejected("DUPLICATE_RUNNER")
    return results
