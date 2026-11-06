# Coordinate transformation request repair — build proof, 6 November 2026

Frozen resource `1fd8818399022e50dd5f0752a45daa8f` advertises JSON at the exact
`http://www.geodetic.gov.hk/transform/v2/` URL. A request without coordinates
returns an HTML manual pointer, explaining the retained parse failure. This
adapter recognizes only the publisher's exact HTTP/HTTPS root and constructs the
verified HTTPS request with explicit caller inputs. It preserves the original
catalogue URL in provenance.

The [publisher manual](https://www.geodetic.gov.hk/transform/v2/tformAPI_manual.pdf)
and [data dictionary](https://www.geodetic.gov.hk/transform/doc/DataDictionary.pdf)
define five input systems. Discovery exposes their different required/optional
fields, declared formats and reference-digit rules before fetching. The adapter
validates finite bounded coordinates, encoded degrees/minutes/seconds, source
zones, height and output-system constraints; it forwards original strings, including
leading zeroes. Optional omissions retain provider defaults. It adds no geographic
binding or coordinate normalization to any other resource.

A finite live-source pilot used the original catalogue payload and the normal
DNS-pinned public-source fetch. Each of the five input systems returned a coordinate
object and passed local HTTP/native MCP parity: exactly five provider requests,
with no native-client re-fetch. Raw response hashes and field lists were retained
privately; record bodies are not published here. This is build/source evidence,
not deployed-client acceptance. The ARC lane was paused at a saved response and
resumed as the same validated process, keeping two source lanes at most.

| Input / output system | Raw response SHA-256 |
|---|---|
| wgsgeog / hkgrid | `eea046e5976d4fa9122ff1ada278d268b3065b1688479531530d32dc69197cd9` |
| hkgeog / wgsgeog | `a046ac90c2beea67e146c3fd0c037e817af4ae857c92bf582ca4c6d2ff2f5d5d` |
| hkgrid / wgsgeog | `a046ac90c2beea67e146c3fd0c037e817af4ae857c92bf582ca4c6d2ff2f5d5d` |
| utmgrid / wgsgeog | `b10945515af4a4642105b5fa1a957ea2f7cc862c5dad760b40c443fd1772849e` |
| utmref / hkgrid | `edd8c8abeb57dbdf57e5ba2f04f0b7b607dfe7f486fc21ad3a64ca8d37078f72` |

The first pilot found the missing HTTP catalogue alias and made zero provider
requests. The next stopped on a native maintenance lease before any provider
request; that local harness failure is not a source hold. The corrected harness
waited outside the local API request and completed all five source scopes. No
provider denial was retried through another host, header or proxy.

Tests cover every input system, raw response/context preservation, leading zeroes,
invalid fields/ranges/sexagesimal values, numeric exponent bounds and all seven
publisher error codes. Error envelopes cannot become accepted coordinate rows.
Existing published-request tests also pass. Required full checks, exact-head CI,
coordinated deployment, actual hosted clients and fresh isolated recovery remain
release gates. Other frozen reader/source/task holds remain open.

DEBUG REPORT

- Symptom: the coordinate API root has a retained JSON parse failure.
- Root cause: an unparameterized documentation response was read as JSON records.
- Fix: exact endpoint binding with conditional inputs and raw error-envelope validation.
- Evidence: five actual source responses matched local HTTP/native MCP; 48 focused tests passed.
- Regression test: `tests/test_geodetic_requests.py`, including the actual HTTP catalogue URL.
- Status: build/source verification complete; production release verification pending.
