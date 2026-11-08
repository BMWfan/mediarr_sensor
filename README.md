<p align="center"><img src="custom_components/mediarr/brand/icon.png" width="72" height="72" alt="Mediarr clapperboard icon"></p>

Support This Project If you find this project helpful, please consider supporting it. Your contributions help maintain and improve the project. Any support is greatly appreciated! ❤️ https://buymeacoffee.com/vansmak Thank you for your support!


# Mediarr for Home Assistant (inspired by upcoming media card) https://github.com/Vansmak/mediarr-card

## Changelog

### v0.8.0-dev.5 — Request fixes and connection checks

- Pair with Card 0.6.0-dev.6 and restart Home Assistant after installation.
- `mediarr/request_capabilities` reads Seerr auth and non-sensitive service APIs
  to verify its default Radarr/Sonarr targets, profiles and root folders. It also
  checks configured TMDB and optional Immaculaterr connectivity. Only availability
  and safe reason codes are returned; no URLs, keys, profile names or root paths.
- Checks use bounded timeouts and a shared 10-second cache. They never add test
  media or change manager settings. Card checks repeat every 30 seconds; network
  state may still change between checking and executing a command.
- Fix double-encoded title searches and prevent movie/series cross-type fallback.
  A failed latest-season lookup no longer silently requests season one.
- Developer prerelease only; stable/main remain unchanged.

### v0.8.0-dev.4 — Current playback and pause/resume

- Pair with Card 0.6.0-dev.5; restart HA after installing this integration.
- `mediarr/players` includes current state, title and pause/resume capabilities
  for permitted Plex player entities. The card displays active devices separately.
- `mediarr/playback_control` pauses/resumes a selected authorized, available player
  in the appropriate state, using HA services with the requesting user's context.
  Unsupported, offline and unauthorized targets are rejected. Service failures
  never produce successful command acknowledgements.
- Main/stable remain unchanged until user testing and explicit approval.

### v0.8.0-dev.3 — Explain player availability

- Pair with Card 0.6.0-dev.4. Player status distinguishes disabled, not loaded,
  unknown and unavailable entities. Permission filtering remains enforced.
- Refreshing the card's player list rereads current HA state; it does not wake
  devices or reload integrations. Open Plex on the target and allow remote
  control, then refresh. Enable disabled entities in HA settings when needed.
- This release does not claim to fix server/network/client availability, and
  retains exact server/item playback delegation. Main/stable remain unchanged.

### v0.8.0-dev.2 — Episode progress, trailers and waiting-title artwork

- Pair with Mediarr Card 0.6.0-dev.3; update this integration first and restart HA.
- Read Plex episode state in paged section queries, not per-episode requests.
  Summarize available unplayed regular episodes after the furthest watched or
  partially played position. Ignore old gaps and specials; include later seasons.
  Return compact episode ranges per show, using the configured Plex account.
  Unavailable/incomplete episode queries are explicit and retain the library.
- Metadata includes an official YouTube trailer, preferring the user's language
  with English fallback. Only validated video IDs become external links.
- Manager snapshots now include public CDN poster/fanart URLs. Manager credentials
  and private image URLs never reach the browser; queries are stripped.
- Developer prerelease only; main/stable remain unchanged pending approval.

### v0.8.0-dev.1 — Cinema developer backend

- Pair with Mediarr Card 0.6.0-dev.1; install via HACS beta versions and restart HA.
- Adds `mediarr/cinema`: trending, upcoming movie/TV releases and TMDB's native
  per-account recommendations. No locally trained or scored recommendation engine.
- Adds `mediarr/tmdb_account`: status/start/finish/disconnect for the current HA
  user. Add the optional **TMDB API Read Access Token** in the integration's TMDB
  options, keeping the existing API key. Approve the browser link from the card,
  then confirm in the card. Account credentials stay in private HA storage and
  responses never include long-lived tokens. Connections are isolated by HA user.
- Adds `mediarr/collections`: reads existing Plex collections and dynamic smart
  collection membership on demand, without modifying Plex.
- Plex catalog returns added dates, in-progress state and signed backdrop artwork.
  Manager releases distinguish cinema, digital, disc and next-episode dates.
- Adds `mediarr/players` / `mediarr/play`: only permitted HA Plex player entities
  are listed/controlled. Playback delegates an exact server/item URI to HA's
  official Plex integration with the requesting user's context. Open Plex on the
  TV to make its player available; an Android TV entity alone is insufficient.
- Main/stable versions remain unchanged pending explicit approval after testing.

### v0.7.0
- Authenticated `mediarr/search` catalog search with bounded pagination and caching.
- `mediarr/library` loads complete Plex movie/show sections, including watched
  titles, and Radarr/Sonarr managed lists with queue progress. Sources come from
  existing Mediarr configuration; no credentials are sent to the card.
