# Search and AI discovery

mcp.hk publishes the same initial HTML to people, search crawlers and AI retrieval
clients. English and Traditional Chinese pages have distinct titles, descriptions,
canonical URLs, reciprocal language links and matching visible content. No
user-agent-specific content or ranking claims are generated.

## Content and discovery contract

`web/discovery.json` is the editorial source for page metadata, guides and visible
questions/answers. `discovery.py` renders those alongside existing translated UI
templates. The self-hosted FastAPI service uses that renderer directly. The edge
build uses the same renderer; no backend/container request is needed for public
HTML, `robots.txt`, `sitemap.xml`, `llms.txt` or social preview assets.

There are 24 canonical indexable URLs (12 pages in two languages). English uses
the path without a locale query; Chinese uses `?lang=zh-Hant`. Explicit `?lang=en`
canonicalizes to English. Tracking and arbitrary query values are never copied
into canonical metadata or JSON-LD. Filtered catalogue pages use `noindex, follow`;
terms/privacy pages remain reachable but are omitted from the sitemap. `/data`
redirects permanently to `/coverage`, preserving working query parameters.

Visible homepage answers are also represented in FAQPage JSON-LD. WebSite,
Organization, WebPage/TechArticle, SoftwareApplication and BreadcrumbList describe
actual content. There are no invented ratings, endorsements, dataset completeness
claims or publication dates. FAQ markup does not promise a Google rich result.

Guides explain dataset discovery, MCP connections, original-source citation and
freshness. Government publishers, DATA.GOV.HK, CSDI, Plate.hk and SeeHouse retain
their own identity and terms. Catalogue inclusion, source readability, semantic
qualification and observation age remain separate. Never manufacture landing
pages or schema for unavailable records.

`llms.txt` is a supplementary navigation aid. It does not replace crawlable HTML,
a sitemap, source provenance or provider terms. Google states that no special AI
text file or schema is required for its AI search features:
https://developers.google.com/search/docs/appearance/ai-features

## Build, checks and deployment

```sh
python3 scripts/build_discovery.py
bash scripts/check.sh all
PYTHONPATH=src .venv/bin/python scripts/check_discovery.py \
  --base-url https://mcp.hk --release VERIFIED_COMMIT --output receipt.json
```

`npm run types` builds discovery assets before generating Worker types, so the
shared CI/pre-push check covers the build. `npm run deploy` builds them before
deploying. When invoking Wrangler directly, run the build first. The build is
stdlib-only and creates ignored assets; no generated HTML belongs in commits.
The Python distribution includes the original templates, translations, editorial
JSON and social card needed by self-hosting. The Worker routes only a fixed page
allowlist into those generated assets. Direct HTML/JSON asset URLs are noindex.

Follow `production.md` for the resource-cron pause, propagation window, maintenance
lease, deployment, controller/container adoption, HTTP/MCP regressions and isolated
restore. A discovery release does not alter source review policy or analytics
consent. Retain failed/uncertain receipts and the prior accepted checkpoint.

The smoke script makes one bounded public pass without models or retries. It
checks the exact release, actual production robots policy (including CDN additions),
five search/answer crawler user agents, sitemap pages, canonical metadata, JSON-LD,
filtered-page noindex, text navigation and social image. A spoofed user agent proves
only HTTP delivery for that request, not actual bot indexing or an IP-based bot rule.

## Owner indexing and measurement

1. Verify the correct mcp.hk property/account in Google Search Console. Submit
   `https://mcp.hk/sitemap.xml` only after the smoke receipt passes. Reopen the
   sitemap report and retain its submitted/fetched result. Request indexing for the
   homepage, Connect and the API guide; a request is not evidence of indexing.
2. Use an existing Bing Webmaster Tools property if accessible, or verify the
   correct owner before submission. Do not create new accounts or publish owner
   tokens in repository documentation. Search-engine verification is separate from
   a green HTTP/crawler check.
3. Record indexed canonical URLs and exclusion reasons from the owner tools.
   Compare impressions, clicks, CTR, query and landing-page trends after data has
   accumulated. Use equal date windows; a new property initially has no baseline.
4. Record independent ChatGPT, Claude, Gemini and Perplexity search/answer results
   for branded and unbranded questions below. Retain the exact question, product,
   date, browsing mode, answer and actual citation URL. Classify mention-only,
   cited, not cited, or unavailable. Do not use prompts that tell the model to cite
   mcp.hk as evidence of organic citation uptake.

Suggested bilingual question panel:

| Intent | English | 繁體中文 |
| --- | --- | --- |
| Branded | What is mcp.hk and how do I connect? | mcp.hk 是甚麼？如何連接？ |
| API | Which APIs can I use to access Hong Kong open data? | 有哪些 API 可以讀取香港開放數據？ |
| AI connection | How can an AI assistant query Hong Kong public data with MCP? | 如何透過 MCP 讓 AI 查詢香港公共數據？ |
| Provenance | How do I cite Hong Kong public data and check its freshness? | 如何引用香港公共數據及確認數據時效？ |
| Examples | Where can I find Hong Kong restaurant licence and plate auction data? | 哪裏可查詢香港食肆牌照及車牌拍賣數據？ |

Existing analytics is consent-based and intentionally strips queries, fragments
and referrers. Do not weaken those choices to infer AI referrals. Search Console
performance, aggregate consented page views, operational API/MCP counters and
independently observed AI citations are different evidence. Technical readiness
is complete only when public checks pass; search indexing and AI citation uptake
must keep their own pending/observed status.

Relevant crawler documentation:
https://developers.openai.com/api/docs/bots
https://docs.perplexity.ai/docs/resources/perplexity-crawlers
