# Verification — library provenance

## Current status
Implementation and relevant synthetic tests pass. Reviewed source commit: `a7b97f43fe402582896584a6c1d362978789168f`. Paired source commits: card `5e8230ce96a36967b33cf7f9283143772c580488`, sensor `a7b97f43fe402582896584a6c1d362978789168f`. No live incident resolution claimed; Draft PR creation is blocked by API network access.

## Provenance and measurements
Issue: https://github.com/BMWfan/mediarr-card/issues/44 including SPEC-046 pilot handoff. Task/thread: 6afa79ad-6e6c-8191-9a49-2bd60c9cc069. Environment: ccarenv_b64_Y2NhcmVudl9kYmRjOWNmN2E5NmM4MTkxYjAwNGFmZjBhNTQzOGNhNA. Installed CLI previously observed 0.167.0-alpha.4; coordinator version not independently established. Start timestamp 2026-11-16 04:10:42 UTC (clock tool, after initial lookup). Card baseline d94fbb62d3d359fac73790285188385f5b66436b; sensor baseline ab78fe791a05d2d8ed3f03d130249c587446272d. Use branches, not main writes.

Actual input/output/cached tokens: UNMEASURED; no platform usage counters exposed. Single optimized pilot, not A/B evidence. Do not substitute word counts or estimates. Tool calls/runtime/rework will be recorded at a defined checkpoint.

## Access observations and rework
GitHub GraphQL issue read returned Forbidden; existing HTTPS Git reads and public issue HTML succeeded. Parsed actual issue body/pilot comment. No credentials inspected or printed. One local source lookup used the wrong repo path and was corrected; missing specs directories were investigated rather than treated as passing discovery. Some initially combined outputs were truncated; relevant regions were narrowed before implementation. No production calls.

## Commands/results — actual synthetic runs

Card repository:
- `node --test tests/seerr-provenance.test.mjs` before the correction: exit 1, six failing tests, including actual ready versus expected waiting for legacy request4 and Available versus Failed label.
- Same command after correction: exit 0, six passed. Added EN/DE label assertions during review; repeated focused run: exit 0, six passed in 115.035183ms.
- `node --test tests/*.test.mjs`: exit 0, 35 passed, 0 failed/cancelled/skipped (258.268339ms in the captured pre-browser model run).
- `CHROMIUM_PATH=/usr/bin/chromium bash dev/setup.sh`: exit 0; temporary development build and locked Playwright installation, pinned HA image already present.
- `bash dev/start.sh` followed by `CHROMIUM_PATH=/usr/bin/chromium node tests/e2e/provider-config.mjs`: exit 0; authenticated HA API/RUNNING/sensor fixture PASS, five provider checks PASS. New actual-HA UI assertions classify failed/completed requests and partial movies as waiting; explicit available media, partial TV and real boolean file evidence as ready. Legacy detail labels show Failed/Completed with explicit request_status precedence and old-row fallback.
- `CHROMIUM_PATH=/usr/bin/chromium bash dev/test.sh`: completed log reports 6 Python release tests OK; 35 model tests passed, no failed/cancelled/skipped; browser suites: legacy 18, library 14, metadata 4, catalog 8, full-library 6, provider configuration 5, cinema 13, legacy security 10 — all PASS (78 browser checks). No assertion/stack-trace failure in this final complete log.
- `bash scripts/build-single-file.sh`, `node --check mediarr-card.js`, `git diff --exit-code -- mediarr-card.js` after source commit, and `cmp mediarr-card.js dev/.runtime/config/www/mediarr-card.js`: exit 0. Required by existing validate.yml bundle consistency gate; artifact generation is intentional, not a release. Exactly the tested development bundle is committed. All tracked JS/MJS `node --check` and `git diff --check`: exit 0.

