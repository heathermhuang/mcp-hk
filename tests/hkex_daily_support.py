"""Synthetic report-layout fixtures; no provider payload is checked into Git."""

from datetime import date

DAY = date(2026, 10, 23)
SERIALS = {
    1: "CS20261023E00001",
    2: "DA20261023E00002",
    3: "DB20261023E00003",
    4: "DC20261023E00004",
}


def menu(day=DAY):
    return (
        "<html><body>"
        + "".join(
            f'<a href="DSM{day:%Y%m%d}C{k}.htm">Category {k}</a>' for k in (1, 2, 3, 4)
        )
        + "</body></html>"
    ).encode()


def report(category=1, day=DAY, empty=False, amendment=False):
    form = {1: "2", 2: "3A", 3: "3B", 4: "3C"}[category]
    serial = SERIALS[category]
    link = f"/di/NSForm{form}.aspx?fn={serial}&amp;sid=100&amp;sc=00005"
    headings = ["Serial No", "Name of listed corporation", "Stock code"] + [
        "Synthetic header"
    ] * (9 if category == 4 else 10)
    heading = "<tr>" + "".join(f"<td>{x}</td>" for x in headings) + "</tr>"
    balance = "<table><tr><td>9,007,199,254,740,993.00000001(L)</td><td>5.01</td></tr><tr><td>0(S)</td><td>0.00</td></tr></table>"
    mark = (
        ' (Amendment to <a href="/di/NSForm3A.aspx?fn=DA20261022E00001">DA20261022E00001</a>)'
        if amendment
        else ""
    )
    cells = [
        f'<a href="{link}">{serial}</a>' + mark,
        "Synthetic issuer &amp; partner",
        "00005",
        "Ordinary shares" if category < 3 else "Synthetic associated corporation",
        "Synthetic discloser",
        f"{day:%d/%m/%Y}",
        "1101(L)",
        "1,000(L)",
        "HKD 1.2000",
        balance,
        balance,
    ]
    if category == 4:
        cells.insert(7, "USD")
    row = "" if empty else "<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>"
    return f"<html><body>Date: {day:%d/%m/%Y}<table>{heading}{row}</table></body></html>".encode()
