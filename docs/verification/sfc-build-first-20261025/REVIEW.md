# Build-first implementation review

Reviewed the actual fetch/parser/collector, raw-source lineage, operator CLI and
Webb archive UI against the existing source-isolation and publication contracts.

Corrections made during review:

- Network read timeouts alone do not cap a slowly streamed whole response. Added
  an overall asynchronous response deadline around the full bounded body; identity
  content encoding avoids an unbounded decompression step. Fixed origins and no
  redirects/proxies remain enforced.
- Source date strings use an explicit English month/date representation. Added
  deterministic parsing and retained raw strings with validated ISO day values;
  no machine-locale guess or invented timestamp timezone.
- Inline duplicate licence assignments could otherwise evade a start-of-line
  packet detector. Duplicate/ambiguous assignment and duplicate JSON keys now fail.
- Corporate bilingual name spans stay separate; names are never an identity join.
- The catalogue activity's `status=R` is not a licence-status claim. Overall and
  per-interval status remain `not_supplied` on this licence-history route.
- New source lineage is included in the immutable version manifest; restore proof
  and publication bind its checksum as well as facts. A 403 now retains a forbidden
  hold, independently from a 429 Retry-After rate-limit hold.
- Archive licence type is displayed explicitly, including registered institutions;
  it is not assumed from a CE or confused with the corporation-only new-source scope.
- Archive UI pins the response version, bounds rows and identifiers, uses text
  nodes, distinguishes empty from failed, preserves labelled prior results on a
  failed replacement request, and contains its table at mobile widths.

No blocking findings remain in the build under the exercised contracts. Saved
public-page replay and one bounded private development observation establish the
real parser interface; synthetic HTTP/PostgreSQL tests establish controlled full
pipeline behavior. They are not a claim of a public fresh-data launch, complete
SFC register coverage, current-status judgment or ordinary unattended collection.
The source's former-EO and individual-directory exclusions remain outside this
corporate-only fresh-source build. No paid feed, enquiry, new terms or credentials
were requested to implement it.
