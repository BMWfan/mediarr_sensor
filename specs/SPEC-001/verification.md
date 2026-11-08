# Verification

## Tests

Command run using the pinned Home Assistant image from
`.github/workflows/metadata-tests.yml`:

```sh
docker run --rm --entrypoint python \
  -v "$PWD:/work:ro" -w /work \
  ghcr.io/home-assistant/home-assistant@sha256:23f4dfbb69ce76315dbc4de7915504f1c2dcecd7ca2648113a493a385972e133 \
  -m unittest discover -s tests -v
```

Initial governance-baseline result: **passed** — 19 tests ran, 0 failures, 0 errors.

## Scope and formatting

- `git diff --check`: passed.
- Manual review confirmed changes are limited to governance, templates, and
  SPEC-001 records; runtime and workflow files are unchanged.

## Updated review — 2026-11-08

This documentation branch now includes backend PR #18 head
`64b8e433509c3aa562948471c1fc5a8e754c91a7` and is stacked on `feat/cinema-data`.
Its review diff contains only governance/templates/specification records; no
Python, manifest, service schema, sensor field or release-workflow change.

Executed in the running pinned HA 2026.10.4 container:
`python -m unittest discover -s tests -v` — **57 passed, 0 failures/errors**.
`git diff --check` passed. Review confirmed the existing developer-first policy
is retained and user approval is still required before any main merge/stable
release. Existing session authorization for developer prereleases is not removed
by these rules. No production connection, new release or merge to main performed.

Technical review: no unresolved implementation finding in the documentation-only
diff. Ready for owner review; owner merge/release decisions remain pending.

The six release-policy tests and manual-publication workflow are inherited from
the updated PR #18 base, not introduced by this governance review diff.
