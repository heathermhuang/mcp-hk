# Census published files — released 6 November 2026

PR [#164](https://github.com/heathermhuang/mcp-hk/pull/164) is deployed at
`a7ad82d521afa11b08c19375aaf880cc055ab311`. All five exact-main workflows passed. Worker
`f5eaaf14-ff66-4080-8837-21d52a170b7b`, immutable image, private controller and native
application/running-instance version 82 were independently verified.

The three original XML-labelled district-profile resources return HTML indexes.
They now expose the actual published file choices. Every selected download is
checked against its current same-origin source page; workbook sheet actions retain
that file context. No URL/default-file guessing, credentials or source fallback is
introduced. Unknown choices/invalid selectors cannot clear a source access hold.
Original page/file provenance and raw values remain distinct.

All three original resources exposed fourteen file choices each. The hosted
HTTP/native MCP walk visited every original file frontier and followed discovered
sheet actions. 57 file/sheet scopes passed; 0 remain explicitly
unresolved in the receipts. Discovery choices alone are not acceptance. Raw rows
can include secondary headers/notes and positional field labels; counts are not
qualified statistical observations, district/entity counts or representation/
language equivalence. No new native dataset/resource or geographic binding is added.

Fresh accepted archive `5454119c7dde31a69f71baaffe43b555b93778acd7d2c7508200df688bea1d9d` was independently
retrieved from immutable R2. Its 114,938,107 bytes restored 331,206,656 SQLite /
362,361,939 total bytes. Producer checksum, captures, integrity, accepted
packs, source registry, both inventory generations, existing bindings and retained
JSON/WFS/HKMA/workbook facts passed. 57 accepted file/sheet metadata facts and
all root choices recovered; 0 additional dated scopes remain subject to the
existing per-resource variant-retention bound. Two exact English DC record scopes
(one archive and one workbook) matched local HTTP/native MCP with zero provider
requests. Other source rows are not claimed as a complete offline replica of all
files. The 4 MB row cache, 50 variants and all source/recovery bounds are unchanged.

A local helper-copy omission initially stopped the wrapper before that step made
any request. The checked helper was restored and only the remaining checks ran;
prior passing regressions and the failure receipt were retained.

Legacy point, Census/RVD, CTB/KMB/NLB, published-interface, LocationSearch and scoped
historical-action client regressions passed. Only resource cron was paused; native
five/four-schedule read-back timed the full propagation window and native leases
were respected. The pre-deploy archive restored independently. Adoption was awaited
without redeployment/lease clearing; the cold new instance started through its
ordinary health request. All five schedules were independently restored/read back,
final health passed, only the owned slot was released and source qualification
processes resumed according to their observed journals.

The complete frozen programme remains open: wider qualification graphs, interactive
Census builder work, exact source/schema/capacity investigations and independently
evidenced semantic tasks continue. Diagnostic HTML/challenge/empty-file samples are
not converted into empty datasets or group-wide closure.
