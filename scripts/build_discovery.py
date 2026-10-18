"""Build the exact self-hosted HTML into static edge assets (stdlib only)."""

import importlib.util
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "discovery", root / "src/mcp_open_data_hk/discovery.py"
)
discovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(discovery)
web = discovery.WEB
routes = {}
for path in discovery.public_paths():
    routes[path] = {}
    for lang in ("en", "zh-Hant"):
        asset = discovery.asset_path(path, lang)
        target = web / asset.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(discovery.render_page(path, lang))
        routes[path][lang] = asset
        if path == "/coverage":
            filtered = asset.replace(".html", "-filtered.html")
            (web / filtered.lstrip("/")).write_text(
                discovery.render_page(path, lang, filtered=True)
            )
            routes[path][lang + "-filtered"] = filtered
for path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
    body, _ = discovery.text_response(path)
    (web / path.lstrip("/")).write_text(body)
(root / "deploy/cloudflare/discovery-routes.json").write_text(
    json.dumps(routes, indent=2) + "\n"
)
print(f"Built {len(routes) * 2} localized pages and discovery files")
