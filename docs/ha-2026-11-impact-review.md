# Home Assistant 2026.11: Mediarr impact review

Reviewed 2026-11-09; revalidated 2026-11-13 against project code, not just feed titles. Target: **Core 2026.11.1**, the latest stable observed at review time. Pinned official multi-platform image: `sha256:6785d1eca68747a524c156faae1b139ed415c07357386ae6fe17291986e59e82`. Local image label and authenticated `get_config` both confirm 2026.11.1. Previous test baseline was 2026.10.4; it was not proof of 2026.11 compatibility.

## Concrete decisions

| Change | Decision / priority | Code evidence, benefit and risk |
| --- | --- | --- |
| 2026.11.1 Core and frontend 20261028.5 | Adopt test baseline / P0 | Pin Card `dev/compose.yaml` and backend metadata CI to the verified digest. Run existing browser/transport/model tests and actual HA command/config-flow smoke. No speculative runtime migration. |
| Integration categories | Adopt metadata / P2 | Add `media_entertainment.tv_streaming` to the sensor manifest. This is the exact category used by Plex, Jellyfin and Radarr at core tag 2026.11.1; improves catalog discovery without adding UI. Runtime/API and minimum advertised HA remain unchanged. Actual target-HA loader/config-flow start is tested. |
| Removed `ha-md-list`, `ha-formfield`, Material chip/typography properties | No migration needed / P0 check | Full source search found none of the removed components/properties in our Card modules. Its media controls use native DOM buttons; do not rewrite them into unrelated HA internals. Real target-version browser rendering still needs PASS, not just this search. |
| Theme panel background variables | Defer optional theme-following mode / P2 | Our full-page media surface is a card/overlay, not a registered custom HA panel. Cinematic poster/background styling is intentional. A future option may use `--ha-panel-background` with older-theme fallback; blindly removing its background would change the approved design. |
| Always provide flow `step_id` | Already compliant / P1 | AST review of `config_flow.py` finds no calls to the four affected form/menu/progress/external-step methods without `step_id`. Actual initial flow schema is exercised against HA. Deprecation removal is 2027.5; no missing-ID workaround is needed. |
| Config-entry functions returning None | Retain supported custom-integration behavior / P1 | `__init__.py` returns bool for setup/unload. Official guidance explicitly keeps bool supported for custom integrations without deprecation. Core-only migration rules must not be blindly imposed on this custom integration. |
| Automatic dashboard section strategies | Defer implementation; recommend next / P1 | Card already exposes `getStubConfig` and `getConfigElement`; it registers no `customStrategies`. A separate opt-in section strategy can generate a grid containing the existing compact card or configured full-page card. Benefit: adding Mediarr through HA's section editor with preview. No extra sidebar/menu. Needs entity autodiscovery, duplicate-registration protection, preview/editor tests and an old-HA fallback. Not included silently in this release. |
| Conditional form visibility | Defer / P2 | Backend provider setup lives in `config_flow.py` and uses voluptuous schemas. Conditional fields could hide advanced/provider-only options. New API requires correct field marker/schema handling and tests for retained saved options: hidden fields are not saved. Do not risk wiping stored credentials or raising the minimum HA version for a cosmetic change. |
| Config-entry-scoped Repairs and refresh | Defer / P2 | Mediarr currently has no issue-registry implementation; readiness APIs already expose transient Seerr/manager failure to the Card. Persistent credential/configuration errors could use entry-linked Repairs later. Requires entry-scoped IDs, recovery/removal tests, old-HA compatibility and suppression of flapping/offline noise. Config-subentry linking is 2026.12, not 2026.11. |
| New entity lifecycle hooks | Defer explicit opt-in / P2 | Jellyfin's entity implements add/remove hooks. New rename-in-place behavior must not skip cleanup/subscriptions. Compatibility fallback remains until 2027.11. Plan rename/subscription regression tests before implementing `async_entity_id_changed`; no current-version break is inferred. |
| DeviceInfo dataclass | Not currently applicable / P2 watch | No Mediarr `DeviceInfo`, `_attr_device_info` or `device_info` manipulation was found. Avoid changing ordinary provider dictionaries as if they were HA DeviceInfo instances. Reassess when proper device modeling is introduced. |
| Undefined helper changes | Defer: future version | No `UNDEFINED`/`UndefinedType` use in Mediarr. Official announcement targets 2026.12, so it does not justify requiring a new helper on older supported HA. |
| Child devices | Reject for current scope | Our virtual media/provider sensors do not model physical subparts of one hardware product. Using child devices for films, series or separate servers would misrepresent the device model. |
| Camera audio, backup naming, scanner devices, button events, app Linux capabilities, auth-provider MFA | Not applicable | Mediarr does not implement camera/backup/scanner/event platforms, an add-on/app container or an HA auth provider. Existing HA-authenticated WebSocket/control permissions remain mandatory. No new feature work here. |
| Python console / contributor-site relocation | Development/source maintenance only | Useful for debugging and locating authoritative documentation; not a user-facing media feature. No production console or debug credentials are enabled. |

