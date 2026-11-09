# Verification and review

2026-11-09, synthetic local checks:

- Identical contract fixture bytes verified with `cmp` across both checkouts.
- Card: `node --test tests/*.test.mjs`: 29 passed; release-policy suite: 6 passed.
- Card: `CHROMIUM_PATH=/usr/bin/chromium bash dev/test.sh`: PASS in real local Home Assistant with synthetic fixtures, including existing old-backend, permissions, readiness and timeout coverage. The new adapter tests were separately executed and are now also included in this command.
- Backend: pinned HA image command from AGENTS.md, `python -m unittest discover -s tests -v`: 60 passed, including 3 new producer contract tests.
- `npm audit --prefix dev --package-lock-only --audit-level=low`: no known vulnerabilities.
- `pip-audit==2.10.1` against manifest requirements: no known vulnerabilities in resolver-selected versions (local Python 3.12; CI also resolves under Python 3.13). This does not audit every HA pin in deployed systems.
- Gitleaks 8.24.3 current tracked tree: no findings. Local release binary checked against official release checksums; CI builds exact tool version with pinned Go.
- Backend narrow false-positive exception tested against the exact empty schema expression and a generated credential inserted into that expression; only the credential is detected, with values suppressed.
- All tracked JavaScript syntax and Python AST checks passed; `git diff --check` passed.

Review: no runtime module, manifest, package version, release workflow or stable tag changed. All new CI permissions are read-only, jobs have timeouts, advisories are not ignored. Secret scan is current-tree only; historical scanning is not claimed. Tests exercise actual frontend adapters and backend WebSocket handler/result/error envelopes but do not substitute for authenticated real-provider testing. Shared examples document a v1 contract rather than adding a mandatory wire version.

Recommendation: approve with the stated scanner and fixture scope limits after CI is green. Owner merge/release approval remains required. Existing developer releases contain unchanged runtime code; this PR publishes no new prerelease. Monitoring adoption is tracked separately and still depends on the shared workflow.
