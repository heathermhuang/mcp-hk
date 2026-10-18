"""Bounded public SEO/AEO/GEO check; no model calls, secrets or indexing claims.

Run with the project Python: python scripts/check_discovery.py --output receipt.json
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from mcp_open_data_hk.discovery import Document, canonical, content  # noqa: E402


def check(base, expected_release=None):
    receipt = {
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "baseUrl": base,
        "checks": [],
        "indexing": "not_measured",
        "aiCitations": "not_measured",
    }
    with httpx.Client(timeout=30, follow_redirects=False) as client:

        def read(path, agent="mcp.hk-discovery-check/1.0"):
            started = time.monotonic()
            response = client.get(base + path, headers={"User-Agent": agent})
            receipt["checks"].append(
                {
                    "path": path,
                    "userAgent": agent,
                    "status": response.status_code,
                    "release": response.headers.get("x-mcp-release"),
                    "milliseconds": round((time.monotonic() - started) * 1000),
                    "sha256": hashlib.sha256(response.content).hexdigest(),
                }
            )
            assert response.status_code == 200, f"{path}: HTTP {response.status_code}"
            if expected_release:
                assert (
                    response.headers.get("x-mcp-release") == expected_release
                ), f"{path}: release mismatch"
            return response

        robots = read("/robots.txt")
        parser = RobotFileParser()
        parser.parse(robots.text.splitlines())
        assert "https://mcp.hk/sitemap.xml" in (
            parser.site_maps() or []
        ), "Missing sitemap declaration"
        agents = [
            "Googlebot",
            "bingbot",
            "OAI-SearchBot",
            "PerplexityBot",
            "Claude-SearchBot",
        ]
        for agent in agents:
            assert parser.can_fetch(
                agent, "https://mcp.hk/"
            ), f"{agent}: home blocked by robots"
            assert parser.can_fetch(
                agent, "https://mcp.hk/guides/hong-kong-open-data-api"
            ), f"{agent}: guides blocked"
            read("/", agent)
        import xml.etree.ElementTree as ET

        sitemap = ET.fromstring(read("/sitemap.xml").text)
        entries = {n.text for n in sitemap.findall("{*}url/{*}loc")}
        expected = {
            canonical(p, lang)
            for p, data in content()["pages"].items()
            if not data.get("noindex")
            for lang in ("en", "zh-Hant")
        }
        assert entries == expected, "Sitemap URLs do not match the canonical page set"
        for url in sorted(entries):
            parsed = urlsplit(url)
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            response = read(path)
            nodes = list(Document(response.text).elements())
            canonicals = [
                n.attrs["href"] for n in nodes if n.attrs.get("rel") == "canonical"
            ]
            assert canonicals == [url], f"{path}: canonical mismatch"
            robots = [
                n.attrs["content"] for n in nodes if n.attrs.get("name") == "robots"
            ]
            assert len(robots) == 1 and robots[0].startswith(
                "index,"
            ), f"{path}: index directive mismatch"
            data = json.loads(
                next(
                    n.children[0]
                    for n in nodes
                    if n.attrs.get("type") == "application/ld+json"
                )
            )
            assert data["@context"] == "https://schema.org"
            assert "noindex" not in response.headers.get(
                "x-robots-tag", ""
            ), f"{path}: blocked by response header"
        filtered = read("/coverage?q=weather&lang=zh-Hant")
        assert filtered.headers.get("x-robots-tag") == "noindex, follow"
        assert "Citation and limits" in read("/llms.txt").text
        image = read("/assets/social-card.png")
        assert image.content.startswith(b"\x89PNG\r\n\x1a\n")
        assert read("/connect").text.find("https://mcp.hk/mcp") >= 0
    receipt.update({"technicalDiscovery": "pass", "canonicalUrls": len(entries)})
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://mcp.hk")
    parser.add_argument("--release")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = check(args.base_url.rstrip("/"), args.release)
    except (AssertionError, httpx.HTTPError, ValueError, StopIteration) as exc:
        raise SystemExit("Discovery check failed: " + str(exc)) from None
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "checks"}))
