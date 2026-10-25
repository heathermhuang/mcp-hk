# Focused code, security and data-semantics review

Review scope: the actual HKEX diff against current main, reviewed H01–H10/shared
contracts and the installed pre-landing checklist. No independent-agent review is
claimed. Findings below were fixed in this checkout and covered by focused tests.

- SQL/migration correctness: renamed reserved `window` column; schema re-entry now
  works for an existing source-only owner without broad CREATE DATABASE privileges.
- Locking: collection sessions and transactional publication use distinct lock keys;
  backup/restore qualification takes both, avoiding cross-connection self-deadlock.
- Durable limits: exhausted per-run budgets remain charged. The next ordinary
  occurrence can resume known partial work; uncertain requests still require explicit
  reconciliation. Independent inventory hashes provide a bounded unchanged exit.
- Coverage: require independent page/serial/detail hashes, reject page drift, missing
  source dates, inconsistent window basis and unresolved revision closure; an empty
  accepted window still retains its exact issuer/security identity.
- Reader/privacy: strict served-filing/issuer validation rejects unexpected fields.
  Public lineage uses a metadata-only view. Status cannot leak restricted issuer or
  filing inventory when a consumer's output mode is denied or unknown.
- Rights/races: recheck currently pinned policy under publication/pointer locking and
  before return; test mid-run revocation. A later policy cannot grant rights to an
  older captured version by assumption. No runtime public flag enables a source.
- Recovery: pg_restore explicitly selects its isolated database; source-wide logical
  equality covers raw bytes, policies, runs, requests, all relations and pointers.
  Fingerprints stream rows and sort fixed-size hashes rather than buffering history.
- Surface integration: real ASGI REST/MCP parity caught and fixed a dispatch parameter
  collision. Route-level ID/version validation now yields typed query errors.
- Retention: expiry follows the oldest retained detail capture across resumed
  runs, rather than publication time; expired versions cannot expose issuer identity
  through status or materialise a new export.
- Identity round-trip: the exact returned `hkex:di:` and `hkex:issuer:` identifiers
  are accepted by public detail/list contracts, retaining original serial values and
  forbidding cross-namespace coercion.
- Resource discipline: no live transport, new source timer, paid resource, provider
  outreach, source sweep or production data mutation is hidden in registration.

No known blocking defect remains in the disabled engineering scope after the recorded
checks. Source rights, an actual provider parser/inventory, real pilot/offsite recovery,
production data activation and ordinary-operation observation remain activation
blockers. A tested normalized contract is not proof of those external properties.
