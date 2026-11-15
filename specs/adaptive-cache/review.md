# AI review

Reviewed changes against cache contracts, source/auth isolation, paired-version
compatibility and synthetic evidence. Findings corrected before publication:

- Swallowed rejected HA event-unsubscribe acknowledgements during rapid view changes.
- Retained partial episode-progress errors on normalized Plex cache hits.
- Validated upstream library/queue response envelopes before treating emptiness as deletion.
- Kept optional storage failure from breaking otherwise successful source reads.
- Preserved decoded artwork across grant renewal, reset failed-image retry handles,
  canceled retry timers on close and postponed retry traffic while hidden.
- Kept independent thumb/backdrop revisions and cleared old hero art when a new hero lacks it.
- Limited visible missing-art enrichment to four concurrent metadata requests.
- Kept live Plex identity/authorization checks uncached and rejected stale source scopes.
- Excluded private source-check timestamps from public revision changes.

No workflow changes or production writes. Provider push, upstream conditional
requests and durable Plex first-import history are outside this change. A file
update is verified not to change the `addedAt` field consumed here; this does not
claim Plex itself never replaces an item's added timestamp.

Main/stable publication remains an owner decision after testing the new developer
pair. CI and tagged-byte verification are recorded on the stacked PRs.
