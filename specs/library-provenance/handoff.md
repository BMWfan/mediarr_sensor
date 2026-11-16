# Issue #44 pilot handoff

- Objective: separate Seerr request state from actual availability; [spec](spec.md), [plan](plan.md), [tasks](tasks.md).
- Checked source: mediarr_sensor `a7b97f43fe402582896584a6c1d362978789168f`. Branch: fix/44-seerr-status-contract; base main.
- Paired source: card `41de88e`, sensor `a7b97f4`. Sensor adds request_status/media_status and preserves legacy status. Card never derives ownership from request status; media5 or independent library/file evidence is positive; media4 counts for TV only.
- Verified: 61 pinned-HA backend tests; 36 card model, 6 release and 79 real-HA browser checks pass. Status and malformed-input regressions were red before correction and green after. [Actual evidence/measurement](verification.md).
- Limits: no production playback/membership proof, no claimed fix for the unobserved #41 incident. Old card classifier still needs updating; no released minimum version yet. Tokens remain UNMEASURED; no A/B savings claim.
- Drafts: [card #48](https://github.com/BMWfan/mediarr-card/pull/48), [sensor #33](https://github.com/BMWfan/mediarr_sensor/pull/33); both verified Draft. The historical PR-creation blocker is resolved by owner-created drafts.
- Next: keep Draft; review current CI/evidence before any owner decision. API remains blocked, but public Actions run pages expose status and exact tested commit. No merge/release/production access.