- Plex artwork uses authenticated, temporary signed Home Assistant image URLs.
- Discovery remains supplied by existing integrations, without a new
  recommendation engine or imitation of Netflix predictions.
- Regional streaming offers distinguish subscriptions, rentals and purchases.
- Movie/TV request services accept optional `tmdb_id` and propagate rejected
  requests to Home Assistant instead of reporting apparent success.
- Pair with card 0.5.0. Configure Plex, explicit TMDB credentials and optional
  Radarr/Sonarr sources in Mediarr. Seerr remains required for request actions.
- Plex watch history is for the configured token's account. This does not connect
  personal Netflix/Prime accounts, import their exports or authorize a TMDB account.

### v0.6.1
- **Fix:** Immaculaterr — all sensors now share a single API client to prevent simultaneous login attempts on startup
- **Fix:** Immaculaterr — rate-limit backoff: after a 429 login failure, further attempts are blocked for the duration specified by the server instead of retrying every 30 seconds

### v0.6.0
- Immaculaterr Watched Collections: new sensors based on Plex watch history (`recentlyWatched`, `changeOfTaste`)
- New service `mediarr.reset_immaculaterr_rejected` to reset previously rejected suggestions
- Config Flow: Watched Collections configurable via UI
- Fix: Seer Discovery diagnostic logs reduced to DEBUG level (no more ERROR spam)

## Services
This integration provides services to interact with Overseerr/Jellyseerr and Immaculaterr Observatory. While the various trending/discover sensors and frontend card are optional, the related credentials must be configured when you want button actions from Home Assistant.

### Minimum Required Configuration just to have overseer\jellyseer request services from ha
To use the seer request services, add this to your configuration.yaml:

```yaml
mediarr:
  seer:
    url: your_seerr_url
    api_key: !secret seer_api_key
```
and for sensors:
```yaml
sensor:
  - platform: mediarr
    seer:
      url: your_seerr_url
      api_key: your_api_key
```      

To use the Immaculaterr services, add this to your `configuration.yaml`:

```yaml
mediarr:
  immaculaterr:
    url: http://your_immaculaterr_host:5454
    username: your_username
    password: !secret immaculaterr_password
```

**Available Immaculaterr services:**

- `mediarr.process_immaculaterr_suggestion` — Approve, reject, or remove a suggestion:
  ```yaml
  service: mediarr.process_immaculaterr_suggestion
  data:
    library_section_key: "1"
    media_type: movie        # movie or tv
    suggestion_id: 12345
    action: approve          # approve, reject, remove, undo, keep
    apply: true              # Optional: apply immediately (default: true)
  ```

- `mediarr.reset_immaculaterr_rejected` — Reset all previously rejected suggestions so they appear again:
  ```yaml
  service: mediarr.reset_immaculaterr_rejected
  ```

## Installation

### HACS Installation
1. Open HACS
2. Go to "Integrations"
3. Click the three dots menu and select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Add"
6. Find and install "Mediarr" from HACS
7. Restart Home Assistant

Note: this repository is currently intended to be added as a `Custom repository`. It is not part of the default HACS catalog, so it will not appear in the normal HACS search until you add the repository URL manually.

This integration is YAML-based. After installing it with HACS, configure `mediarr:` and/or the `sensor:` platform in `configuration.yaml`; it does not show up through Home Assistant's "Add integration" flow.


### Manual Installation
1. Download the latest  before hacs (can break)
2. Copy all contents from `custom_components/mediarr/` to `/config/custom_components/mediarr/`
   
4. Restart Home Assistant

## Configuration

### Option A: Configure via Home Assistant UI (recommended)
After installing with HACS and restarting Home Assistant:
1. Go to **Settings -> Devices & Services**
2. Click **Add Integration**
3. Search for **Mediarr**
4. Complete the setup flow (Seer / Immaculaterr / TMDB)
5. Use **Configure** on the integration later to update options

This UI flow creates a config entry and removes the need for full YAML sensor setup in most cases.

