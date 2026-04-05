"""Sensor platform for Mediarr."""
from __future__ import annotations

from typing import Any
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN
from .config_helpers import get_entry_config
from .common.const import (
    DEFAULT_DAYS,
    DEFAULT_MAX_ITEMS,
)

_LOGGER = logging.getLogger(__name__)


def _normalize_section_keys(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []

    if isinstance(raw_value, (list, tuple, set)):
        values = list(raw_value)
    else:
        values = [raw_value]

    keys: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def _extract_section_keys(
    config: dict[str, Any],
    *,
    singular_key: str,
    plural_key: str,
    legacy_alias: str | None = None,
) -> list[str]:
    keys = _normalize_section_keys(config.get(plural_key))
    singular_value = config.get(singular_key)
    if singular_value is None and legacy_alias:
        singular_value = config.get(legacy_alias)
    for key in _normalize_section_keys(singular_value):
        if key not in keys:
            keys.insert(0, key)
    return keys


def _resolve_tmdb_api_key(
    config: dict[str, Any],
    section_config: dict[str, Any] | None = None,
) -> str | None:
    if isinstance(section_config, dict):
        section_key = str(section_config.get("tmdb_api_key") or "").strip()
        if section_key:
            return section_key

    global_key = str(config.get("tmdb_api_key") or "").strip()
    if global_key:
        return global_key

    for section in ("tmdb", "seer", "immaculaterr"):
        candidate_section = config.get(section)
        if isinstance(candidate_section, dict):
            candidate_key = str(candidate_section.get("tmdb_api_key") or "").strip()
            if candidate_key:
                return candidate_key

    return None


async def _async_build_sensors(
    hass,
    config: dict[str, Any],
    *,
    setup_yaml_immaculaterr_services: bool,
) -> list:
    """Create sensors from config."""
    session = async_get_clientsession(hass)
    sensors = []

    plex_config = config.get("plex")
    if plex_config:
        from .server.plex import PlexMediarrSensor
        plex_sensors = await PlexMediarrSensor.create_sensors(hass, plex_config)
        sensors.extend(plex_sensors)

    jellyfin_config = config.get("jellyfin")
    if jellyfin_config:
        from .server.jellyfin import JellyfinMediarrSensor
        jellyfin_sensors = await JellyfinMediarrSensor.create_sensors(hass, jellyfin_config)
        sensors.extend(jellyfin_sensors)

    emby_config = config.get("emby")
    if emby_config:
        from .server.emby import EmbyMediarrSensor
        emby_sensors = await EmbyMediarrSensor.create_sensors(hass, emby_config)
        sensors.extend(emby_sensors)

    sonarr_config = config.get("sonarr")
    if sonarr_config:
        from .manager.sonarr import SonarrMediarrSensor
        sensors.append(SonarrMediarrSensor(
            session,
            sonarr_config["api_key"],
            sonarr_config["url"],
            sonarr_config.get("max_items", DEFAULT_MAX_ITEMS),
            sonarr_config.get("days_to_check", DEFAULT_DAYS)
        ))

    sonarr2_config = config.get("sonarr2")
    if sonarr2_config:
        from .manager.sonarr2 import Sonarr2MediarrSensor
        sensors.append(Sonarr2MediarrSensor(
            session,
            sonarr2_config["api_key"],
            sonarr2_config["url"],
            sonarr2_config.get("max_items", DEFAULT_MAX_ITEMS),
            sonarr2_config.get("days_to_check", DEFAULT_DAYS)
        ))

    radarr_config = config.get("radarr")
    if radarr_config:
        from .manager.radarr import RadarrMediarrSensor
        sensors.append(RadarrMediarrSensor(
            session,
            radarr_config["api_key"],
            radarr_config["url"],
            radarr_config.get("max_items", DEFAULT_MAX_ITEMS),
            radarr_config.get("days_to_check", DEFAULT_DAYS)
        ))

    radarr2_config = config.get("radarr2")
    if radarr2_config:
        from .manager.radarr2 import Radarr2MediarrSensor
        sensors.append(Radarr2MediarrSensor(
            session,
            radarr2_config["api_key"],
            radarr2_config["url"],
            radarr2_config.get("max_items", DEFAULT_MAX_ITEMS),
            radarr2_config.get("days_to_check", DEFAULT_DAYS)
        ))

    trakt_config = config.get("trakt")
    if trakt_config:
        from .discovery.trakt import TraktMediarrSensor
        sensors.append(TraktMediarrSensor(
            session,
            trakt_config["client_id"],
            trakt_config["client_secret"],
            trakt_config.get("trending_type", "both"),
            trakt_config.get("max_items", DEFAULT_MAX_ITEMS),
            trakt_config["tmdb_api_key"]
        ))

    tmdb_config = config.get("tmdb")
    if tmdb_config:
        from .discovery.tmdb import TMDBMediarrSensor
        tmdb_api_key = _resolve_tmdb_api_key(config, tmdb_config)
        filters = tmdb_config.get("filters", {})

        for endpoint in ["trending", "now_playing", "upcoming", "on_air", "airing_today"]:
            if tmdb_config.get(endpoint, False):
                sensors.append(TMDBMediarrSensor(
                    session,
                    tmdb_api_key,
                    tmdb_config.get("max_items", DEFAULT_MAX_ITEMS),
                    endpoint,
                    filters
                ))

        if tmdb_config.get("popular_movies", False):
            sensors.append(TMDBMediarrSensor(
                session,
                tmdb_api_key,
                tmdb_config.get("max_items", DEFAULT_MAX_ITEMS),
                "popular_movies",
                filters
            ))

        if tmdb_config.get("popular_tv", False):
            sensors.append(TMDBMediarrSensor(
                session,
                tmdb_api_key,
                tmdb_config.get("max_items", DEFAULT_MAX_ITEMS),
                "popular_tv",
                filters
            ))

    seer_config = config.get("seer")
    if seer_config:
        from .services.seer import SeerMediarrSensor
        from .discovery.seer_discovery import SeerDiscoveryMediarrSensor
        seer_tmdb_enabled = seer_config.get("tmdb_enrichment", True)
        seer_tmdb_api_key = (
            _resolve_tmdb_api_key(config, seer_config) if seer_tmdb_enabled else None
        )
        filters = seer_config.get("filters", {})

        sensors.append(SeerMediarrSensor(
            session,
            seer_config["api_key"],
            seer_config["url"],
            seer_tmdb_api_key,
            seer_config.get("max_items", DEFAULT_MAX_ITEMS)
        ))

        if seer_config.get("trending", False):
            sensors.append(SeerDiscoveryMediarrSensor(
                session,
                seer_config["api_key"],
                seer_config["url"],
                seer_tmdb_api_key,
                seer_config.get("max_items", DEFAULT_MAX_ITEMS),
                "trending",
                None,
                filters
            ))

        if seer_config.get("popular_movies", False):
            sensors.append(SeerDiscoveryMediarrSensor(
                session,
                seer_config["api_key"],
                seer_config["url"],
                seer_tmdb_api_key,
                seer_config.get("max_items", DEFAULT_MAX_ITEMS),
                "popular_movies",
                "movies",
                filters
            ))

        if seer_config.get("popular_tv", False):
            sensors.append(SeerDiscoveryMediarrSensor(
                session,
                seer_config["api_key"],
                seer_config["url"],
                seer_tmdb_api_key,
                seer_config.get("max_items", DEFAULT_MAX_ITEMS),
                "popular_tv",
                "tv",
                filters
            ))

        if seer_config.get("discover", False):
            sensors.append(SeerDiscoveryMediarrSensor(
                session,
                seer_config["api_key"],
                seer_config["url"],
                seer_tmdb_api_key,
                seer_config.get("max_items", DEFAULT_MAX_ITEMS),
                "discover",
                None,
                filters
            ))

    immaculaterr_config = config.get("immaculaterr")
    if immaculaterr_config:
        from .services.immaculaterr import ImmaculaterrMediarrSensor
        movie_library_section_keys = _extract_section_keys(
            immaculaterr_config,
            singular_key="movie_library_section_key",
            plural_key="movie_library_section_keys",
            legacy_alias="movies_library_section_key",
        )
        tv_library_section_keys = _extract_section_keys(
            immaculaterr_config,
            singular_key="tv_library_section_key",
            plural_key="tv_library_section_keys",
        )
        mode = immaculaterr_config.get("mode", "review")
        immac_tmdb_enabled = immaculaterr_config.get("tmdb_enrichment", True)
        tmdb_api_key = (
            _resolve_tmdb_api_key(config, immaculaterr_config)
            if immac_tmdb_enabled
            else None
        )
        max_items = immaculaterr_config.get("max_items", DEFAULT_MAX_ITEMS)
        if not movie_library_section_keys and not tv_library_section_keys:
            _LOGGER.warning(
                "Immaculaterr configured but no library section key set. "
                "Set movie_library_section_key and/or tv_library_section_key."
            )

        for movie_library_section_key in movie_library_section_keys:
            sensors.append(ImmaculaterrMediarrSensor(
                immaculaterr_config["url"],
                immaculaterr_config["username"],
                immaculaterr_config["password"],
                "movie",
                movie_library_section_key,
                max_items,
                mode,
                tmdb_api_key,
            ))

        for tv_library_section_key in tv_library_section_keys:
            sensors.append(ImmaculaterrMediarrSensor(
                immaculaterr_config["url"],
                immaculaterr_config["username"],
                immaculaterr_config["password"],
                "tv",
                tv_library_section_key,
                max_items,
                mode,
                tmdb_api_key,
            ))

        if setup_yaml_immaculaterr_services:
            from .services.immaculaterr_requests import (
                ImmaculaterrRequestHandler,
                async_setup_immaculaterr_services,
            )

            hass.data.setdefault(DOMAIN, {})
            if "immaculaterr_request_handler" not in hass.data[DOMAIN]:
                hass.data[DOMAIN]["immaculaterr_request_handler"] = ImmaculaterrRequestHandler(
                    immaculaterr_config["url"],
                    immaculaterr_config["username"],
                    immaculaterr_config["password"],
                )
                await async_setup_immaculaterr_services(hass, DOMAIN)

    return sensors


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up Mediarr sensors from YAML configuration."""
    sensors = await _async_build_sensors(
        hass,
        config,
        setup_yaml_immaculaterr_services=True,
    )

    if sensors:
        if "mediarr_sensors" not in hass.data:
            hass.data["mediarr_sensors"] = []
        hass.data["mediarr_sensors"].extend(sensors)
        async_add_entities(sensors, True)


async def async_setup_entry(hass, entry: ConfigEntry, async_add_entities):
    """Set up Mediarr sensors from a config entry."""
    config = get_entry_config(entry)
    sensors = await _async_build_sensors(
        hass,
        config,
        setup_yaml_immaculaterr_services=False,
    )
    if sensors:
        async_add_entities(sensors, True)
    return True


async def async_unload_platform(hass, config):
    """Unload the platform."""
    if config.get("seer") and "mediarr_sensors" in hass.data:
        sensors = hass.data["mediarr_sensors"]
        seer_sensors = [s for s in sensors if hasattr(s, "get_request_info")]
        for sensor in seer_sensors:
            await sensor.async_will_remove_from_hass()
        hass.data["mediarr_sensors"] = [s for s in sensors if s not in seer_sensors]
