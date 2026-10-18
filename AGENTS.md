# mcp.hk working instructions

- Run Python checks with `PYTHONPATH=src` and the project environment. Required CI
  covers Python 3.10/3.11/3.12, formatting/lint and Worker tests/type checks.
- Preserve dirty primary checkouts; use an isolated checkout for releases.
- Follow `docs/production.md` for controller/container deployments. Pause only the
  resource cron through trigger configuration before changing Worker/DO code;
  allow the documented propagation window and any owning maintenance lease.
- Never clear a lease after an interrupted response. Preserve failed/unknown
  receipts and the last checksum-verified accepted checkpoint.
- A static release header does not prove controller or container adoption. Verify
  private controller diagnostics, actual backend policy and accepted-pack readiness.
- Keep the resource cron paused through adoption, then restore all five configured
  schedules. Recovery uses short checkpointed `resources` batches, with health checks.
- Completion requires live HTTP/MCP regressions and an isolated restore of a fresh
  accepted backup. Distinguish source validation from observation age, semantic
  qualification and upstream availability; never turn source failures into empty data.
- Offload blocking SQLite work from async reader/review paths, including cache LRU
  touches and failure writes. Preserve the real-lock event-loop regression tests.