### Step 1: Configure Sensors
Add one or more of the following sensors to your `configuration.yaml, sensors`:
**Customizable Filters**: Control content discovery with granular options
** have multiple instances for sonarr and radarr (2 each)
```yaml
sensor:
  - platform: mediarr
    seer: 
      url: localhost
      api_key: your_api_key
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      tmdb_api_key: "your_tmdb_api_key" 
      trending: true # Optional     
      discover: true  # Optional
      popular_movies: false  # Optional, recommended to use tmdb for popular
      popular_tv: false # Optional, recommended to use tmdb for popular

    plex:  # Optional
      url: Plex url
      token: your_token
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      tmdb_api_key: "your_tmdb_api_key"
      language: en #default

    jellyfin:  # Optional
      url: jellyfin url
      token: your_api_key 
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      tmdb_api_key: "your_tmdb_api_key"
      language: en #default

    sonarr:  # Optional
      url: http://localhost:8989
      api_key: your_sonarr_api_key
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      days_to_check: 60 #example

    sonarr2:  # Optional
      url: http://localhost:8989
      api_key: your_sonarr_api_key
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      days_to_check: 60  #example

    radarr:  # Optional
      url: http://localhost:7878
      api_key: your_radarr_api_key
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      days_to_check: 60 #breaking change

    radarr2:  # Optional
      url: http://localhost:7878
      api_key: your_radarr_api_key
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
      days_to_check: 60 #breaking change
      
    
    trakt:  # Optional
      client_id: "your_client_id"
      client_secret: "your_client_secret"
      tmdb_api_key: "your_tmdb_api_key"  # Required for posters
      trending_type: both  # Options: movies, shows, both
      max_items: 45  #example how many items you want in sensor, you can chosse a different amount in card
     
    
    tmdb:  # Optional
      tmdb_api_key: "!secret tmdb_api_key"  #may need quotes
      trending_type: all  # Options: movie, tv, all
      max_items: 45  #example how many items you want in sensor, you can choose a different amount in card
      trending: true          # Default endpoint
      now_playing: true       # Optional
      upcoming: true          # Optional
      on_air: true            # Optional
      airing_today: false     # Optional
      popular_movies: true
      popular_tv: true
      filters:
        min_year: 2020  # Only show content from 2020 onwards
        exclude_talk_shows: true
        exclude_genres: [10763, 10764, 10767]

    immaculaterr:  # Optional
      url: http://your_immaculaterr_host:5454
      username: your_username
      password: !secret immaculaterr_password
      max_items: 45
      mode: review                    # Optional: review or pendingApproval
      tmdb_api_key: "your_tmdb_api_key"  # Optional, used for overview/backdrop enrichment
      movie_library_section_key: "1"  # Optional
      tv_library_section_key: "2"     # Optional
      # Watched collections (requires Immaculaterr v1.7.6+):
      enable_watched_collection: false         # Optional: creates additional sensors based on watch history
      watched_collection_kind: recentlyWatched # Optional: recentlyWatched or changeOfTaste
```
# Sensor Configuration
- **max_items**: Number of items to display (default: 45)
- **days_to_check**: Days to look ahead for upcoming content (Sonarr only, default: 90)
- **trending_type**: Content type to display for Trakt and TMDB
- **mode**: For Immaculaterr Observatory sensors, use `review` for the suggestion feed or `pendingApproval` for approval queues
- **enable_watched_collection**: Creates additional sensors based on Plex watch history (requires Immaculaterr v1.7.6+)
- **watched_collection_kind**: `recentlyWatched` recommends based on recently watched titles; `changeOfTaste` recommends from different genres than usual
- Available Filters

- hide_existing: Toggle library content filtering (default: true)
- min_year: Minimum release year for content
- exclude_talk_shows: Remove talk shows and similar content
- exclude_non_english: Show only English content
- exclude_genres: List of genre IDs to filter out

Common Genre IDs to Exclude

10763: News
10764: Reality
10767: Talk Shows
35: Comedy (if you want to filter out comedy)
99: Documentary (if you prefer scripted content)
  
### Step 3: if you want a front-end, install Mediarr-card from https://github.com/Vansmak/mediarr-card
Add the Card

## Getting API Keys

### Plex
1. Get your Plex token from your Plex account settings
2. More details at [Plex Support](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)

### Sonarr/Radarr
1. Go to Settings -> General
2. Copy your API key

### Trakt
1. Create an application at [Trakt API](https://trakt.tv/oauth/applications)
2. Get your client ID and secret

### TMDB
1. Create an account at [TMDB](https://www.themoviedb.org/)
2. Request an API key from your account settings

### Overseer\Jellyseer
1. Go to Settings -> General
2. Copy your API key
   
## Upcoming Features

## Contributors
Vansmak aka Vanhacked
FNXPT

## License
MIT


## Selected-title metadata (v0.6.2+)

The authenticated Home Assistant WebSocket command `mediarr/media_details`
provides full descriptions, cast/roles, public TMDB portrait URLs, genres,
ratings and runtime for a selected title. It reuses an existing explicitly
configured `tmdb_api_key` from Mediarr's YAML configuration or config entries;
Plex/Seerr/Sonarr credentials are never substituted. No credential is returned
to the card or placed in frontend URLs.

The matching card update loads details when a sensor only has a short synopsis
or lacks cast data. Use mediarr-card v0.4.1 or newer with this backend update. Both components must be updated.
Restart Home Assistant after installing the backend. Old cards continue to work.
Requests are cached for six hours (maximum 256 entries), with at most four
concurrent WebSocket metadata lookups. Ambiguous title searches do not silently
pick the first movie/series result. Errors distinguish missing credentials,
rejected authentication, missing/ambiguous titles and temporary availability.

Tests: with Home Assistant's Python dependencies installed, run
`python -m unittest discover -s tests -v`. These tests use a fake TMDB transport;
they do not require or expose a real TMDB key.
