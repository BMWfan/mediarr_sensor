# Mediarr card/backend contract v1

`tests/contracts/v1.json` is identical in both repositories. `contract_version` versions the **test document**, not a new required wire field. Existing wire payloads remain compatible. Minimum complete feature pairing: card 0.6.0-dev.7, integration 0.8.0-dev.6. Older backends can still render sensor excerpts; missing commands disable dependent actions with an update message.

Authenticated HA WebSocket commands carry `type` and use HA result/error envelopes. `mediarr/media_details` takes typed `media_type`, optional positive `tmdb_id`, title, year, language and region. Results require positive integer `tmdb_id` and `movie`/`tv`; cast and overview may be absent. `mediarr/search` returns integer `page`/`total_pages` and typed results; malformed types/IDs are discarded. TMDB `show` sensor values normalize to `tv`; request IDs must never substitute for TMDB IDs.

`mediarr/request_capabilities` returns independent movie/tv/immaculaterr/tmdb/tmdb_account `{available, reason}` states. Missing or failed checks never authorize a request. Movie and TV requests use `mediarr.request_movie`/`request_tv` with the exact selected TMDB ID. Successful acknowledgement is not proof of download completion. Existing catalog tests verify HTTP payloads and service rejection.

Playback commands enforce HA entity visibility/control permissions, feature support and actual availability; an unknown command cannot fabricate accepted playback. Existing playback tests cover permissions and errors. TMDB account state is per HA user; app/account tokens remain on the backend and are not included in fixtures or artifacts.

Before changing a contract, update both copies in paired PRs, run producer tests, frontend adapter and real-HA browser tests, document old/missing backend behavior and obtain owner review. Additive unknown fields must remain tolerated. The current shared fixture compares example behavior, not every provider field or full JSON-schema conformance.
