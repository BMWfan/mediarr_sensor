# Issue #44 pilot handoff

- Objective: separate Seerr request state from actual availability; [spec](spec.md), [plan](plan.md), [tasks](tasks.md).
- Checked source: mediarr_sensor `a7b97f43fe402582896584a6c1d362978789168f`. Branch: fix/44-seerr-status-contract; base main.
- Paired source: card `706d4b7`, sensor `a7b97f4`. Sensor adds request_status/media_status and preserves legacy status. Card never derives ownership from request status; media5 or independent library/file evidence is positive; media4 counts for TV only.
- Verified: 61 pinned-HA backend tests; 35 card model, 6 release and 78 real-HA browser checks pass. Focused six-case consumer regression was red before correction and is green after. [Actual evidence/measurement](verification.md).
- Limits: no production playback/membership proof, no claimed fix for the unobserved #41 incident. Old card classifier still needs updating; no released minimum version yet. Actual tokens/cache and whole-task tool total UNMEASURED; partial tool counts and pause-inclusive wall time recorded. No controlled A/B savings claim.
- Next: create separate linked Draft PRs when api.github.com is allowed, or use prepared branch comparison links. Keep Draft; no merge/release/production access. Existing GitHub API Forbidden is the remaining access gate, not a failed implementation test.