Sensor repository:
- `docker run --rm --entrypoint python -v "$PWD:/work:ro" -w /work ghcr.io/home-assistant/home-assistant@sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82 -m unittest discover -s tests -p test_seer_status.py -v` before correction: exit 1; four subtest errors, each `KeyError: 'request_status'` (1 test method, 0.007s). This is expected red proof of the missing additive contract, not an environment failure.
- `docker run --rm --entrypoint python -v "$PWD:/work:ro" -w /work ghcr.io/home-assistant/home-assistant@sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82 scripts/test-ha.py` after correction: full log reports `Verified Home Assistant 2026.11.1; frontend 20261028.5`, 61 tests in 0.170s, OK. New async_update regression mocks Seerr request transport and TMDB details/images; asserts legacy status, independent media_status including missing/null case, request and TMDB IDs, media type, existing request/release dates, and no invented has_file field.

Full-run logs are local temporary artifacts: `/tmp/issue44-card-suite.log`, `/tmp/issue44-sensor-green.log`. Both completed before Resume; shell session handles were then unavailable. Their saved complete runner outcomes establish executed/completed tests; do not claim the unavailable process exit statuses were re-polled. Focused checks and post-commit syntax/bundle checks above have directly returned exit 0.

## AI review and compatibility

Reviewed the production diff: three additive producer lines; card availability predicate, request labels and EN/DE Completed labels; generated bundle matches source. Parameter/service/ID/date behavior stays intact. New request_status takes priority for labels, legacy status falls back; neither grants ownership. Media status comparison accepts only exact enum numbers/strings 4/5; other values fail closed. Explicit non-null flat media_status takes priority over nested media.status. Watched state still requires library evidence. Failed requests with independent positive library/file evidence remain ready. No invented import timestamps, new backend services or version/release claims. New fields are a draft capability, not an already released minimum version. Legacy old cards still need the consumer correction to fix their own classifier. No live Plex/Seerr/Radarr/Sonarr/TMDB call; synthetic fixtures and mocked browser request/playback services do not prove real playback or fix the owner's #41 incident.

## SPEC-046 pilot measurement (single optimized run, no baseline)

| Scope | Actual input tokens | Actual output tokens | Cached subset | Tools | Duration | Quality/rework |
| --- | --- | --- | --- | --- | --- | --- |
| Whole implementation pilot | UNMEASURED | UNMEASURED | UNMEASURED | Whole-run total unavailable; partial measured window below | 04:10:42 to 10:00:56 UTC checkpoint, 5h50m14s wall time including user/Resume pause; not active work time | Final suites pass; expected red regressions and access/discovery retries retained |
| Instrumented post-resume review window | UNMEASURED | UNMEASURED | UNMEASURED | 6 functions.exec orchestrations; separately 8 exec_command, 1 clock, 1 environment_status and 1 asynchronous clarification call; 0 subprocess polls in this window | Ends 2026-11-16 10:00:56 UTC; excludes this documentation write and later push/PR operations | Bundle/source review, German label assertions, syntax and bundle-consistency checks |

Instrumentation starts with the post-resume bundle/focused-check orchestration; earlier tool history is not a complete machine-exported counter. Counts are actual calls in that bounded window, **not** a fabricated full-task total, and orchestration wrappers are reported separately from nested calls to avoid double-counting. No platform input/output/cache usage counters exposed; no character estimate substituted. Initial implementation-to-final-suite-log checkpoint: 04:10:42 to saved log mtime 04:17:46 UTC, about 7m04s; this excludes later review/docs/PR preparation and is not an end-to-end task-cost claim. Resume clock: 09:55:51 UTC. User pause is included only in the wall-clock measure. Model config unavailable as trustworthy usage metadata; installed CLI is not model usage evidence.

Rework: expected regression failures first; one wrong-repository lookup and initial too-wide/truncated reads narrowed; GitHub API Forbidden; unavailable process handles on Resume checked against preserved logs instead of blindly rerunning suites; German label assertions added during review; generated bundle intentionally refreshed for existing CI. No changed-source test failures remain. Artifact maintenance and GitHub access retries are not excluded from future total-token accounting; actual cost remains UNMEASURED here. This pilot is not matched A/B evidence and demonstrates no savings percentage.

## Draft PR access / handoff

