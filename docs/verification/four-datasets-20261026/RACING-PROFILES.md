# Dated Racing profile observations

This increment adds horse, jockey and trainer observations to the existing
SQLite/R2 pipeline. It does not complete the full historical Racing programme.
Results and meeting participant identities retain their existing contracts.

## Source and output scope

The operating basis is the owner's authorized implementation of ordinary public
professional racing facts. This is not a claim of an HKJC licence or endorsement.
The exact qualified routes are the English and Traditional Chinese `horse`,
`jockeyprofile` and `trainerprofile` pages under
`https://racing.hkjc.com/{en-us,zh-hk}/local/information/`, with exact source-native
identifiers and `Season=Current` for professionals. Other origins, duplicate ID
parameters, arbitrary routes and historical season parameters are rejected.

Three real bilingual technical captures on 26 October covered horse
`HK_2024_K307`, jockey `PZ` and trainer `NM`. Each read was reserved in the existing
durable admission ledger before dispatch and settled with its actual byte count.
No raw HTML was retained. Those private normalized captures are development
evidence, not a public accepted version. Imports must verify the two original
settled admission IDs and byte counts; they do not seed or charge them twice.

Allowed output is the bounded set of source-displayed professional attributes,
source statistics cutoff, season-start career counts and displayed form rows.
Biographies, contact details, betting accounts, images, video and replay columns
are excluded. Horse owners remain disclosed source strings, without a company or
person identity crosswalk. Unknown currency for a bare `$`, unqualified import-date
interpretation and absent effective dates remain null. Annual race indices are
kept as source strings; race IDs require an exact date/venue/race-number link.
Current profile attributes never amend past races. Displayed form rows do not
establish complete career history.

## Activation, collection and recovery

An authenticated `profile_policy` action installs a checksum-pinned source record;
all new modes start unavailable. The record declares fields, routes, retention,
cadence, evidence and expiry. The audit retains previous policy records. Revocation
or expiry blocks affected collection, publication, serving and export without
deleting the last accepted checkpoint or changing another source's policy.

The cohort consists only of exact participants in accepted results. The existing
five-minute maintenance job alternates due result and profile work; no timer,
account, paid service or separate provider quota is added. Both languages resume
from normalized cached captures across bounded ticks. A 30-day per-profile refresh
target is not a guaranteed whole-cohort cycle. Provider attempts share the existing
200/day, 64 MiB/day ceiling, 400 KiB response bound and exclusive collector lock.
The policy's minimum request interval also applies. A completed unavailable response
defers the target by one day; parser drift is held for review. Unknown requests and
provider holds retain their charges and stop new source work.

New profile payloads have a separate 32 MiB aggregate cap and require 20 GiB free
space. The existing 500 MB database and 150 MB compressed backup bounds remain.
Stored versions are immutable, limited to 2 MiB each and checked on read. New facts
remain private until an independent R2 checkpoint download/restore matches every
Racing fact/control table. Publication then compares the old accepted pointer and
the pending candidate before advancing it. A failed or superseded candidate cannot
replace the previous observation.

## Public contracts

- `/api/v1/racing/profiles/{kind}/{source_id}` reads dated accepted attributes.
- `/history` returns 20 rows by default, maximum 100, with a signed 48-hour cursor
  bound to identity, version and language.
- `/export` downloads that profile and the selected history page, with JSON,
  formula-safe CSV, schema/field definitions, notice and member hashes.
- MCP adds `hk_racing_profile_observation` and `hk_racing_profile_history` only
  when an accepted observation and the current MCP mode are available.
- `/racing` keeps the meeting identity/appearances view and adds dated accepted
  observations when available, preserving the pinned version across sharing and
  language changes. Missing profiles leave meeting data usable.

## Verification and current limits

Regression coverage includes cohort/field checks, bilingual identity/count/date
semantics, staged-data privacy, same-file restore rejection, complete changed-state
restore rejection, last-good retention, stored-content corruption, signed cursors,
policy revocation, shared REST/MCP values and bounded source resumption. Eight local
browser journeys cover both languages at 320/390/768/1280 pixels, each with an actual
ZIP download and member/hash verification. Their source facts are invented; these
are not real-provider acceptance receipts. The browser tests use a sustainable
request pace through the unchanged shared public limiter.

A fresh production checkpoint was independently downloaded and restored at the
26 October 16:14 UTC checkpoint: 14 accepted meetings, 138 races and 1,733 result
rows. Historical collection is held on an HTTP 302 from the exact 15 July 2026
Happy Valley results URL. The preserved request and durable hold have not been
cleared, reclassified as a parser error, or bypassed. New source dispatch requires
resolution of that specific redirect; already charged completed captures can be
qualified without fetching again. Full season/history, declarations, sectionals,
dividends, trials/rankings and prospective observations remain separate incomplete
acceptance items.

Release evidence must still record exact-head hook/CI, actual runtime adoption,
real captured profile publication, live REST/MCP/bilingual/download parity and a
fresh accepted offsite restore. The acceptance ledger remains incomplete.
