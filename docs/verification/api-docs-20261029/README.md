# API docs redesign — 29 October 2026

The candidate replaces the disconnected docs introduction and default endpoint
list with the homepage’s shared shell, a first-request walkthrough, and a native
searchable reference. This is PR evidence, not a production deployment.

## What changed

- A copyable district-statistics request, JSON response link and explanation of
  `data.population`, `data.referencePeriod` and `provenance`. The exact command
  was checked against the existing public accepted snapshot: HTTP 200 with all
  documented fields. Page load/search does not execute data queries.
- Search by English/Traditional Chinese label, shared family keywords, method,
  path or API group. Groups and operations come from the actual runtime OpenAPI
  schema. The current bilingual labels cover all 53 configured production
  operations, while unknown future operations remain visible with original
  metadata. Local screenshots use the default configuration’s 48 operations.
- Readable parameter/request-body tables and response definitions remain schema-driven,
  with expandable local references and original OpenAPI definitions available.
- Bilingual HTML before JavaScript, persistent search/group/operation selection
  through language changes, canonical/noindex handling and a no-JavaScript guide.
- The original vendored Swagger console and old deep links remain available. Its
  original English technical interface is explicitly labelled; the new guide,
  search, operation labels, parameter controls and feedback are bilingual.
  Swagger JavaScript/CSS load only when the console is opened.

## Verification

- Repository checks: **711 Python tests passed; 122 existing optional/PostgreSQL
  skips**, formatting/lint, generated discovery, Worker types/TypeScript and
  **158 Worker tests passed**. Mandatory pre-push checks revalidate committed HEAD;
  hosted CI is reported separately on the PR.
- New browser suite: English/Traditional Chinese at **320, 390, 768 and 1280px**.
  Copy, bilingual subject/path/method search, groups, keyboard expansion, complex
  request bodies, locale/selection persistence, empty/reset states, lazy Swagger,
  schema/console retry, saved locale, old Swagger links and future-operation/XSS
  handling pass. No source-record API is called by page load, search or expansion.
- Existing **160-surface** content/navigation/layout matrix passes without errors.
- The default public OpenAPI document is **byte-identical** to the baseline,
  SHA256 `d38c98e6b30cab079f6f9072e14ad1d34623153a4b5008b58506fe4eb34ed27d`.
  Data/MCP handlers, source gates, source policies and deployment settings are
  unchanged. The only HTTP handler edit localizes the excluded `/docs` UI route.

## Screenshots

| View | English | Traditional Chinese |
|---|---|---|
| Desktop top | [Screenshot](desktop-en.png) | [Screenshot](desktop-zh-Hant.png) |
| Mobile top | [Screenshot](mobile-en.png) | [Screenshot](mobile-zh-Hant.png) |
| Desktop reference | [Screenshot](reference-desktop-en.png) | [Screenshot](reference-desktop-zh-Hant.png) |
| Mobile reference | [Screenshot](reference-mobile-en.png) | [Screenshot](reference-mobile-zh-Hant.png) |

[Browser receipt](browser.json), [OpenAPI preservation](openapi-preservation.json)
and [first-request proof](first-request-proof.json) provide bounded evidence.
No source activation, qualification, licensing or new ingestion claim is added.
