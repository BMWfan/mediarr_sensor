# Backend ↔ mediarr-card contract

Contract version: **1.0** (documentation version; not a new wire-protocol field).

This contract describes the card-facing behavior implemented by the Mediarr
integration. It is not a promise that a card release has been tested against every
backend revision. Coordinate changes to these interfaces with the card repository
and test both sides before claiming cross-repository compatibility.

## Authentication and permissions

- The card connects through the authenticated Home Assistant WebSocket and invokes
  the commands below. The backend uses only credentials configured in Mediarr;
  credentials and upstream URLs are not card inputs or response fields.
- These commands rely on Home Assistant's authenticated WebSocket session. The
  current handlers do not implement a separate per-entity or per-command role
  authorization policy; do not describe them as providing one.
- `/api/mediarr/library_image/{source_id}/{rating_key}` requires Home Assistant
  authentication. Plex image URLs are signed by Home Assistant and are temporary.
- Request services are Home Assistant services and use configured Seerr/Jellyseerr
  credentials. The card must not receive or persist those credentials.

## WebSocket commands

### `mediarr/library`

Request fields:

| Field | Type | Default / constraints |
| --- | --- | --- |
| `page` | integer | `1`; valid range 1–10000; 100 rows per page |
| `refresh` | boolean | `false`; bypasses the 30-second snapshot cache |
| `language` | string | `en`; two/three-letter language, optionally `-CC` |

Success response: `groups` (`plex`, `radarr`, `sonarr` arrays), `page`,
`total_pages` (at least 1), `complete`, and `errors`. Items are provider-specific;
optional fields such as IDs, watched state, file state, artwork, and download
progress are not guaranteed for every provider/item. `complete: false` means one or
more sources were unavailable; `errors` contains provider and safe error code only.

### `mediarr/media_details`

Request fields: `media_type` (`movie`, `tv`, or `unknown`, default `unknown`),
optional positive integer `tmdb_id`, `title` (default empty, max 256 characters),
optional integer `year` (1800–2200), `language` (default `en`), and `region`
(default `DE`, two uppercase letters). A title or TMDB ID is required.

Success returns public title metadata, identifiers, cast/directors, and regional
streaming offers. It never returns upstream configuration or credentials.

### `mediarr/search`

Request fields: required `query` (2–128 characters), `language` (default `en`),
and `page` (default 1, range 1–5). Success returns `results`, `page`, and
`total_pages` capped at 5. Results contain movies and TV only; people and adult
results are excluded. Catalog presence is not library availability.

## Errors and client behavior

Application errors sent by the handlers use Home Assistant's `send_error` envelope
with a stable code and credential-free message. Requests rejected by the WebSocket
schema use Home Assistant's standard schema-validation error. Current application
codes include:

| Code | Meaning | Client behavior |
| --- | --- | --- |
| `invalid_format` | Invalid field or request bounds | Correct the request; do not retry unchanged |
| `tmdb_not_configured` | No explicit TMDB credential is configured | Explain setup is required |
| `metadata_auth` | TMDB rejected the configured credential | Explain credential rejection without exposing it |
| `metadata_not_found` | No matching title/metadata was found | Offer another search or selection |
| `metadata_ambiguous` | A title/year did not identify one result | Require an explicit selection |
| `metadata_unavailable` | Upstream metadata is unavailable or invalid | Offer retry; do not infer missing data |
| `plex_not_configured` | No Plex source is configured | Explain setup is required |
| `library_unavailable` | A configured source could not be read | Preserve available data and show partial status |
| `library_incomplete` | A source returned an incomplete page | Do not present the result as complete |

Keep error codes stable. A new field may be added compatibly; removing/renaming a
field, changing its meaning or validation, changing an error's meaning, or altering
the authentication boundary requires a contract revision and coordinated card
change.

## Home Assistant services

The request services in `custom_components/mediarr/services.yaml` are invoked via
Home Assistant, not a separate unauthenticated backend endpoint:

- `submit_movie_request`: `name`, optional positive integer `tmdb_id`.
- `submit_tv_request`: `name`, optional positive integer `tmdb_id`, optional
  `season` (`first`, `latest`, or `all`; default `latest`).
- `update_request`: `name`, `type` (`movie` or `tv`), `new_status`
  (`approve`, `decline`, or `remove`), and optional positive `request_id`.
- `process_immaculaterr_suggestion`: documented in `services.yaml`; availability
  depends on Immaculaterr configuration.

Home Assistant service validation and backend rejection behavior are part of the
observable contract. Keep regression tests for exact identifiers, validation,
credential isolation, and rejected upstream requests.

## Compatibility and validation status

The repository's unit tests cover WebSocket schemas, metadata/search errors, library
pagination, and request rejection using synthetic fixtures. They do not execute the
card or establish an end-to-end cross-repository compatibility guarantee. The
paired card draft `BMWfan/mediarr-card#20` identifies backend draft
`BMWfan/mediarr_sensor#18`; both drafts and their existing release policy must
remain untouched unless the owner explicitly directs otherwise. Validate a claimed
pair against the exact backend/card revisions in isolated fixtures before release.
