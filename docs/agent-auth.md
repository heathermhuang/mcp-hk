# Optional hosted agent access

Anonymous `/mcp` and `/api/v1/*` access stays available. The managed Cloudflare
deployment additionally implements anonymous-start agent registration, owner claims,
OAuth JWT-bearer exchange, public OAuth clients with authorization code + PKCE S256,
and immediate access-token/registration revocation. Only `data.read` is granted.
This does not grant writes, operator privileges, higher quotas or private records.
The standalone Python/stdio server does not run an authorization server; its
`/auth.md` points explicitly at the optional hosted implementation.

## Agent journey

1. Read `/.well-known/oauth-protected-resource` and the advertised authorization
   server metadata. Root metadata identifies `https://mcp.hk`; path-specific
   `/.well-known/oauth-protected-resource/agent/data` identifies
   `https://mcp.hk/agent/data`. Both describe the same finite read-only mirrors.
   Request the exact advertised resource; tokens bind their audience to it.
2. POST JSON `{"type":"anonymous","scopes":["data.read"]}` to `/agent/identity`.
   Save the returned identity assertion and claim token privately. The assertion
   is signed with ES256 and the key published at `/oauth2/jwks`.
3. POST form fields `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`,
   `assertion=<identity_assertion>` and `resource=https://mcp.hk/agent/data` to
   `/oauth2/token`. Use the access token as an Authorization bearer header.
4. GET `/agent/data/packs`, `/agent/data/catalogue/datasets` or
   `/agent/data/status`. The Worker checks durable token/registration state on
   every call, strips authentication/cookies before the existing data controller,
   and preserves its network-IP and shared request budgets.
5. POST `token=<access_token>` to `/oauth2/revoke` to revoke that token. The
   identity assertion can still mint another token until it expires. Revoking
   the identity assertion revokes its whole registration and all access tokens.

Token responses are never cached. Access tokens live at most 15 minutes;
assertions at most one day. No refresh token is issued. Tokens validate signature,
issuer, audience, type, key ID, expiry, scope and durable registration version.

## User-controlled claims

The owner creates an optional recovery-key account at `/agent/account`. It has an
opaque ID and a high-entropy random recovery key, shown once. There is no email,
name, password reset, external identity provider or verified-human identity claim.
The account represents control of the recovery key. The user saves it outside the
agent and shares only the public owner ID with the agent.

The agent sends its private `claim_token` and `owner_id` to `/agent/identity/claim`.
The response supplies a high-entropy private verification URL and a six-digit code.
The signed-in owner types the code on that page. Claim confirmation checks the
selected owner, private attempt URL, code, same-origin POST and session CSRF token.
Attempts expire after ten minutes and five incorrect codes lock the attempt.
The agent polls `/oauth2/token` with the claim grant advertised in metadata, no
faster than every five seconds. Completion rotates the registration version,
invalidates all pre-claim credentials, and returns fresh credentials with the
same read-only scope. A claim token completes once.

Claimed registrations live at most 30 days, bounded by the owner's remaining
90-day account lifetime. The account page lists and revokes each agent registration (at most 200 active
registrations per owner). Sign
out removes the one-hour Secure/HttpOnly/SameSite=Strict session cookie. Credentials
never appear in query strings, except the high-entropy private verification handle
needed by the claim page; HTML pages send only the origin as referrer (never the
private path/query), with no-store and a restrictive
CSP, contains no analytics and is excluded from crawling.

OAuth browser clients can register exact HTTPS redirects (numeric loopback HTTP
for local clients). Authorization requires a signed-in owner and explicit
same-origin consent. Only S256 PKCE is accepted. Codes expire after one minute
and are consumed once; client, redirect and verifier must match. Requests with
invalid redirects are never redirected to those addresses.

## Storage, limits and recovery

`AGENT_AUTH` is a separate SQLite Durable Object. It holds the service signing key,
hashed owner recovery keys, session/claim/code hashes, opaque registrations, OAuth
clients and credential-free audit events. It never shares the data container's
SQLite database or R2 source-data archives. Private signing keys never leave the
DO; JWKS contains only the public key. A process restart reloads the same signing
key. Do not delete/recreate the namespace or regenerate its key during deployment.

