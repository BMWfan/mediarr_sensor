# Read-only maintenance monitoring

Tracks issue #23. This non-fork project uses the shared phase-1 action from BMWfan/Home-Assistant-Mail-And-Packages at immutable commit `0b8bc1aa6a2d1254ba39b7c0efd1f521656f3be8`. There is no copied monitor engine and no assumed upstream. Sources and project-specific relevance are explicit in `.github/maintenance-monitor.yml`.

Run **Maintenance monitor (read-only)** from Actions using workflow_dispatch. The development branch runs on push for validation; weekly scheduling starts only after owner-approved merge to the default branch. Permissions are contents:read and actions:read; no extra secrets or production access.

Download `maintenance-report` or read the run summary. JSON includes exact versions/SHAs, official citations, timestamps, project relevance, conservative priority and uncertainty. Findings default to defer/review; package advisory matches do not prove that your installed version is vulnerable. State is observational, never human approval. No local recommendation engine, issues, agent assignments, PRs, merges, releases or HA calls are created by this workflow.

The first run reports a baseline. State artifacts are scoped to repository/ref/config bytes and retained 90 days; reports 30 days. Same snapshots produce no new observations. A failed source or state restore fails the run and does not advance state. Source windows are bounded to 20 release/feed/advisory items, not a full security inventory. Config/ref changes and expired artifacts deliberately rebaseline. Official HA developer news uses the current contributors.home-assistant.io RSS feed.

Disable in GitHub Actions or remove schedule/push triggers. Roll back by reverting the caller config/workflow or pinning the last reviewed shared commit. No runtime restart/migration is needed. GitHub Actions minutes/storage may count against the account allowance. Shared-action access is subject to existing GitHub policy; never add a broad PAT silently.

Core adapter/state/security behavior is covered by the shared source mocked test suite. Local real-source and GitHub workflow_dispatch evidence will be recorded in the specification. Adoption changes no card/backend runtime contract. The consumer's provider set is configuration, not a duplicated implementation.
