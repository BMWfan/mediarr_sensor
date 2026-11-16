Seerr sensor rows currently expose request.status through the ambiguous legacy status field. Add request_status and media_status independently so consumers can distinguish failed/completed requests from actual media availability. Preserve all existing fields, IDs, dates and request services; missing media status is null. No request state creates file/ownership evidence.

Companion to [BMWfan/mediarr-card #44](https://github.com/BMWfan/mediarr-card/issues/44). SDD-Light M specification, compatibility contract and actual evidence: [specs/library-provenance](https://github.com/BMWfan/mediarr_sensor/tree/fix/44-seerr-status-contract/specs/library-provenance).

Paired consumer: [BMWfan/mediarr-card fix/44-seerr-request-status](https://github.com/BMWfan/mediarr-card/tree/fix/44-seerr-request-status), source 41de88e. Old cards still require their own classification correction; there is no new released minimum version yet.

Validation: pinned Home Assistant 2026.11.1 / frontend 20261028.5 runner reports all 61 tests OK. New async_update regression uses actual-shaped synthetic Seerr requests with mocked Seerr/TMDB transports and checks additive fields plus unchanged legacy fields and dates. It failed before the producer correction. Paired consumer passes 36 model, 6 release and 79 real-HA browser checks. Logs were preserved across Resume; no unobserved process exit status is claimed.

No production access, live membership/playback claim, CI/release workflow changes, version bump, service/API change, merge or release. SPEC-046 pilot records actual bounded tool counts, pause-inclusive wall time and rework; actual input/output/cache tokens remain UNMEASURED, with no A/B or savings claim. Keep Draft for owner review.

Final recency review also prevents manager/Seerr-only ownership from entering compact Recently added without Plex/Jellyfin provenance, with a red/green real-HA regression and refresh-on-later-Plex evidence. Final card suite directly returned exit 0; no live incident resolution claimed.

Paired Draft PRs: [card #48](https://github.com/BMWfan/mediarr-card/pull/48), [sensor #33](https://github.com/BMWfan/mediarr_sensor/pull/33). Owner-requested review also fixes malformed request-status keys resolving inherited properties; regression and full local card suite pass. Exact-head public CI evidence and review findings are in verification.md.
