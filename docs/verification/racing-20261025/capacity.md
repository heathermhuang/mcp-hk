# Shared host capacity — read-only snapshot

25 October 2026, about 05:15–05:20 UTC. Existing approved DigitalOcean droplet
`mcp-hk-curated-20261024`, ID 612072562, `sgp1`; current provider identity matches.
No resource, backup plan, host job or source database was changed.

| Item | Observed / allocation |
| --- | --- |
| Host disk capacity | 82,086,711,296 bytes |
| Available disk, first/follow-up | 56,241,778,688 / 55,820,034,048 bytes |
| RAM total / available | 3,915 / 2,953 MiB |
| Main curated database | 6,528,998,423 bytes |
| Existing offsite verification database | 5,965,274,135 bytes |
| Existing official restore database | 59,374,615 bytes |
| PostgreSQL maintenance database | 7,699,479 bytes |
| Racing durable growth for this release | **0 bytes**: no production schema/data/source timer |
| SFC release ledger reservation | 0 bytes for its gate-only release |
| HKEX allocation | Must reconcile its current release ledger before activation |
| Proposed initial future racing growth | At most 1 GiB, including captures/index/WAL/backup allocation; not reserved or activated |
| Required new-growth free reserve | 20 GiB minimum, preserving any stricter current owner guard |

The change in available disk occurred while the separately owned official offsite
service was activating. This is a bounded observation, not a measured restore peak
or attribution of every byte. The main database and existing restore clones are
already included in disk use; do not double-count them as free capacity.
Current files already encompass Enigma/CR, indexes, WAL, local dumps and immutable
host code. Independent offsite objects are outside this host's filesystem total.

A combined growth/restore forecast must include all three source allocations,
accepted/staging versions, raw retention, indexes, WAL, local and downloaded dumps,
restore clone and temporary work. This gate-only release adds no forecasted source
growth. It does not qualify any source's 1 GiB allocation or daily RPO. The existing
US$24 compute + US$4.80 weekly backup = US$28.80/month before tax baseline remains
within the recorded US$30 approval; no invoice measurement or new spend is claimed.
