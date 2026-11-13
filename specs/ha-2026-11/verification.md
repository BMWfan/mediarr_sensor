# Verification — Home Assistant 2026.11.1

Re-run after Cloud recovery on 2026-11-13. The pre-existing uncommitted changes
were preserved. Exact candidate commits are attached to the PR and GitHub CI
runs; this local run tested the candidate source tree before commit.

## Target and results

- Official multi-platform image: `ghcr.io/home-assistant/home-assistant@sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82`.
- Actual running Core: **2026.11.1**; frontend: **20261028.5**.
- Node **24.19.0**, Playwright **1.58.2**, system Chromium **154.0.8037.57**.
  CI installs the Chromium revision selected by the locked Playwright instead;
  it records the actual browser version rather than assuming equivalence.
- Backend: **60 tests, OK, exit 0** using the pinned image and
  `python scripts/test-ha.py`. The first direct-script attempt failed seven
  imports because the repository was absent from `sys.path`; fixed in the
  runner, then the entire suite passed. No tests were skipped or disabled.
- Card: **29 model/contract tests**, **6 release-policy tests**, and
  **76 browser checks**, full `bash dev/test.sh` exit **0**. Browser breakdown:
  legacy 18, library 14, metadata 4, catalog 8, full library 6, provider setup 3,
  Cinema 13, security 10.
- Authenticated real-HA smoke: **PASS, exit 0** for target Core identity, actual
  Mediarr command registration, unavailable unconfigured providers,
  `tmdb_not_configured`, and serialized initial config-flow schema/cleanup.
- HA `check_config`: **exit 0** (independently captured).
- Workflow YAML parsed; `git diff --check` passed. The tracked card bundle
  changes only its developer build identifier and matches the local test bundle.

## Reproduction

Card checkout:

```sh
export CHROMIUM_PATH=/usr/bin/chromium # omit to install pinned Playwright browser
export HA_DEV_RUNTIME_DIR="$PWD/dev/.runtime-ha-2026-11-1"
export HA_DEV_PORT=8125
bash dev/setup.sh
bash dev/start.sh
bash dev/test.sh
docker compose -p mediarr-card-dev -f dev/compose.yaml exec -T homeassistant \
  python -m homeassistant --script check_config --config /config
```

Sensor checkout:

```sh
docker run --rm --entrypoint python -v "$PWD:/work:ro" -w /work \
  ghcr.io/home-assistant/home-assistant@sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82 \
  scripts/test-ha.py
```

For the optional real-command smoke, install this integration into the
**disposable** HA config, enable `mediarr: {}`, restart that development HA,
refresh its local bootstrap token with `dev/start.sh`, then run
`scripts/smoke-ha.mjs` with `HA_SMOKE_URL=http://127.0.0.1:8125` and
`HA_SMOKE_AUTH_FILE` pointing to the ignored local-auth file. No provider
credentials are needed. Never upload that file or HA storage.

## Evidence, review and limits

CI now preserves exact commit, actual Core/frontend/browser versions and complete
synthetic test output using explicit artifact paths and `pipefail`. Local logs
are in `/tmp/mediarr-resume-audit` and ignored Card runtime result/screenshot
files; these are not portable release proof. PR checks establish that link.

Review found no runtime migration required for the examined HA changes. The only
integration behavior-adjacent change is the official TV/Streaming manifest
category. See `docs/ha-2026-11-impact-review.md` for adopt/defer/reject decisions.
Paired request, playback and data contracts remain unchanged.

Browser provider replies and backend HTTP transports are synthetic; these passes
do not prove production Plex/Seerr/Radarr/Sonarr connectivity, physical playback,
YouTube availability, every older HA version or every config-flow step. Season/
collection mockups and regional Trending setup are not implemented by this PR.

Developer publication/tag verification and owner testing are separate gates.
No stable tag/release is changed and no main merge is authorized by these tests.
