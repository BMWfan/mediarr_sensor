# SPEC-001: Establish SDD-Light agent rules and PR templates

## Objective

Introduce GitHub-native SDD-Light guidance for the Python/Home Assistant backend
without changing runtime code, CI/release workflows, or protection rules.

## Scope

- Document the staged workflow, roles, sizing, test safeguards, compatibility,
  and release approval gates.
- Add GitHub S/M/L issue templates and a PR template.
- Record implementation and verification evidence for this change.

## Non-goals

- Runtime, CI/release workflow, branch protection, or paired card changes.
- Merge, release, prerelease, or deployment.

## Acceptance criteria

- [x] Specify → Clarify → Plan → Tasks → Analyze → Implement → Verify → AI
  Review → owner-approved Merge is documented.
- [x] S/M/L scope and required M/L records are documented.
- [x] Release approval policy from draft PR #18 is preserved and prereleases
  require explicit user approval.
- [x] Safe fixtures, credential handling, pinned HA/Python tests, and
  mediarr-card compatibility guidance are documented.
- [x] Actual verification evidence is recorded in `verification.md`.
- [x] No runtime or workflow files are changed.