## Sources and traceability

Official Core release: https://github.com/home-assistant/core/releases/tag/2026.11.1 . The patch notes explicitly bump frontend to 20261028.5; the remaining listed platform-specific fixes do not require a Mediarr runtime change from this code review. This is not a guarantee for every external media server/version.

The feed linked articles could not be fetched reliably at their public permalinks during review, so the actual official source Markdown was read from the contributor repository. Immutable source references:

- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-28-frontend-component-updates-2026.11.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-28-custom-section-strategies-in-the-dashboard-editor.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-21-form-fields-visible.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-28-issue-registry-refresh.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-23-config-entry-methods-return-none.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-23-flow-results-require-step-id.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-12-new-entity-lifecycle-hooks.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-13-device-info-class.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-20-integration-categories.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-10-22-child-devices.md
- https://github.com/home-assistant/contributors.home-assistant.io/blob/f52d9a349a9348046ae27de975d86bc5f87b2283/src/content/blog/2026-11-01-undefined-helper.md

Category reference: https://github.com/home-assistant/core/blob/2026.11.1/homeassistant/components/plex/manifest.json (also Jellyfin and Radarr). Announcements dated after 2026-11-09 are not treated as currently shipped requirements.

## Test meaning and limits

See the paired compatibility specification verification for actual commands and results. Browser tests use real HA rendering but mock catalog/provider replies and media requests. Backend tests use synthetic HTTP transports. The extra smoke uses the real HA command registry, authenticated connection, disabled unconfigured capabilities, missing-TMDB error and actual config-flow serialization with no provider credentials. These do not prove production Plex/Seerr/TMDB account behavior, every config-flow step or every older HA version.

Monitor `report.json` items are observations, not completed decisions: their default `defer`/unknown risk is not this assessment. This document is the human/code-specific assessment. Deduplicating an observation must not be mistaken for validating it. Optional deferred features remain proposals, not claimed as implemented.

## Reproducibility audit (2026-11-13)

GitHub main and the last published developer tags were re-read after restoring
the Cloud executor. Earlier main CI runs are green, but still use the older
2026.10.4 image; they do not establish this 2026.11.1 candidate's compatibility.
The saved Cloud setup instructions also still described the initial seven-test
environment and older checkout refs. Repository scripts and the candidate CI,
not those stale instructions, are the verification source for this change.

The restored direct backend runner initially failed to import seven test modules
because Python placed `scripts/` rather than the repository root on `sys.path`.
The runner now inserts the checkout root before discovery. This was an actual
verification defect, not evidence that the previous 60-test unittest invocation
failed. Candidate CI retains exact commit/version/test output, preserving the
runner's exit status through `pipefail`. No authentication/storage is uploaded.

The proposed regional Trending setup and the generated season/collection design
images are not implemented by this compatibility change and are not covered by
its passing regressions. The images are design mockups, not implementation proof.
