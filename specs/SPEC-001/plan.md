# Plan

1. Inspect the main-branch repository, current pinned test command, and draft
   PR #18 release policy.
2. Add root agent rules, a concise SDD-Light constitution, GitHub S/M/L issue
   templates, and a PR template.
3. Keep all changes documentation-only and preserve the existing release
   policy while stating the explicit prerelease approval gate.
4. Run the existing tests in the pinned Home Assistant image, inspect the diff,
   scan changed files for secrets, and review the change with CodeQL.

## Constraints

- Work on the issue branch based on `main`; do not modify PR #18 or paired card
  #20.
- Do not merge, release, prerelease, deploy, or modify runtime, CI/release
  workflows, or protection rules.
