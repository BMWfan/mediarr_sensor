# Mediarr card/backend contract v1

`tests/contracts/v1.json` is identical in both repositories. `contract_version` versions the **test document**, not a new required wire field. Existing wire payloads remain compatible. Minimum complete feature pairing: card 0.6.0-dev.7, integration 0.8.0-dev.6. Older backends can still render sensor excerpts; missing commands disable dependent actions with an update message.

Authenticated HA WebSocket commands carry `type` and use HA result/error envelopes. `mediarr/media_details` takes typed `media_type`, optional positive `tmdb_id`, title, year, language and region. Results require positive integer `tmdb_id` and `movie`/`tv`; cast and overview may be absent. `mediarr/search` returns integer `page`/`total_pages` and typed results; malformed types/IDs are discarded. TMDB `show` sensor values normalize to `tv`; request IDs must never substitute for TMDB IDs.

`mediarr/request_capabilities` returns independent movie/tv/immaculaterr/tmdb/tmdb_account `{available, reason}` states. Missing or failed checks never authorize a request. Movie and TV requests use `mediarr.request_movie`/`request_tv` with the exact selected TMDB ID. Successful acknowledgement is not proof of download completion. Existing catalog tests verify HTTP payloads and service rejection.

Playback commands enforce HA entity visibility/control permissions, feature support and actual availability; an unknown command cannot fabricate accepted playback. Existing playback tests cover permissions and errors. TMDB account state is per HA user; app/account tokens remain on the backend and are not included in fixtures or artifacts.

Before changing a contract, update both copies in paired PRs, run producer tests, frontend adapter and real-HA browser tests, document old/missing backend behavior and obtain owner review. Additive unknown fields must remain tolerated. The current shared fixture compares example behavior, not every provider field or full JSON-schema conformance.


## Additive Seerr request-row status contract (Issue #44)

`status` remains the legacy **request** status. New `request_status` repeats that
value; new `media_status` carries `request.media.status` or null when absent.
Request 4 means FAILED, request 5 means COMPLETED; neither proves ownership.
Media 5 means AVAILABLE; media 4 means PARTIALLY_AVAILABLE (TV evidence only,
not movie availability). Plex/Jellyfin records and strict boolean file flags
remain independent positive evidence. Missing media fields on old producers are
handled conservatively; do not reinterpret legacy status as media status.

There is no new released version minimum yet: the paired draft builds implement
this additive contract. Old cards retain their existing status interpretation;
new cards work with old sensor rows but cannot infer Seerr-only availability from
request status. TV partial availability is not full-series completeness or a
playback guarantee. Existing request dates are not library import timestamps.

See [producer specification](../specs/library-provenance/spec.md).
