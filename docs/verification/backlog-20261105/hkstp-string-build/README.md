# HKSTP recruitment JSON string — build evidence, 6 November 2026

Exact original resource `df2492726bb048a59ad63da80a5295b6` returns a JSON string
containing a complete JSON array at
`https://opendata.hkstp.org/corporate/recruitment/v1/`. The existing generic reader
correctly preserves a generic string, but this exact publisher framing turns the
previously accepted job-field schema into one `value` field and triggers drift.

The narrow serialization reader decodes exactly one string layer for that exact
URL and format. It requires a complete array of objects, rejects duplicate keys,
nonfinite numbers, incomplete framing and scalar/error strings, and keeps existing
row/field/source limits. Standard arrays retain the ordinary reader. Other URLs
are unchanged. The original outer response remains the content hash/version and
byte-count evidence. Values and 13 original fields are retained, including nulls,
leading zeros, dates, salaries and text; no active-vacancy, entity or eligibility
qualification is added. Empty arrays remain subject to ordinary schema-drift rules.

The previously saved 273,907-byte response (SHA-256
`34fb8006cb9d0e43cf1cb8d6e1c3a772488d3f70abde9b1287661e5312d450ea`)
replays all 501 objects without value changes, matching the historical accepted
field contract. Local HTTP/native MCP parity passed with one fixture read and no
provider requests. This is fixture/build evidence, not hosted current acceptance.

Focused reader tests: 42 passed. Full Python suite: 1,010 passed, 122 expected
skips. Formatting/lint passed. Required push-hook and exact-head CI remain release
gates. Hosted verification and fresh backup/isolated restore remain pending.