Anonymous registration and public OAuth client registration each allow five/hour
per daily-HMAC network identifier and 100/hour globally. All non-discovery auth
requests share 60/minute per identifier and 10,000/day globally. The 8 KiB auth body
limit is independent of the existing data limit. Account creation and login have
additional bounds. Expired records are deleted on activity and by an hourly DO
alarm while records remain; audit events expire after seven days. Cloudflare's
SQLite point-in-time recovery can retain deleted storage versions for 30 days.
Restoring historical auth storage can resurrect revoked credentials; incident
recovery must revoke all registrations before accepting traffic again.

The existing operator credential can POST `/__ops/agent-auth/revoke-all` for bulk
revocation. That route is private and is not a public tool. This permanently
invalidates the current registration versions; it does not affect anonymous data.
No public credential is accepted by any `__ops` endpoint.

## Verification

`agent-auth.test.mjs` exercises real ES256/JWKS verification, persisted keys,
registration/exchange/use/revoke, owner binding, CSRF, claim expiry/guess limits,
rotation, public OAuth consent, exact redirect checks, concurrent single-use code
exchange, scope/body limits and durable rate limits. Run the required full gate
with `bash scripts/check.sh all`. Smoke the real Worker/DO before release and the
production flow afterwards. Never retain raw live credentials in public receipts.

The Auth.md draft and scanner use evolving metadata names. Both `identity_endpoint`
and `register_uri` (and claim endpoint aliases) identify the same implemented
anonymous registration/claim handlers. Provider ID-JAGs, service-auth email flow,
provider event receivers, A2A and Poppy are not advertised as implemented.

References: [Auth.md](https://workos.com/auth-md/docs/apps),
[RFC 8414](https://www.rfc-editor.org/rfc/rfc8414),
[RFC 9728](https://www.rfc-editor.org/rfc/rfc9728),
[RFC 7523](https://www.rfc-editor.org/rfc/rfc7523),
[RFC 7009](https://www.rfc-editor.org/rfc/rfc7009),
[RFC 7591](https://www.rfc-editor.org/rfc/rfc7591).

## Recovery rotation and scoped containment (candidate, not deployed)

Successful recovery login now consumes the old key atomically, returns a new key
once, and invalidates every previous owner session, including another client's
already-issued cookie. Explicit **Replace recovery key and revoke other sessions**
does the same from a valid CSRF-protected account session. Ordinary sign-out remains
local to that session. None of these actions renews the original 90-day account expiry.
Legacy owner records migrate on recovery; legacy cookies without a generation fail
closed and must sign in with their existing key. Revocation survives service restart.

Save the replacement before leaving its response. If the body is lost but the new
cookie arrived, use that session's replacement action again. If both key and session
are lost, the account cannot be recovered: there is no identity/email backdoor. Create
a new account and have the operator contain the known old owner ID when necessary;
do not reset signing keys or delete the namespace to recover an individual account.

The authenticated operator endpoint `POST /__ops/agent-auth/contain-owner` accepts
only JSON `{"owner":"owner_…"}` (the exact account ID, not a recovery key). It removes
that owner's recovery/session/claim/authorization artifacts and revokes associated
registrations, including pending claim registrations, in one storage transaction.
It leaves unrelated owners operational and records a credential-free containment
audit event. Repeating it is safe; retain failed/unknown responses and inspect state
before relying on containment. Never exercise it against real accounts as a test.
`/__ops/agent-auth/revoke-all` deliberately retains its registration-only meaning.

Account create/recovery/rotation/containment events retain opaque owner identifiers
and timestamps for seven days; no key, cookie, token, CSRF value or source payload is
written to the audit. Auth records remain in the separate auth Durable Object.

Rollback must retain current auth storage. Deleting old sessions/recovery records
helps preserve invalidation, and disabled owners are removed with a tombstone, but
older code can reopen lifecycle gaps for subsequent actions. Do not roll back the auth
service to pre-remediation code or restore a historical auth snapshot; restrict the
affected path or forward-fix while retaining revocation. Data snapshot restore is a
separate operation and never restores auth state. See the [candidate status](security/remediation-20261024/README.md).
