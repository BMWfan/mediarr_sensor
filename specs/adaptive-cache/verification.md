# Verification (2026-11-15)

- `docker exec mediarr-cache-tests python scripts/test-ha.py`: **82 tests PASS**.
  The runner asserts actual HA Core 2026.11.1; image digest is pinned in the
  existing metadata workflow. Tests use simulated responses and in-memory stores.
- Covers concurrent forced reads, immediate stale returns, retry backoff, private
  restore/expiry/config isolation, in-flight config changes, bounded revisions,
  partial source retention vs confirmed empty reads, catalog/queue invalidation,
  uncached Plex identity, durable typed IDs/conflicts, metadata single-flight,
  optional storage failure, thumb/art independence, image ETag/304 and play scope.
- Copied source/manifest into the disposable loopback HA runtime, compared bytes,
  restarted HA and ran `scripts/smoke-ha.mjs`: **PASS** for authenticated real
  commands, missing-provider errors, disabled capabilities and config-flow schema.
- `python3 scripts/check-python.py` and `git diff --check`: **PASS**.

Paired frontend checks run against real disposable HA with synthetic provider
transports. They do not prove production Plex/Seerr connectivity, physical player
control or Safari behavior. Restart persistence here is tested with simulated
storage/recreated clients, not a production account. No credentials from any
production system are used.

Exact PR CI commit/artifacts, HACS tag and manifest-byte verification are recorded
on the stacked PR after CI/release completion. Owner testing and fresh explicit
approval are required before any main merge or stable release.
