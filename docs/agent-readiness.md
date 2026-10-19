# Agent discovery and content delivery

mcp.hk is a public, read-only MCP/HTTP data service. Discovery documents describe
interfaces that actually work. OAuth, A2A, personal-agent identity and payment
protocols are not offered and must not be fabricated for a scanner score.

| Path | Contract |
| --- | --- |
| `/.well-known/mcp/server-card.json` | MCP Server Card draft shape; actual Streamable HTTP endpoint, protocol version, server identity and tools capability |
| `/.well-known/api-catalog` | RFC 9727 `application/linkset+json` with HTTP/OpenAPI and MCP description/documentation links |
| `/.well-known/agent-skills/index.json` | Agent Skills Discovery 0.2.0 index with a real SKILL.md and SHA-256 digest |
| `/.well-known/ai-catalog.json` | ARD draft catalogue for implemented MCP/HTTP services; stable identifiers and representative queries |
| `/auth.md` | Anonymous public access instructions; no public registration, token or OAuth endpoint |
| `/llms.txt`, `/llms-full.txt` | Compact navigation and expanded first-party documentation, not a copy of third-party source records |

The MCP card is a draft interoperability document, not a claim that SEP-1649/2127
is a stable MCP specification. Its name/version/tools capability are tested against
MCP initialization. Update it when the implementation version changes. Provider
terms and source freshness/semantic qualifications still apply.

Documents are generated as edge assets without starting the container. Self-hosting
uses the same generator. Discovery responses expose CORS and registered Link
relations (`api-catalog`, `service-desc`, `service-doc`, `describedby`). Private
operator routes remain private.

## Markdown

The 12 indexable public pages support `Accept: text/markdown`, plus explicit
`/index.md`, `/connect.md`, `/guides/hong-kong-open-data-api.md` and corresponding
page aliases. `?lang=zh-Hant` selects Chinese. HTML remains the default; quality
values and explicit `q=0` are honored. Both representations include `Vary: Accept`;
edge representations use distinct asset paths/ETags.

Markdown comes from the same rendered main content, excluding hidden app screens,
controls, scripts and dynamic loading placeholders. Explicit aliases are noindex.
Canonical HTML URLs and the 24-URL sitemap are unchanged. Terms/privacy retain
their existing HTML interfaces. Expanded LLM content contains documentation, not
cached provider records or credentials.

## Browser tools

`webmcp.js` feature-detects `document.modelContext`, with the documented legacy
`navigator.modelContext` fallback, and registers two read-only tools:

- `search_hong_kong_datasets`: validated query/access mode and maximum ten results;
  calls only the existing first-party catalogue API.
- `get_hong_kong_data_packs`: no arguments; reads the existing pack directory.

Executors validate inputs even when a client ignores JSON Schema, omit cookies,
reject redirects, cap response size, and propagate failures instead of inventing
empty records. Existing quotas/provenance remain intact. Unsupported browsers keep
the normal site; no fake WebMCP polyfill is added.

## Content policy and DNS

`Content-Signal: search=yes, ai-input=yes, ai-train=no` declares search/grounding
preferences while reserving training use. It does not replace provider licences
or alter private-route access. `Agentmap` and an HTML `ai-catalog` link point at
the actual ARD catalogue.

DNS-AID is an emerging draft. Advertise only the existing MCP service: HTTPS/SVCB
`_mcp._agents.mcp.hk`, ServiceMode priority 1, target `mcp.hk`, actual TLS ALPN
`h2`/`http/1.1`, port 443. Optional experimental `key65400` can point to the MCP
server card, following the DNS-AID reference implementation's private-use mapping.
Do not advertise nonexistent A2A endpoints or claim DNSSEC authentication unless
the resolver reports it. Preserve Worker records and Google's ownership TXT.
Registrar/DNSSEC migration is outside this change.

## Verification

Run `bash scripts/check.sh all` and the normal discovery smoke. Regressions cover
media quality, visible-content and static/self-hosted parity, skill digest and MCP
handshake consistency, private boundaries and actual WebMCP executors. After
deployment, rerun the scanner using its documented interface:

```http
POST https://isitagentready.com/api/scan
Content-Type: application/json

{"url":"https://mcp.hk"}
```

Retain the raw result and check messages. A level measures scanner criteria, not
indexing or AI citations. Auth/A2A/personal-agent findings remain explicit
non-applicable capabilities for this public data service. Verify real browser tool
invocations and MCP/HTTP requests, not just manifests. Follow `production.md` for
cron pause, adoption, fresh checkpoint restore and schedule recovery.

Primary sources:

- https://www.rfc-editor.org/rfc/rfc9727
- https://github.com/modelcontextprotocol/modelcontextprotocol/issues/1649
- https://github.com/cloudflare/agent-skills-discovery-rfc
- https://webmachinelearning.github.io/webmcp/
- https://agenticresourcediscovery.org/
- https://datatracker.ietf.org/doc/draft-mozleywilliams-dnsop-dnsaid/
- https://github.com/dns-aid/dns-aid-core
- https://isitagentready.com/.well-known/agent-skills/index.json
