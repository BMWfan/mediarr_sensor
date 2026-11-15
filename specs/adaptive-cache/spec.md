# Adaptive caching (L)

Goal: stable, immediate UI after reload, reliable cross-view film identity and availability, silent background revalidation and stable artwork. Preserve movies in the library. Initial load only: cinema reel.

Acceptance: bounded persisted server cache/identity with version/expiry and source isolation, no credentials or signed URLs stored; shared refresh coalescing; partial outage is not deletion; cache IDs resolved before catalog merging; stable loaded art with targeted missing art retry; no global background loading banner; no cached grants for writes; synthetic tests for restart/reload, concurrent reads, failure/recovery, deletions, image failures, reduced motion and live cross-view state.

Base: stacked on published movie-collections developer candidates; do not merge main without owner testing of the new developer release.
