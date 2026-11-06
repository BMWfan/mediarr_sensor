# SDD-Light constitution

## Purpose and roles

Use GitHub issues, branches, and draft PRs as the source of truth for changes
to the Python/Home Assistant backend. ChatGPT coordinates and reviews; Copilot
implements on isolated branches and submits draft PRs. The repository owner
alone approves merges and releases.

## Required sequence

1. **Specify:** describe the problem, scope, and acceptance criteria in an issue.
2. **Clarify:** resolve ambiguities and record constraints and non-goals.
3. **Plan:** choose S/M/L and outline the approach.
4. **Tasks:** break the approved plan into verifiable work.
5. **Analyze:** check compatibility, security, risks, and test coverage.
6. **Implement:** make the smallest complete change on an isolated branch.
7. **Verify:** run relevant tests and record actual commands and results.
8. **AI Review:** review the diff for correctness, regressions, and secrets.
9. **Owner-approved Merge:** merge only with explicit owner approval.

Do not advance past an unresolved decision or represent unrun checks as passing.

## Change sizes and records

- **S:** GitHub issue and PR with regression proof; no additional documents.
- **M:** add `spec.md`, `plan.md`, `tasks.md`, and `verification.md` for the
  change.
- **L:** include all M records plus `research.md`, `contracts.md`, `risks.md`,
  `migration.md`, and `rollback.md`.

Keep records together under a change-specific directory, such as
`specs/<id>/`. State assumptions and non-goals in the specification; make tasks
and verification traceable to acceptance criteria.

## Backend safeguards

- Use the exact pinned Home Assistant test image and Python test command in
  `.github/workflows/metadata-tests.yml`; do not add or change CI/release
  workflows or protection rules as part of this SDD-Light setup.
- Use synthetic fixtures and mocked transports. Never put real credentials,
  account tokens, personal data, HA `.storage` contents, or runtime artifacts
  in tests, commits, logs, screenshots, or PR evidence.
- Preserve existing mediarr-card compatibility. Keep existing sensor fields,
  services, and response shapes functional; document and test any intentional
  contract change and coordinate paired card changes.
- Preserve the release policy in the root `AGENTS.md`: prereleases require
  explicit user approval, and merge/stable release each require separate
  explicit approval. Do not deploy.
