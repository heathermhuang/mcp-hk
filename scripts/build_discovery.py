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
agent_spec = importlib.util.spec_from_file_location(
    "agent_discovery", root / "src/mcp_open_data_hk/agent_discovery.py"
)
agents = importlib.util.module_from_spec(agent_spec)
agent_spec.loader.exec_module(agents)
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
        if not discovery.content()["pages"][path].get("noindex"):
            md_asset = asset.replace(".html", ".md")
            (web / md_asset.lstrip("/")).write_text(
                agents.markdown_document(discovery, path, lang)
            )
            routes[path][lang + "-markdown"] = md_asset
        if path in {"/coverage", "/companies", "/hkex", "/sfc"}:
            filtered = asset.replace(".html", "-filtered.html")
            (web / filtered.lstrip("/")).write_text(
                discovery.render_page(path, lang, filtered=True)
            )
            routes[path][lang + "-filtered"] = filtered
            filtered_md = filtered.replace(".html", ".md")
            (web / filtered_md.lstrip("/")).write_text(
                agents.markdown_document(discovery, path, lang, filtered=True)
            )
            routes[path][lang + "-filtered-markdown"] = filtered_md
for path in ("/robots.txt", "/sitemap.xml", "/llms.txt"):
    body, _ = discovery.text_response(path)
    (web / path.lstrip("/")).write_text(body)
(root / "deploy/cloudflare/discovery-routes.json").write_text(
    json.dumps(routes, indent=2) + "\n"
)
agent_routes = {}
for index, (path, (body, media_type)) in enumerate(
    agents.agent_documents(discovery).items()
):
    suffix = (
        ".json"
        if "json" in media_type
        else ".md" if media_type == "text/markdown" else ".txt"
    )
    asset = f"/discovery/agents/document-{index}{suffix}"
    target = web / asset.lstrip("/")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body)
    agent_routes[path] = {"asset": asset, "contentType": media_type}
(root / "deploy/cloudflare/agent-routes.json").write_text(
    json.dumps(agent_routes, indent=2) + "\n"
)
print(f"Built {len(routes) * 2} localized pages and discovery files")
