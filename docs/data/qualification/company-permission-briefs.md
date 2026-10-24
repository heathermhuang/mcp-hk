# Source permission briefs — UNSENT

24 October 2026. These briefs request a decision, not permission inferred from
public visibility. No message has been sent, terms accepted, contract signed or
paid feed ordered. All gated collectors and public output modes remain absent.

## Gazette / Government Logistics Department

Purpose: an attributed company-notice chronology on mcp.hk, preserving exact
published identifiers, notice type, issue/event dates and corrections. Proposed
pilot: complete issues in one declared week, including all relevant pages, rather
than the capped search results. Please identify an authorised automated download
route, permitted cadence and limits, and separately confirm permission to retain
source notices and parsed observations, keep correction/history records and
backup copies, serve source-linked facts through public REST/MCP, export derived
records, and redistribute original PDFs (optional and independently gated).

We would distinguish proposed striking-off, actual dissolution, withdrawals and
restoration; absence and a name match would never establish dissolution. Please
specify attribution, expiry/recheck, deletion and personal-data conditions. No
unattended extraction begins without an exact permitted route.

Evidence: [Important Notices](https://egazette.gld.gov.hk/en/important-notices),
checked 24 October: prior written authorisation for reproduction/distribution and
50 search matches per category. Main Gazette/extraordinary and supplements have
different available-date boundaries. These statements are source constraints,
not a legal opinion on an alternative route.

## SFC corporate licence verification

Purpose: allow a person to verify the corporate institution they intend to deal
with, by exact CE reference, with source dates and a link to the official register.
Pilot: at most 25 corporate CE references, at most 100 reads/day, one concurrent
request, subject to a stricter provider limit. No contact/marketing dataset,
individual-role expansion or inferred BRN crosswalk is proposed.

Please confirm separately the approved automated access route and purpose,
short-term cache duration, retained dated corporate licence/activity observations,
correction history, backup retention, public source-linked REST/MCP verification
responses and user page exports. If general public responses or exports are not
allowed, please specify an appropriate verification-only presentation and whether
access must be user initiated. Please specify permitted update frequency,
identifiers, available historical dates and attribution. We will preserve unknown
intervals and will not infer a former-executive-officer history.

Evidence: [SFC register legal information](https://www.sfc.hk/en/Regulatory-functions/Intermediaries/Licensing/Register-of-licensed-persons-and-registered-institutions/Public-register-of-licensed-persons-and-registered-institutions),
checked 24 October: specified verification purposes; daily end-of-day updates;
former executive-officer records excluded. Each requested mode remains unresolved.

## HKEX Part XV DI

Purpose: source-linked disclosure chronology, initially one issuer and a declared
seven-calendar-day filing window. Please identify a DI-specific authorised
programmatic listing/detail route or provide written permission covering bounded
retrieval, all pages/corrections, retention/backups, derived structured facts,
amendment links, public REST/MCP, exports and source links. Please provide request
limits, attribution and deletion/recheck obligations, and identify any paid route
and price for separate human approval before commitment.

We will retain event date separately from submission/publication dates, exact
filing/issuer identifiers and replacement links; disclosures will not be labelled
trades or present holdings. The pilot does not include prices, CCASS or trading.
DION (since 3 July 2017), non-DION (1 April 2003–2 October 2017) and the transition
interval will be qualified separately.

Evidence: [HKEX terms](https://www.hkex.com.hk/global/exchange/terms-of-use?sc_lang=en)
sections 4–5 and [DI guide](https://www2.hkexnews.hk/Shareholding-Disclosures/Disclosure-of-Interests?sc_lang=en),
checked 24 October. General terms restrict programmatic access and reuse; the
published permission contact is info@hkex.com.hk. No DI-specific exception was
established. This is an unsent brief, not authority to contact that address.

## Scoped recurring offsite uploader decision

Current authority covers release-time uploads through existing operator access.
It does not authorise copying broad operator OAuth or the gateway OPS token to the
host. Proposed route for approval: an R2 S3 credential limited to the existing
mcp-hk-backups bucket, and preferably only the curated official-backup prefix if
the provider actually supports that restriction. Do not describe a bucket-scoped
credential as prefix-scoped. Required permissions are immutable object PUT and
verification GET/HEAD, with no deletion, other buckets or gateway maintenance.

Store only on the dedicated host in an owner-only uploader configuration; never
in reader containers, source receipts, URLs or logs. Upload dump, checksums,
source/transform metadata and manifest first, independently retrieve/verify them,
then advance an offsite pointer. An actual fresh restore and observed daily upload
are required before advertising a 24-hour RPO or enabling catch-up/address growth.
If the available R2 mechanism cannot restrict permissions as requested, return the
actual scope for human approval before creating/installing a credential.

This route has not been provisioned or approved. Daily local dumps and the weekly
host policy remain distinct from daily offsite uploads. No expanded catch-up or
100/250-address stage may be enabled solely because this brief exists.

### Concrete prepared capability (preferred to distributing an R2 parent token)

The code now includes a disabled-by-default `/__company-backup/` capability on the
existing Worker and a fixed-origin host uploader. With no dedicated
`OFFICIAL_BACKUP_TOKEN`, every request returns 404. A new, separately approved
host-only credential would permit only PUT and GET/HEAD of three exact artifact
names inside `curated/official/daily/<timestamp-random>/`. No list, delete,
mutable overwrite, arbitrary object path or gateway operation is exposed. The
Worker uses existing R2 binding access without passing it to the host. R2 checks
SHA-256 during immutable conditional upload. The host retrieves and checks dump
and source metadata before writing/retrieving the immutable manifest recovery
pointer. The dump bound is 256 MiB and each metadata object 1 MiB.

The capability does not claim that an uploaded dump has been restored. Activation
requires explicit approval, creation and secure installation of its distinct
credential, real negative-scope tests, a fresh independent restore and an actual
unattended upload. A daily systemd invocation is still to be installed/qualified
with that approved route. No credential has been created by preparing this code.

[Current R2 temporary-credential docs](https://developers.cloudflare.com/r2/api/s3/temporary-credentials/)
also describe prefix and explicit-action scoping through local signing. Such a
route still needs a parent credential and reliable renewal issuer; broad OAuth
must not be copied to the host as a substitute. The dedicated prepared capability
avoids putting an R2 parent credential there.
