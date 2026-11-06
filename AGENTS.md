# Mediarr development workflow

## Roles and sequence

Use the GitHub-native SDD-Light sequence for every change:

1. **Specify** the observable problem and desired behavior.
2. **Clarify** assumptions, scope, non-goals, and compatibility expectations.
3. **Plan** the approach and verification before implementation.
4. **Task** the work into reviewable steps with clear acceptance criteria.
5. **Analyze** affected Home Assistant behavior, the card contract, security, and release impact.
6. **Implement** only the assigned issue on an isolated branch and draft PR.
7. **Verify** with reproducible commands and report actual results and coverage gaps.
8. **AI review** for correctness and risks; record the recommendation and unresolved risks.
9. **Owner-approved merge** only after the repository owner explicitly approves.

Copilot implements the assigned, isolated issue. ChatGPT coordinates and reviews; it
does not authorize a merge or release. A draft PR is not approval to merge, deploy,
or publish.

## Scope sizing

- **S — focused change:** State the bug or behavior, acceptance criteria, and
  regression evidence. Keep the change local.
- **M — feature or cross-cutting change:** Include a short specification, plan,
  ordered tasks, and verification evidence, in addition to S-level details.
- **L — broad or breaking change:** Also document research, API contracts,
  migration and compatibility, risks, rollout, and rollback.

Choose the smallest size that accounts for the affected behavior and interfaces.

## Repository safety

- Work only in the assigned repository branch and PR. Do not edit unrelated branches,
  repositories, or active feature PRs. In particular, preserve the paired
  `mediarr_sensor#18` / `mediarr-card#20` drafts and their release policy.
- Do not connect to production Home Assistant, real credentials, or live media
  services. Tests must use synthetic fixtures and the isolated, pinned HA test
  image in CI.
- Never copy credentials into tests, logs, issues, or card-facing responses. Keep
  service credentials and API destinations in Home Assistant configuration.
- Update `docs/backend-card-contract.md` and its regression evidence whenever a
  change affects a card-consumed command, response, error, service, or permission
  boundary. Coordinate paired changes with the card repository; do not modify it
  from this repository's task.
- Do not merge, deploy, publish a release, or trigger the release workflow without
  explicit owner approval for that action. A version bump or merge is not release
  authorization.
- Preserve the active `main – PR und Tests` ruleset. Do not weaken branch
  protections or CI requirements.

## Verification and reporting

- Prefer the existing HA-container test command:
  `docker run --rm --network none --entrypoint python -v "$PWD:/work:ro" -w /work ghcr.io/home-assistant/home-assistant@sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133 -m unittest discover -s tests -v`
- Report commands exactly as run, their results, and what was not verified. Do not
  claim cross-repository or live-system validation unless it actually occurred.
- Keep PRs focused. Include the AI review recommendation (approve, approve with
  risks, or reject) and outstanding risks for the owner.
