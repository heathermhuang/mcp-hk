"""Deterministic, source-backed HTML for readers and crawlers alike."""

import json
from functools import lru_cache
from html import escape
from html.parser import HTMLParser
from pathlib import Path

ORIGIN = "https://mcp.hk"
WEB = Path(__file__).parent / "web"
VOID = set(
    "area base br col embed hr img input link meta param source track wbr".split()
)
SCREENS = {
    "/": "home",
    "/demo": "explore",
    "/connect": "connect",
    "/sources": "sources",
    "/plates": "plates",
}
INDEX = "index, follow, max-image-preview:large"


class Element:
    def __init__(self, tag, attrs=(), children=None):
        self.tag, self.attrs, self.children = tag, dict(attrs), children or []

    def html(self):
        attrs = "".join(
            " "
            + key
            + ("" if value is None else '="' + escape(value, quote=True) + '"')
            for key, value in self.attrs.items()
        )
        if self.tag in VOID:
            return f"<{self.tag}{attrs}>"
        children = "".join(
            (
                child.html()
                if isinstance(child, Element)
                else child if self.tag in {"script", "style"} else escape(child)
            )
            for child in self.children
        )
        return f"<{self.tag}{attrs}>{children}</{self.tag}>"


class Document(HTMLParser):
    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = Element("document")
        self.stack = [self.root]
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = Element(tag, attrs)
        self.stack[-1].children.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                self.stack = self.stack[:index]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)

    def elements(self, node=None):
        for child in (node or self.root).children:
            if isinstance(child, Element):
                yield child
                yield from self.elements(child)

    def html(self):
        return "<!doctype html>" + "".join(
            child.html() for child in self.root.children if isinstance(child, Element)
        )


@lru_cache(maxsize=1)
def content():
    return json.loads((WEB / "discovery.json").read_text())


@lru_cache(maxsize=1)
def translations():
    # translations.js deliberately contains a JSON object, also consumed by browsers.
    source = (WEB / "translations.js").read_text()
    return json.loads(
        source.split("const translations =", 1)[1].strip().removesuffix(";")
    )


def locale(value):
    return "zh-Hant" if (value or "").lower() in {"zh", "zh-hant", "zh-hk"} else "en"


def canonical(path, lang="en"):
    return ORIGIN + path + ("?lang=zh-Hant" if lang == "zh-Hant" else "")


def asset_path(path, lang="en"):
    name = "home" if path == "/" else path.strip("/").replace("/", "--")
    return f"/discovery/{lang}/{name}.html"


def public_paths():
    return list(content()["pages"])


def text_response(path):
    if path == "/robots.txt":
        return (
            "User-agent: *\nContent-Signal: search=yes, ai-input=yes, ai-train=no\nDisallow: /__ops/\n"
            "Disallow: /api/\nDisallow: /mcp\nDisallow: /healthz\nDisallow: /readyz\n"
            "Disallow: /assets/discovery/\nDisallow: /agent/\nDisallow: /oauth2/\nDisallow: /*?*q=\n"
            f"\nSitemap: {ORIGIN}/sitemap.xml\nAgentmap: {ORIGIN}/.well-known/ai-catalog.json\n",
            "text/plain",
        )
    if path == "/sitemap.xml":
        urls = []
        for page, data in content()["pages"].items():
            if data.get("noindex"):
                continue
            for lang in ("en", "zh-Hant"):
                alternatives = "".join(
                    f'<xhtml:link rel="alternate" hreflang="{code}" '
                    f'href="{escape(canonical(page, variant), quote=True)}"/>'
                    for code, variant in [
                        ("en", "en"),
                        ("zh-Hant", "zh-Hant"),
                        ("x-default", "en"),
                    ]
                )
                urls.append(
                    f"<url><loc>{escape(canonical(page, lang))}</loc>{alternatives}</url>"
                )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
            'xmlns:xhtml="http://www.w3.org/1999/xhtml">' + "".join(urls) + "</urlset>",
            "application/xml",
        )
    if path == "/llms.txt":
        pages = content()["pages"]
        links = "\n".join(
            f"- [{data['en']['title']}]({canonical(page)}): {data['en']['description']}"
            for page, data in pages.items()
            if not data.get("noindex")
        )
        return (
            "# mcp.hk\n\n> Independent, open-source Hong Kong public data over MCP and HTTP.\n\n"
            "## Documentation\n" + links + "\n\n## Interfaces\n"
            "- MCP: https://mcp.hk/mcp (Streamable HTTP; public read-only access; no API key)\n"
            "- OpenAPI: https://mcp.hk/openapi.json\n"
            "- Source code: https://github.com/heathermhuang/mcp-hk\n\n"
            "- Expanded documentation: https://mcp.hk/llms-full.txt\n"
            "- Public access instructions: https://mcp.hk/auth.md\n"
            "- API catalog: https://mcp.hk/.well-known/api-catalog\n"
            "- MCP server card: https://mcp.hk/.well-known/mcp/server-card.json\n\n"
            "## Citation and limits\n"
            "Cite original provider URLs and attribution from response provenance. Check source "
            "status, retrieval/check timestamps, reference period, warnings and stale flags. "
            "Catalogue inclusion does not mean every resource is queryable. A successful fetch "
            "does not establish semantic accuracy or observation freshness. Plate.hk auction "
            "history is not a valuation or availability check. SeeHouse asking prices are not "
            "completed transactions. mcp.hk is independent of the Hong Kong Government. "
            "Data reuse remains subject to each provider's terms; MIT covers software only.\n\n"
            "This file is a navigation aid, not a guarantee of indexing or AI citations.\n",
            "text/plain",
        )
    return None


