# Library provenance — Issue #44 (SDD-Light M)

## Problem and scope
Card Issue #44 and its SPEC-046 pilot handoff distinguish request state from media availability. Scope here: additive producer status contract. Paired repository changes stay in separate branches/Draft PRs. No production access, paid model/API calls, merge, release, CI/release workflow changes, import-date invention or fix claim for the unobserved live Plex report (#41).

## Contract and acceptance
- Producer preserves legacy `status = request.status` and adds `request_status = request.status`, `media_status = request.media.status` (null if absent); no enum conversion or ownership inference. Existing type, IDs and dates remain intact.
- Request enum: 1 pending, 2 approved, 3 declined, 4 failed, 5 completed. None alone proves availability, including legacy `status` 4/5.
- Positive availability: Plex/Jellyfin record, existing strict boolean `has_file`/`hasFile`, or explicit Seerr media_status 5 (available). Media status 4 is partial: evidence for TV only, not movies or unknown type. A failed request never erases independent positive availability.
- Absent/malformed media status fails closed. Raw nested `media.status` can be consumed for actual-shaped fixtures; flat explicit media_status takes precedence. Never reinterpret ambiguous legacy status as media status.
- Legacy card labels use request_status preferentially, status as fallback: 4 Failed, 5 Completed. No change to request-service APIs.
- Ownership and recency are separate: manager/Seerr-only availability must not enter compact Recently added without Plex/Jellyfin library provenance. Do not invent timestamps; a later matching library record must refresh the compact row even when ID/title/stage stay unchanged.
- Synthetic tests cover all request codes, absent/new/legacy fields, partial movie/TV, true/false file evidence and merged sources; producer tests exercise async_update with mocked Seerr/TMDB transports.

## Compatibility and boundaries
New fields are additive; old cards can consume unchanged rows but retain their own old classification bug. Updated card works with old sensors conservatively; explicit Seerr-only media availability needs a sensor build containing this contract. No numerical minimum released version exists yet; identify paired commits/PRs in verification. UI ready means some TV media exists, not all seasons/episodes or confirmed playback. No real Plex/Seerr/Radarr/Sonarr access.

Enum source: https://github.com/seerr-team/seerr/blob/fc53b3dda37727df6514df8c4bb66eda4b2891e5/server/constants/media.ts (retrieved 2026-11-16).
