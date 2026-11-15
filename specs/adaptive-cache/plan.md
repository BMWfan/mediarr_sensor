# Plan and analysis

1. Research primary cache guidance and inspect actual source/identity/art paths.
2. Add shared backend stale-while-revalidate with source isolation, single-flight,
   private restart persistence, bounded retention and failure backoff.
3. Separate slow catalogs from fast queues; retain failed provider rows, validate
   source envelopes and preserve partial episode-progress errors on cache hits.
4. Persist verified typed identity evidence; enrich current authenticated rows
   before merging catalog matches, without inventing ownership or matching remakes.
5. Add revision-pinned pages, unchanged responses, event notifications and
   visibility-aware frontend checks. Commit background snapshots atomically.
6. Keep decoded art stable, separate art/thumb revisions, implement private image
   validators and targeted missing/broken image recovery. Retain prior good art.
7. Show a delayed, reduced-motion-safe cinema reel only on empty initial load.
8. Verify synthetic backend/model/real HA browser regressions, review exact CI
   evidence, publish paired HACS developer candidates and verify tagged bytes.

Analysis: cache is optional and bounded; failures are not deletions or write
grants. A private source digest isolates data across configuration changes;
current auth and server/player checks remain authoritative. Unknown provider
push/validator contracts are deferred. Rollback uses the previous dev tags.