def editorial_body(path, lang):
    page = content()["pages"][path][lang]
    parts = [
        f"<h1>{escape(page['heading'])}</h1><p class=\"mhk-pagelead\">{escape(page['description'])}</p>"
    ]
    for section in page.get("sections", []):
        parts.append(f"<section><h2>{escape(section['heading'])}</h2>")
        parts.extend(
            f"<p>{escape(paragraph)}</p>" for paragraph in section.get("paragraphs", [])
        )
        if section.get("code"):
            parts.append(f"<pre class=\"mhk-codebox\">{escape(section['code'])}</pre>")
        for label, href in section.get("links", []):
            parts.append(
                f'<p><a href="{escape(href, quote=True)}">{escape(label)}</a></p>'
            )
        parts.append("</section>")
    if path == "/guides":
        parts.append("<ul>")
        for target, item in content()["pages"].items():
            if target.startswith("/guides/"):
                parts.append(
                    f'<li><a href="{target}">{escape(item[lang]["heading"])}</a></li>'
                )
        parts.append("</ul>")
    return "".join(parts)


def schema(path, lang):
    page = content()["pages"][path]
    copy = page[lang]
    url = canonical(path, lang)
    graph = [
        {
            "@type": "Organization",
            "@id": ORIGIN + "/#organization",
            "name": "mcp.hk",
            "url": ORIGIN,
            "logo": ORIGIN + "/assets/logo.svg",
            "sameAs": ["https://github.com/heathermhuang/mcp-hk"],
        },
        {
            "@type": "WebSite",
            "@id": ORIGIN + "/#website",
            "name": "mcp.hk",
            "url": ORIGIN,
            "inLanguage": ["en", "zh-Hant"],
            "publisher": {"@id": ORIGIN + "/#organization"},
        },
        {
            "@type": "TechArticle" if path.startswith("/guides/") else "WebPage",
            "@id": url + "#page",
            "url": url,
            "name": copy["title"],
            "headline": copy["title"],
            "description": copy["description"],
            "inLanguage": lang,
            "isPartOf": {"@id": ORIGIN + "/#website"},
            "publisher": {"@id": ORIGIN + "/#organization"},
        },
    ]
    if path == "/":
        graph.append(
            {
                "@type": "SoftwareApplication",
                "@id": ORIGIN + "/#service",
                "name": "mcp.hk",
                "url": ORIGIN,
                "applicationCategory": "DeveloperApplication",
                "operatingSystem": "Any",
                "description": copy["description"],
                "isAccessibleForFree": True,
            }
        )
        graph.append(
            {
                "@type": "FAQPage",
                "@id": url + "#questions",
                "inLanguage": lang,
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": q,
                        "acceptedAnswer": {"@type": "Answer", "text": a},
                    }
                    for q, a in content()["faq"][lang]
                ],
            }
        )
    else:
        crumbs = [(content()["homeLabel"][lang], canonical("/", lang))]
        if path.startswith("/guides/"):
            crumbs.append(
                (
                    content()["pages"]["/guides"][lang]["heading"],
                    canonical("/guides", lang),
                )
            )
        crumbs.append((copy.get("heading", copy["title"]), url))
        graph.append(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": i, "name": name, "item": href}
                    for i, (name, href) in enumerate(crumbs, 1)
                ],
            }
        )
    return {"@context": "https://schema.org", "@graph": graph}


