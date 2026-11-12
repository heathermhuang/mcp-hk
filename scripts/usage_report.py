"""Private usage report. Standard library only; never embeds the ops credential."""

import argparse
import html
import json
from pathlib import Path
import urllib.error
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Operator redirects disabled")


def render(report):
    def escape(value):
        return html.escape(str(value))

    def table(title, rows, columns):
        heading = "".join("<th>" + escape(c) + "</th>" for c in columns)
        values = "".join(
            "<tr>"
            + "".join("<td>" + escape(row.get(c, "")) + "</td>" for c in columns)
            + "</tr>"
            for row in rows
        )
        return (
            "<h2>"
            + escape(title)
            + "</h2><table><thead><tr>"
            + heading
            + "</tr></thead><tbody>"
            + values
            + "</tbody></table>"
        )

    totals = report.get("totals", {})
    content = "<h1>mcp.hk usage</h1><p>" + escape(report.get("asOf", "")) + "</p>"
    content += (
        "<p>Private operator report. Network clients are estimates, not people.</p>"
    )
    content += table("Recorded totals", [totals], list(totals))
    content += table(
        "Daily network estimates",
        report.get("audience", []),
        ["day", "clients", "unresolved", "capped"],
    )
    content += table(
        "Demand and outcomes",
        report.get("dimensions", []),
        ["kind", "value", "requests", "errors", "empty"],
    )
    content += table(
        "Approximate keyword demand",
        report.get("keywords", []),
        ["term", "lower_bound", "upper_bound", "empty_observed"],
    )
    content += table(
        "Recent query outcomes (bounded detail)",
        [
            {
                "time": row.get("at"),
                "operation": row.get("op", {}).get("operation"),
                "dataset": row.get("op", {}).get("dataset"),
                "client": row.get("facts", {}).get("client"),
                "keyword": row.get("facts", {}).get("keyword"),
                "returned": row.get("items"),
                "outcome": row.get("result", {}).get("category"),
                "version": row.get("result", {}).get("version"),
                "duration_ms": row.get("duration"),
            }
            for row in report.get("recent", [])
        ],
        [
            "time",
            "operation",
            "dataset",
            "client",
            "keyword",
            "returned",
            "outcome",
            "version",
            "duration_ms",
        ],
    )
    for title, value in [
        ("Coverage and definitions", report.get("definitions", {})),
        ("Completed-week comparisons", report.get("comparison", {})),
        ("Collection health", report.get("health", {})),
        ("Observed latency", report.get("latency", {})),
        ("Archive status", report.get("archives", [])),
        ("Ingress health", report.get("ingress", {})),
        ("Daily digests", report.get("digests", [])),
    ]:
        content += (
            "<h2>"
            + escape(title)
            + "</h2><pre>"
            + escape(json.dumps(value, ensure_ascii=False, indent=2))
            + "</pre>"
        )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        "style-src 'unsafe-inline'; base-uri 'none'\">"
        "<title>mcp.hk private usage report</title><style>"
        "body{font:16px/1.5 system-ui;max-width:1100px;margin:2rem auto;padding:1rem;"
        "color:#17392f;background:#f8fbf9}table{border-collapse:collapse;width:100%;"
        "display:block;overflow:auto}th,td{padding:.5rem;text-align:left;"
        "border-bottom:1px solid #cbd8d1}pre{white-space:pre-wrap;overflow-wrap:anywhere}"
        "h2{margin-top:2rem}</style><body>" + content + "</body></html>"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, choices=range(1, 91), default=7)
    parser.add_argument("--output", type=Path, help="Private standalone HTML report")
    parser.add_argument("--input", type=Path, help="Render a saved private JSON report")
    parser.add_argument(
        "--secrets", type=Path, default=Path("deploy/cloudflare/.ops-secrets.json")
    )
    args = parser.parse_args()
    if args.input:
        report = json.loads(args.input.read_text())
    else:
        token = json.loads(args.secrets.read_text())["OPS_TOKEN"]
        request = urllib.request.Request(
            "https://mcp.hk/__ops/analytics?days=" + str(args.days),
            headers={
                "Authorization": "Bearer " + token,
                "User-Agent": "mcp.hk-operations/usage-report",
            },
        )
        try:
            with urllib.request.build_opener(NoRedirect).open(
                request, timeout=30
            ) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise SystemExit("Operator report exceeded its size limit")
                report = json.loads(raw)
        except urllib.error.HTTPError as error:
            raise SystemExit(
                "Operator report returned HTTP " + str(error.code)
            ) from None
        except urllib.error.URLError:
            raise SystemExit("Operator report could not be reached") from None
    if args.output:
        # The artifact can contain search demand. Do not publish or sync it.
        args.output.touch(mode=0o600, exist_ok=True)
        args.output.chmod(0o600)
        args.output.write_text(render(report))
        print("Saved private report:", args.output)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
