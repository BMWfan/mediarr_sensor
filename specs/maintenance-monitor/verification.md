# Verification

2026-11-09: Shared suite: 15 mocked cases passed, including non-fork/fork, source and restore failures, bounded retry, credential/redirect safety and persistent deduplication. Scoped repository Ruff lint and format checks passed.

Local official-source report: 7 healthy sources, no failures. Caller workflow_dispatch run https://github.com/BMWfan/mediarr_sensor/actions/runs/42684737347 succeeded. Its downloaded report artifact confirmed 7 healthy sources, **0 duplicate observations**, and no source errors. An earlier sensor run correctly failed closed on the old redirected Plex repository; the config now uses pushingkarmaorg/python-plexapi directly. No history was advanced on that failed run.

Shared source manual run https://github.com/BMWfan/Home-Assistant-Mail-And-Packages/actions/runs/42684172564 also succeeded and restored state. Final source revision `b6a81bf569834956e26db7d6cdc792fc063088e2` removes an unnecessary override-specific lint suppression for compatibility with the source repository's pinned Ruff; behavior is unchanged. Final pinned-revision caller CI is rerun after this commit.

Review: source/action pins are immutable; permissions are contents:read and actions:read; artifacts contain only public observations and state fingerprints. Runtime modules, package/manifest versions and release workflows are unchanged. This is report-only, not an installed-version vulnerability verdict, issue creator or automatic upgrade engine. Schedule runs on the default branch only after merge. Owner-approved merge remains required.
