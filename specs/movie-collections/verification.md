# Verification: movie collections

Local final source tests on 2026-11-14, actual Home Assistant Core 2026.11.1
and frontend 20261028.5. Synthetic provider/HTTP replies only.

- Backend pinned HA runner: **65 tests, OK, exit 0**. Canonical IDs/membership,
  sorting/deduplication, TV/adult/invalid filtering, collection cache, missing
  membership, wrong movie replies, optional failure and retry recovery covered.
- Card full `bash dev/test.sh`: **31 model/contract tests**, **6 release-policy
  tests**, **78 browser checks**, exit **0**. Cinema suite now has 15 checks.
- Browser scenarios cover desktop/mobile and compact fullscreen overlay, one
  unchanged-position synopsis, individual owned/watched/waiting/missing status,
  keyboard part selection, updated metadata/cast and exact selected movie request
  ID. Selection alone never requests media. Existing guarded playback/request
  behavior and all earlier regressions pass. Collection catalog flags cannot
  forge ownership; movie and TV IDs remain distinct.
- `git diff --check`, generated bundle syntax and byte equality with the local
  HA-served bundle passed. Screenshots inspected; fixture artwork is synthetic
  SVG, not real production movie artwork. Screenshots in the ignored runtime:
  `cinema-collection-desktop.png`, `cinema-collection-mobile.png`,
  `cinema-collection-overlay.png`. Existing CI already retains cinema screenshots.

Review: canonical membership is required; no title guessing or new sidebar/menu.
Only sanitized movie records enrich the existing library model. Real local
provider availability and request state take precedence over TMDB. The rail is
inserted after the existing synopsis; plot is not duplicated. An optional
collection failure retains the selected film and offers explicit retry. Backend
credentials stay server-side and collection IDs are never submitted as movie IDs.
No config migration, production connection test or real media request was made.

Paired candidates: Card **v0.6.0-dev.10**, sensor **v0.8.0-dev.9**. Install the
sensor first/restart HA, then Card/reload frontend. Old cards ignore additional
metadata; old backends retain normal movie details but cannot provide this rail.
Hosted CI/tag verification will be recorded on the PR after push. Main merge
requires owner testing and explicit approval; stable releases remain untouched.
