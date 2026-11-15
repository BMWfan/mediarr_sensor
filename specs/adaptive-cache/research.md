# Cache research (2026-11-15)

Primary sources read directly, not just search snippets:
- RFC 5861: stale-while-revalidate and stale-if-error: https://www.rfc-editor.org/rfc/rfc5861
- HTTP validators/cache semantics (ETag/conditional revalidation): https://www.rfc-editor.org/rfc/rfc9111
- TanStack Query: freshness vs garbage collection, retries, structural sharing: https://tanstack.com/query/latest/docs/framework/react/guides/important-defaults
- Persistence with expiry/schema buster: https://tanstack.com/query/latest/docs/framework/react/plugins/persistQueryClient
- Targeted invalidation: https://tanstack.com/query/latest/docs/framework/react/guides/query-invalidation
- SWR focus/reconnect and visibility-aware revalidation: https://swr.vercel.app/docs/revalidation
- Error backoff while keeping usable data: https://swr.vercel.app/docs/error-handling
- HA DataUpdateCoordinator debouncing, push and unchanged-result suppression: https://developers.home-assistant.io/docs/integration_fetching_data/
- Plex notifications exist, but need a properly managed connection/recovery lifecycle: https://python-plexapi.readthedocs.io/en/latest/modules/alert.html
- Radarr distinguishes import, file upgrade and movie deletion events: https://wiki.servarr.com/radarr/settings

## Project decisions
Use these patterns in the existing plain-JS/HA stack, not React Query itself,
a new service worker, Redis or another background service. Shared backend
snapshots and stable identity reconciliation are the source of truth across
views. Long-lived metadata/artwork do not share the freshness rules of file
availability, queues, players or command readiness.

First paint uses available snapshots; background updates never show a global
loader or clear content. Initial empty load gets a contained cinema reel,
accessible status and reduced-motion support, without fake percentages.
Single-flight prevents concurrent tabs/cards from multiplying upstream reads.
Provider failure retains bounded last-good data and marks it stale; successful
complete provider reads may confirm deletion. Last-known data never grants a
write/control permission. Durable identity knowledge enriches only current
authenticated source records, never invents ownership or fuzzy-matches remakes.

Artwork uses separate semantic thumb/backdrop revisions, stable loaded image
nodes, targeted failed-image retry and shorter negative TTLs. Expiring signed
HA URLs are access grants, not artwork revisions, and are never persisted.
Poster existence does not imply a backdrop exists.

Push/webhooks and provider-supported ETag requests are useful follow-ups only
with verified contracts and lifecycle/auth tests; no pretend push or unsupported
conditional headers. Existing HA events can notify views when a shared refresh
finishes. Membership/identity is unified so Trending's checkmark and the library
update in one pass. Films stay in the library; only waiting-only filters change.