@lru_cache(maxsize=64)
def render_page(path, lang="en", filtered=False):
    lang = locale(lang)
    page = content()["pages"][path]
    copy = page[lang]
    template = page.get("template", "article.html")
    doc = Document((WEB / template).read_text())
    strings = translations()["zh" if lang == "zh-Hant" else "en"]
    nodes = list(doc.elements())
    html = next(n for n in nodes if n.tag == "html")
    html.attrs.update({"lang": lang, "data-discovery": "true"})
    if template == "article.html":
        main = next(n for n in nodes if n.attrs.get("id") == "article")
        main.children = Document(editorial_body(path, lang)).root.children
    for node in nodes:
        key = node.attrs.get("data-i18n") or node.attrs.get("data-i18n-html")
        if key and key in strings:
            node.children = (
                Document(strings[key]).root.children
                if "data-i18n-html" in node.attrs
                else [strings[key]]
            )
        for attr in ("placeholder", "aria-label", "content"):
            key = node.attrs.get("data-i18n-" + attr)
            if key in strings:
                node.attrs[attr] = strings[key]
        if "data-page" in node.attrs:
            if node.attrs["data-page"] == SCREENS.get(path):
                node.attrs.pop("hidden", None)
            else:
                node.attrs["hidden"] = None
        if node.tag == "title":
            node.children = [copy["title"]]
        if node.tag == "meta" and node.attrs.get("name") == "description":
            node.attrs["content"] = copy["description"]
            node.attrs.pop("data-i18n-content", None)
        if "data-language-value" in node.attrs:
            node.attrs["value"] = lang
        if node.attrs.get("data-dynamic") == "endpoint":
            node.children = [ORIGIN + "/mcp"]
        if node.attrs.get("id") == "mhk-install":
            node.children = [
                '[mcp_servers."mcp.hk"]\nurl = "https://mcp.hk/mcp"\nstartup_timeout_sec = 120'
            ]
        if "mhk-language" in node.attrs.get("class", "").split():
            node.children = ["EN" if lang == "zh-Hant" else "繁"]
            node.attrs["aria-label"] = (
                "Switch to English" if lang == "zh-Hant" else "切換至繁體中文"
            )
    if path == "/":
        home = next(n for n in nodes if n.attrs.get("data-page") == "home")
        questions = content()["faq"][lang]
        faq = Element("section", [("aria-label", content()["faqLabel"][lang])])
        faq.children = [Element("h2", children=[content()["faqLabel"][lang]])]
        for question, answer in questions:
            faq.children.append(Element("h3", children=[question]))
            faq.children.append(Element("p", children=[answer]))
        home.children.append(faq)
    # All pages link to the same stable, human-readable source and connection guides.
    footer = next(n for n in nodes if n.tag == "footer")
    footer.children.append(
        Element(
            "span",
            children=[
                Element("a", [("href", "/about")], [content()["aboutLabel"][lang]]),
                " · ",
                Element("a", [("href", "/guides")], [content()["guidesLabel"][lang]]),
                " · ",
                Element("a", [("href", "/llms.txt")], ["llms.txt"]),
            ],
        )
    )
    head = next(n for n in nodes if n.tag == "head")
    head.children.append(
        Element("script", [("src", "/assets/webmcp.js"), ("defer", None)])
    )
    head.children.append(
        Element(
            "link",
            [("rel", "api-catalog"), ("href", ORIGIN + "/.well-known/api-catalog")],
        )
    )
    head.children.append(
        Element(
            "link",
            [("rel", "ai-catalog"), ("href", ORIGIN + "/.well-known/ai-catalog.json")],
        )
    )
    if not page.get("noindex"):
        md_path = "/index.md" if path == "/" else path + ".md"
        head.children.append(
            Element(
                "link",
                [
                    ("rel", "alternate"),
                    ("type", "text/markdown"),
                    ("href", canonical(md_path, lang)),
                ],
            )
        )
    if not any(n.tag == "meta" and n.attrs.get("name") == "description" for n in nodes):
        head.children.append(
            Element("meta", [("name", "description"), ("content", copy["description"])])
        )
    robots = "noindex, follow" if filtered or page.get("noindex") else INDEX
    url = canonical(path, lang)
    head.children.append(Element("meta", [("name", "robots"), ("content", robots)]))
    head.children.append(Element("link", [("rel", "canonical"), ("href", url)]))
    for code, variant in [("en", "en"), ("zh-Hant", "zh-Hant"), ("x-default", "en")]:
        head.children.append(
            Element(
                "link",
                [
                    ("rel", "alternate"),
                    ("hreflang", code),
                    ("href", canonical(path, variant)),
                ],
            )
        )
    for key, value in {
        "og:type": "article" if path.startswith("/guides/") else "website",
        "og:site_name": "mcp.hk",
        "og:title": copy["title"],
        "og:description": copy["description"],
        "og:url": url,
        "og:locale": "zh_HK" if lang == "zh-Hant" else "en_HK",
        "og:image": ORIGIN + "/assets/social-card.png",
        "og:image:width": "1200",
        "og:image:height": "630",
        "og:image:alt": "mcp.hk — Hong Kong public data for apps and AI",
    }.items():
        head.children.append(Element("meta", [("property", key), ("content", value)]))
    head.children.append(
        Element("meta", [("name", "twitter:card"), ("content", "summary_large_image")])
    )
    payload = (
        json.dumps(schema(path, lang), ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    head.children.append(
        Element("script", [("type", "application/ld+json")], [payload])
    )
    # Stable locale links are usable without JavaScript; never carry a user's query.
    nav = next(n for n in doc.elements() if n.tag == "nav")
    nav.children.append(
        Element(
            "a",
            [
                ("href", canonical(path, "en" if lang == "zh-Hant" else "zh-Hant")),
                ("hreflang", "en" if lang == "zh-Hant" else "zh-Hant"),
            ],
            ["English" if lang == "zh-Hant" else "繁體中文"],
        )
    )
    for node in doc.elements():
        href = node.attrs.get("href", "")
        if (
            lang == "zh-Hant"
            and href.startswith("/")
            and href.split("?", 1)[0] in public_paths()
        ):
            node.attrs["href"] = href + ("&" if "?" in href else "?") + "lang=zh-Hant"
    return doc.html()
