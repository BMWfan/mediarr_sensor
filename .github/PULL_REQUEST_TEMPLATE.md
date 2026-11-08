## SDD-Light

**Issue:** #
**Size:** S / M / L

### Workflow

- [ ] Specify and acceptance criteria are linked to the issue.
- [ ] Clarify decisions and non-goals are recorded.
- [ ] Plan, tasks, and analysis are complete.
- [ ] Verification lists commands actually run and their results.
- [ ] AI review is complete; this PR remains a draft until owner review.
- [ ] Merge is pending explicit owner approval.

### Evidence and safeguards

- [ ] Regression proof covers the acceptance criteria.
- [ ] Tests use synthetic fixtures/mocks; no credentials or HA runtime artifacts are included.
- [ ] Existing mediarr-card behavior and contracts remain compatible, or paired changes are documented.
- [ ] M: `spec.md`, `plan.md`, `tasks.md`, and `verification.md` are included under `specs/<id>/`.
- [ ] L: `research.md`, `contracts.md`, `risks.md`, `migration.md`, and `rollback.md` are also included under `specs/<id>/`.
- [ ] No runtime, CI, release workflow, or protection-rule changes outside the approved scope.

**Test commands and actual results:**