Runtime status confirms enforced restricted networking, no custom hosts, and `api.github.com` absent from effective allowed hosts. `gh api repos/BMWfan/mediarr-card --jq .permissions` returns `Forbidden`; Git fetch/push use the existing authorized HTTPS Git proxy and are a separate capability. A clarification asks for API network access or user-created drafts; no settings or credentials changed. Review bodies are prepared separately; record actual creation results below. No additional paid call or credential extraction is an alternative.


## Gaps
No production membership/playback verification. No merge/release. Draft PR creation depends on actual GitHub API capability; Git transport success alone is not proof of API permission.


## Final recency review and Draft creation attempts

After the initial successful suites, final issue-scope review found that compact Recently added previously included every ready entry, including manager/Seerr-only ownership with no library provenance. Added a real-HA regression before fixing it. First post-Resume attempt timed out waiting for the card after the long pause (stale local test authentication); reran `bash dev/start.sh` to refresh local-only tokens, without printing them. The retried regression then failed for the intended reason: **3 actual compact posters versus 0 expected**, not an API/setup error. Fixed recent-row selection to require Plex/Jellyfin source references independently of ready status, and added that provenance boolean to the refresh signature. No date is created or rewritten. The browser also verifies that a later matching Plex row refreshes an unchanged ready/ID/title entry.

Final card source commit: `5e8230ce96a36967b33cf7f9283143772c580488`; initial request/media correction `706d4b7` remains in history. Producer code is unchanged at `a7b97f43fe402582896584a6c1d362978789168f`; later producer commits change only documentation.

Actual final commands/results:
- Rebuilt development runtime with `CHROMIUM_PATH=/usr/bin/chromium bash dev/setup.sh`: exit 0.
- `CHROMIUM_PATH=/usr/bin/chromium node tests/e2e/provider-config.mjs`: exit 0; six checks PASS including recent-arrival provenance and later Plex refresh.
- Repeated `CHROMIUM_PATH=/usr/bin/chromium bash dev/test.sh` because compact source logic changed: directly observed exit **0**, also persisted in `/tmp/issue44-final-card-suite.exit`; 6 release tests OK, 35 model tests passed (0 failed/cancelled/skipped) and **79 browser checks PASS** (18 legacy +14 library +4 metadata +8 catalog +6 full-library +6 provider configuration +13 cinema +10 security).
- Post-commit bundle regeneration, syntax check, clean bundle diff and byte comparison with tested development bundle: exit 0. No application changes followed this final run.

The extra recency fix, stale-auth timeout/refresh and repeated affected suite are actual rework after the earlier measurement checkpoint; they are not hidden from the pilot record. Total token usage remains UNMEASURED. Backend did not need a second run for documentation-only updates; its 61-test OK result above still covers unchanged producer code. No CI workflow changed and no release/version bump occurred.

Both branches were pushed successfully. Actual commands attempted once each with the prepared descriptions:
```sh
gh pr create --repo BMWfan/mediarr-card --base main --head fix/44-seerr-request-status --draft --title 'fix(seerr): distinguish requests from available media (#44)' --body-file /tmp/issue44-card-pr.md
gh pr create --repo BMWfan/mediarr_sensor --base main --head fix/44-seerr-status-contract --draft --title 'fix(seerr): expose distinct request and media status fields' --body-file /tmp/issue44-sensor-pr.md
```
Each returned **exit 1**, `Post "https://api.github.com/graphql": Forbidden`. No Draft PR ID/URL was returned; **no PR creation is claimed**. Current API/domain constraint remains the external blocker. Persistent, reviewable [pr-description.md](pr-description.md) contains the intended body; after API access is available, use that tracked file with the same `--draft` commands (never create duplicate drafts if another task/user has already created them).

Branch comparison pages (these are not existing PRs):
- https://github.com/BMWfan/mediarr-card/compare/main...fix/44-seerr-request-status
- https://github.com/BMWfan/mediarr_sensor/compare/main...fix/44-seerr-status-contract

No merge, release, production access, credential extraction or network policy change. The asynchronous question about allowing api.github.com or user-created drafts remains unanswered at this checkpoint; elapsed time is not permission.
