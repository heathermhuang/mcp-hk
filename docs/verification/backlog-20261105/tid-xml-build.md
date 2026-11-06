# TID XML prefix — build proof, 6 November 2026

All 24 remaining original parse-failure resource bodies were inspected, reusing six
prior captures and making 18 new DNS-pinned requests under native maintenance gates.
Eleven are physically HTML. Ten have malformed JSON. Of the three TID feeds, the
English response parses after removing only the ASCII whitespace before its XML
declaration; the other two remain malformed after that diagnostic. These findings
are per original response, not inferred from one representative or an alternative
language. HTML pages can still require native-link/task investigation; their format
mismatch does not prove absence of underlying data.

The adapter is restricted to the three exact TID `messageFromUsEn/Tc/Sc.do` URLs.
It removes that non-content prefix only before an XML declaration, requires the
observed `DATA` root, and leaves strict XML/entity parsing intact. It does not fix
broken attributes or tags. A well-formed HTML response is rejected for these feeds.
Original bytes, source hash, element values and response size remain authoritative.

The English source, resource `851aab38d8c7932828567d37432a092a`, is 2,906 bytes with
SHA-256 `48c52ecaa62fe9de8918a0cde5dc7c4ae176c3ef09913b48cfcda04745e969cf`.
Dated local HTTP/native MCP replay returns the same one root response object with
zero provider requests. This is neither a count of notices nor hosted acceptance.
Both other captured language responses still fail strict XML parsing at their
malformed markup; no language substitution or success claim is made for them.

Regression tests cover raw values/source hashes, exact URL boundaries, malformed
markup, HTML and forbidden XML entities. Existing serialization tests pass. Full
checks, exact-head CI, hosted HTTP/MCP, fresh immutable backup and isolated restore
remain required before release acceptance. Other frozen source/task holds remain.

DEBUG REPORT

- Symptom: the English feed's XML declaration is rejected at its displaced position.
- Root cause: leading whitespace before the XML declaration in the original response.
- Fix: exact-source framing adapter, strict `DATA` root and unchanged XML parsing.
- Evidence: complete dated original-body replay; one English object, two sibling holds.
- Regression test: `tests/test_resource_serializations.py` prefix/root/entity cases.
- Status: build/replay verified; production release pending.
