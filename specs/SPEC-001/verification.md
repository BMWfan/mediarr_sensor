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

Result: **passed** — 19 tests ran, 0 failures, 0 errors.

## Scope and formatting

- `git diff --check`: passed.
- Manual review confirmed changes are limited to governance, templates, and
  SPEC-001 records; runtime and workflow files are unchanged.
