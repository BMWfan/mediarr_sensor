# Cache contracts and policies

| Layer | Freshness / bound | Invalidation |
| --- | --- | --- |
| Shared normalized snapshot | fresh 15s; stale at most 24h; persisted schema v1, max 16 MiB | source/config/credential digest change; manual refresh |
| Snapshot revisions | last four revisions; pinned pages bounded by 24h | semantic rows/errors/completeness change; private check timestamps ignored |
| Plex normalized/catalog GET | 60s; HTTP RAM 128 entries / 16 MiB, individual 4 MiB cap | queue membership/status change; manual refresh; source change |
| Manager queue GET | 5s; views check every 15s while visible | membership/status invalidates catalog; percent-only updates do not |
| Verified identities | private HA schema v1; max 5000 title + 5000 external IDs | conflicting evidence becomes unknown; type/year/external IDs isolated |
| Title metadata | 6h in memory; missing artwork 5min; frontend stale good fields up to 7d | explicit retry; language/region/typed-ID change |
| Image bytes | RAM 256 entries / 32 MiB; each at most 5 MiB; versioned 24h, legacy 5min | independent thumb/art path hashes; source credential scope |
| Signed HA image grants | memory only, renew after 1h, valid 2h | frontend requests fresh projection at least every 30min |
| Broken artwork | exponential retry 15s to 5min while visible; cleanup on close | success resets attempts; semantic asset change resets failure |
| Failed source refresh | exponential jittered backoff roughly 15s to 5min | manual refresh bypass; successful recovery resets |

`mediarr/library` accepts optional `snapshot_id` and `since_revision`; response
adds `revision` and `cache` (`version`, `state`, `age_seconds`, opaque `scope_id`).
Matching first-page revision may return `unchanged: true`. All later pages use
the first-page snapshot ID. Older clients still receive ordinary groups. New
clients omit optional parameters for older backends that provide no revision.

Only a complete successful provider read confirms absence. Partial failure
retains only that provider's bounded last-good rows and marks them
`availability_stale`; failures cannot become an empty successful library. Initial
empty UI can show the first page early; updates to an existing complete library
commit after all pages. Films stay in the combined library when ready; only
explicit waiting-only filters exclude them.

Persist normalized pre-projection rows and public identity evidence, never
credentials, source configuration, signed access URLs or user write permissions.
Source isolation uses a private digest (never returned); image/play requests use
an unrelated opaque scope nonce and validate current source configuration.
Playback server identity, HA authorization and command readiness remain live.

No provider push/webhook, upstream ETag, fuzzy ownership, Redis, service worker
or new recommendation engine is claimed. Image ETags are downstream HTTP
validators, not evidence that Plex supports upstream conditional requests.
