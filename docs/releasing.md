# Releasing

Merging a pull request or changing `custom_components/mediarr/manifest.json` does
not authorize a release. The release workflow is manual and has no `push` trigger.

Before enabling it, a repository administrator must:

1. Set the repository Actions variable `RELEASE_APPROVER` to the owner's GitHub
   login.
2. Configure the `release` environment with required owner approval/reviewers and
   prevent self-review where supported.
3. Preserve the active `main – PR und Tests` ruleset.

To publish, the owner must dispatch **Release On Main** from `main`, select the
explicit `yes` confirmation, and approve the `release` environment deployment.
The workflow refuses other branches, actors, or versions with an existing tag. A
version containing a prerelease suffix is published as a prerelease. Do not dispatch
the workflow as part of implementation or verification.
