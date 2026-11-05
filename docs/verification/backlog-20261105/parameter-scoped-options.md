# Preserve explicit parameters when following schema choices

The actual historical-airport schema accepted `parameters.date`, returned two
native response groups, and advertised a schema next action that omitted the
required date. Following that action lost the context. Parameter-dependent choices
also used the same shared option cache as unrelated requests.

Schema next actions now carry the caller's explicit source parameters. These
choices are returned only in that response; they neither overwrite the public
option cache nor borrow another parameter context's cached choices. Parameter
discovery with missing values returns no cached choices. Discovery shortcuts also
reject undeclared parameters before source contact. Existing static options retain
their normal bounded persistence and backup behavior. No date or service type is
invented and no source acceptance is implied by an option.

Regressions execute a generated action through native MCP, verify the same
parameter context for parameterized workbook sheet selection, prove that public
options remain unchanged without the supplied values, and reject ignored
parameters without a provider request. Actual deployed action-following and fresh
recovery remain release gates for this fix.

The separate airport read used the original published URI with the explicit date
`2026-11-05` and fixed passenger/departure/English flags. Actual HTTP and native MCP
returned the same two groups, dated 4 and 5 November, retaining all nested source
lists (404 observations in that response). Those are neither 404 independently
identified flights nor current-service predictions. The source time strings and
the relationship between requested and returned dates remain unnormalized.
The [official specification](https://www.hongkongairport.com/iwov-resources/misc/opendata/Flight_Information_DataSpec_en.pdf)
describes historical data through the previous calendar day. The existing generic
reader supports the published placeholder; no new provider or route is introduced.
