"""Config flow for the Mediarr integration."""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN
from .common.const import DEFAULT_MAX_ITEMS
from .config_helpers import get_entry_config

SECTION_SEER = "seer"
SECTION_IMMACULATERR = "immaculaterr"
SECTION_TMDB = "tmdb"
FIELD_ENABLE_SEER = "seer"
FIELD_ENABLE_IMMACULATERR = "immaculaterr"
FIELD_ENABLE_TMDB = "tmdb"
TMDB_KEY_FIELD = "tmdb_api_key"
TMDB_ENRICHMENT_FIELD = "tmdb_enrichment"
MANAGED_SECTIONS = (SECTION_SEER, SECTION_IMMACULATERR, SECTION_TMDB)
_LOGGER = logging.getLogger(__name__)


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalize_section_keys(value: Any) -> list[str]:
    if value is None:
        return []

    raw_values: list[Any]
    if isinstance(value, (list, tuple, set)):
        raw_values = list(value)
    elif isinstance(value, str):
        # Allow comma-separated manual input in custom selector mode.
        raw_values = value.split(",")
    else:
        raw_values = [value]

    keys: list[str] = []
    seen: set[str] = set()
    for raw in raw_values:
        normalized = _normalize_optional_text(raw)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        keys.append(normalized)
    return keys


def _extract_section_keys(config: dict[str, Any], *, singular: str, plural: str) -> list[str]:
    keys = _normalize_section_keys(config.get(plural))
    single = _normalize_optional_text(config.get(singular))
    if single and single not in keys:
        keys.insert(0, single)
    return keys


def _extract_shared_tmdb_api_key(config: dict[str, Any]) -> str | None:
    direct = _normalize_optional_text(config.get(TMDB_KEY_FIELD))
    if direct:
        return direct

    for section in MANAGED_SECTIONS:
        section_config = config.get(section)
        if isinstance(section_config, dict):
            key = _normalize_optional_text(section_config.get(TMDB_KEY_FIELD))
            if key:
                return key
    return None


def _apply_shared_tmdb_api_key(config: dict[str, Any], shared_tmdb_api_key: str | None) -> None:
    normalized = _normalize_optional_text(shared_tmdb_api_key)
    config[TMDB_KEY_FIELD] = normalized
    if not normalized:
        return

    for section in MANAGED_SECTIONS:
        section_config = config.get(section)
        if isinstance(section_config, dict):
            if not _normalize_optional_text(section_config.get(TMDB_KEY_FIELD)):
                section_config[TMDB_KEY_FIELD] = normalized


def _filter_keys_to_options(
    keys: list[str],
    options: list[selector.SelectOptionDict],
) -> list[str]:
    if not options:
        return keys
    allowed = {str(option["value"]) for option in options}
    return [key for key in keys if key in allowed]


def _host_from_url(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = urlparse(value)
    except Exception:
        return None
    host = (parsed.hostname or "").strip()
    return host or None


def _friendly_plex_source_name(
    entry: config_entries.ConfigEntry,
    base_url: str | None,
) -> str:
    direct_name = _normalize_optional_text(entry.data.get("server"))
    if direct_name:
        return direct_name

    title = _normalize_optional_text(entry.title)
    if title:
        title_host = _host_from_url(title)
        if title_host:
            return title_host
        return title

    base_host = _host_from_url(base_url)
    if base_host:
        return base_host

    return "Plex"


def _is_movie_section(section_type: str) -> bool:
    normalized = section_type.strip().lower()
    return normalized in {"movie", "movies", "1"}


def _is_tv_section(section_type: str) -> bool:
    normalized = section_type.strip().lower()
    return normalized in {"show", "shows", "tv", "series", "2"}


def _parse_plex_sections(xml_text: str) -> list[dict[str, str]]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    parsed: list[dict[str, str]] = []
    for directory in root.findall(".//Directory"):
        key = (directory.get("key") or "").strip()
        title = (directory.get("title") or "").strip()
        section_type = (directory.get("type") or "").strip()
        if not key or not section_type:
            continue
        parsed.append(
            {
                "key": key,
                "title": title or f"Section {key}",
                "type": section_type,
            }
        )
    return parsed


def _build_section_options(
    sections: list[dict[str, str]],
    *,
    media_type: str,
) -> list[selector.SelectOptionDict]:
    options: list[selector.SelectOptionDict] = []
    for section in sections:
        section_type = section.get("type", "")
        if media_type == "movie" and not _is_movie_section(section_type):
            continue
        if media_type == "tv" and not _is_tv_section(section_type):
            continue

        key = section.get("key", "")
        title = section.get("title", f"Section {key}")
        source = section.get("source", "")
        label = f"{title} (#{key})"
        if source:
            label = f"{source}: {label}"
        options.append(selector.SelectOptionDict(value=key, label=label))

    options.sort(key=lambda item: str(item["label"]).lower())
    return options


async def _async_discover_plex_sections(hass: HomeAssistant) -> list[dict[str, str]]:
    plex_entries = hass.config_entries.async_entries("plex")
    if not plex_entries:
        return []

    session = async_get_clientsession(hass)
    discovered: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for entry in plex_entries:
        server_config = entry.data.get("server_config") or {}
        base_url = _normalize_optional_text(
            server_config.get("url") or entry.data.get("url")
        )
        token = _normalize_optional_text(
            server_config.get("token") or entry.data.get("token")
        )
        verify_ssl = server_config.get("verify_ssl", entry.data.get("verify_ssl", True))
        if not base_url or not token:
            continue

        try:
            async with async_timeout.timeout(10):
                async with session.get(
                    f"{base_url.rstrip('/')}/library/sections",
                    headers={
                        "Accept": "application/xml",
                        "X-Plex-Token": token,
                    },
                    ssl=bool(verify_ssl),
                ) as response:
                    if response.status != 200:
                        _LOGGER.debug(
                            "Failed to discover Plex sections for %s (status=%s)",
                            entry.title,
                            response.status,
                        )
                        continue
                    xml_text = await response.text()
        except (aiohttp.ClientError, TimeoutError, OSError) as err:
            _LOGGER.debug(
                "Failed to load Plex sections for %s: %s",
                entry.title,
                err,
            )
            continue

        for section in _parse_plex_sections(xml_text):
            dedupe_key = (entry.entry_id, section["key"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            section["source"] = _friendly_plex_source_name(entry, base_url)
            discovered.append(section)

    return discovered


def _int_field(min_value: int = 1, max_value: int = 250) -> Any:
    return vol.All(vol.Coerce(int), vol.Range(min=min_value, max=max_value))


def _immaculaterr_mode_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value="review", label="Review"),
                selector.SelectOptionDict(
                    value="pendingApproval",
                    label="Pending Approval",
                ),
            ],
            mode=selector.SelectSelectorMode.LIST,
        )
    )


class MediarrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mediarr."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._sections: list[str] = []
        self._title: str = "Mediarr"
        self._shared_tmdb_api_key: str | None = None
        self._discovered_plex_sections: list[dict[str, str]] = []
        self._plex_discovery_attempted = False

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Return the options flow."""
        return MediarrOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        """Handle the initial step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=self._user_schema())

        self._title = user_input.get("title", "Mediarr")
        self._sections = self._selected_sections(user_input)
        self._data = {}
        return await self._next_step()

    async def async_step_seer(self, user_input: dict[str, Any] | None = None):
        """Configure Seer (Overseerr/Jellyseerr)."""
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="seer",
                data_schema=self._seer_schema(self._effective_tmdb_api_key()),
                errors=errors,
            )

        tmdb_enrichment = bool(user_input.get(TMDB_ENRICHMENT_FIELD, False))
        tmdb_api_key = self._effective_tmdb_api_key()
        if tmdb_enrichment and not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_module"
            return self.async_show_form(
                step_id="seer",
                data_schema=self._seer_schema(self._effective_tmdb_api_key()),
                errors=errors,
            )

        self._data[SECTION_SEER] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            TMDB_ENRICHMENT_FIELD: tmdb_enrichment,
            TMDB_KEY_FIELD: tmdb_api_key if tmdb_enrichment else None,
            "max_items": user_input["max_items"],
            "trending": user_input["trending"],
            "discover": user_input["discover"],
            "popular_movies": user_input["popular_movies"],
            "popular_tv": user_input["popular_tv"],
        }
        return await self._next_step()

    async def async_step_immaculaterr(self, user_input: dict[str, Any] | None = None):
        """Configure Immaculaterr."""
        errors: dict[str, str] = {}
        if not self._plex_discovery_attempted:
            self._discovered_plex_sections = await _async_discover_plex_sections(self.hass)
            self._plex_discovery_attempted = True

        if user_input is None:
            return self.async_show_form(
                step_id="immaculaterr",
                data_schema=self._immaculaterr_schema(
                    self._discovered_plex_sections,
                    self._effective_tmdb_api_key(),
                ),
                errors=errors,
            )

        movie_library_section_keys = _normalize_section_keys(
            user_input.get("movie_library_section_keys")
        )
        tv_library_section_keys = _normalize_section_keys(
            user_input.get("tv_library_section_keys")
        )
        if not movie_library_section_keys:
            movie_key = _normalize_optional_text(user_input.get("movie_library_section_key"))
            if movie_key:
                movie_library_section_keys = [movie_key]
        if not tv_library_section_keys:
            tv_key = _normalize_optional_text(user_input.get("tv_library_section_key"))
            if tv_key:
                tv_library_section_keys = [tv_key]

        if not movie_library_section_keys and not tv_library_section_keys:
            errors["base"] = "missing_library_section_key"
            return self.async_show_form(
                step_id="immaculaterr",
                data_schema=self._immaculaterr_schema(
                    self._discovered_plex_sections,
                    self._effective_tmdb_api_key(),
                ),
                errors=errors,
            )

        tmdb_enrichment = bool(user_input.get(TMDB_ENRICHMENT_FIELD, False))
        tmdb_api_key = self._effective_tmdb_api_key()
        if tmdb_enrichment and not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_module"
            return self.async_show_form(
                step_id="immaculaterr",
                data_schema=self._immaculaterr_schema(
                    self._discovered_plex_sections,
                    self._effective_tmdb_api_key(),
                ),
                errors=errors,
            )

        self._data[SECTION_IMMACULATERR] = {
            "url": user_input["url"].strip(),
            "username": user_input["username"].strip(),
            "password": user_input["password"],
            "mode": user_input["mode"],
            "max_items": user_input["max_items"],
            TMDB_ENRICHMENT_FIELD: tmdb_enrichment,
            TMDB_KEY_FIELD: tmdb_api_key if tmdb_enrichment else None,
            "movie_library_section_key": (
                movie_library_section_keys[0] if movie_library_section_keys else None
            ),
            "tv_library_section_key": (
                tv_library_section_keys[0] if tv_library_section_keys else None
            ),
            "movie_library_section_keys": movie_library_section_keys,
            "tv_library_section_keys": tv_library_section_keys,
        }
        return await self._next_step()

    async def async_step_tmdb(self, user_input: dict[str, Any] | None = None):
        """Configure TMDB discovery sensors."""
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="tmdb",
                data_schema=self._tmdb_schema(self._effective_tmdb_api_key()),
                errors=errors,
            )

        tmdb_api_key = (
            _normalize_optional_text(user_input.get(TMDB_KEY_FIELD))
            or self._effective_tmdb_api_key()
        )
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key"
            return self.async_show_form(
                step_id="tmdb",
                data_schema=self._tmdb_schema(self._effective_tmdb_api_key()),
                errors=errors,
            )
        self._remember_tmdb_api_key(tmdb_api_key)

        self._data[SECTION_TMDB] = {
            TMDB_KEY_FIELD: tmdb_api_key,
            "max_items": user_input["max_items"],
            "trending": user_input["trending"],
            "now_playing": user_input["now_playing"],
            "upcoming": user_input["upcoming"],
            "on_air": user_input["on_air"],
            "airing_today": user_input["airing_today"],
            "popular_movies": user_input["popular_movies"],
            "popular_tv": user_input["popular_tv"],
        }
        return await self._next_step()

    def _user_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional("title", default="Mediarr"): str,
                vol.Optional(FIELD_ENABLE_SEER, default=True): bool,
                vol.Optional(FIELD_ENABLE_IMMACULATERR, default=False): bool,
                vol.Optional(FIELD_ENABLE_TMDB, default=False): bool,
            }
        )

    def _seer_schema(self, default_tmdb_api_key: str | None = None) -> vol.Schema:
        default_tmdb_enrichment = bool(default_tmdb_api_key)
        return vol.Schema(
            {
                vol.Required("url"): str,
                vol.Required("api_key"): str,
                vol.Optional(TMDB_ENRICHMENT_FIELD, default=default_tmdb_enrichment): bool,
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Optional("trending", default=True): bool,
                vol.Optional("discover", default=True): bool,
                vol.Optional("popular_movies", default=False): bool,
                vol.Optional("popular_tv", default=False): bool,
            }
        )

    def _immaculaterr_schema(
        self,
        discovered_sections: list[dict[str, str]],
        default_tmdb_api_key: str | None = None,
    ) -> vol.Schema:
        schema: dict[Any, Any] = {
            vol.Required("url"): str,
            vol.Required("username"): str,
            vol.Required("password"): str,
            vol.Required("mode", default="review"): _immaculaterr_mode_selector(),
            vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
            vol.Optional(
                TMDB_ENRICHMENT_FIELD,
                default=bool(default_tmdb_api_key),
            ): bool,
        }

        movie_options = _build_section_options(discovered_sections, media_type="movie")
        tv_options = _build_section_options(discovered_sections, media_type="tv")

        if movie_options:
            schema[vol.Optional("movie_library_section_keys", default=[])] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=movie_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            )
        else:
            schema[vol.Optional("movie_library_section_key", default="")] = str

        if tv_options:
            schema[vol.Optional("tv_library_section_keys", default=[])] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=tv_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            )
        else:
            schema[vol.Optional("tv_library_section_key", default="")] = str

        return vol.Schema(schema)

    def _tmdb_schema(self, default_tmdb_api_key: str | None = None) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(TMDB_KEY_FIELD, default=default_tmdb_api_key or ""): str,
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Optional("trending", default=True): bool,
                vol.Optional("now_playing", default=True): bool,
                vol.Optional("upcoming", default=True): bool,
                vol.Optional("on_air", default=True): bool,
                vol.Optional("airing_today", default=False): bool,
                vol.Optional("popular_movies", default=True): bool,
                vol.Optional("popular_tv", default=True): bool,
            }
        )

    def _selected_sections(self, user_input: dict[str, Any]) -> list[str]:
        sections: list[str] = []
        if user_input.get(FIELD_ENABLE_TMDB):
            sections.append(SECTION_TMDB)
        if user_input.get(FIELD_ENABLE_SEER):
            sections.append(SECTION_SEER)
        if user_input.get(FIELD_ENABLE_IMMACULATERR):
            sections.append(SECTION_IMMACULATERR)
        return sections

    async def _next_step(self):
        if not self._sections:
            _apply_shared_tmdb_api_key(self._data, self._effective_tmdb_api_key())
            return self.async_create_entry(title=self._title, data=self._data)

        next_section = self._sections.pop(0)
        return await getattr(self, f"async_step_{next_section}")()

    def _effective_tmdb_api_key(self) -> str | None:
        return self._shared_tmdb_api_key or _extract_shared_tmdb_api_key(self._data)

    def _remember_tmdb_api_key(self, tmdb_api_key: str | None) -> None:
        normalized = _normalize_optional_text(tmdb_api_key)
        if normalized:
            self._shared_tmdb_api_key = normalized


class MediarrOptionsFlow(config_entries.OptionsFlow):
    """Handle Mediarr options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._base_config = get_entry_config(config_entry)
        self._data: dict[str, Any] = {}
        self._sections: list[str] = []
        self._shared_tmdb_api_key: str | None = _extract_shared_tmdb_api_key(
            self._base_config
        )
        self._discovered_plex_sections: list[dict[str, str]] = []
        self._plex_discovery_attempted = False

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        """Manage options."""
        if user_input is None:
            return self.async_show_form(step_id="init", data_schema=self._user_schema())

        self._sections = self._selected_sections(user_input)
        self._data = {}
        return await self._next_step()

    async def async_step_seer(self, user_input: dict[str, Any] | None = None):
        """Configure Seer in options."""
        defaults = self._base_config.get(SECTION_SEER) or {}
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="seer",
                data_schema=self._seer_schema(defaults, self._effective_tmdb_api_key()),
                errors=errors,
            )

        tmdb_enrichment = bool(user_input.get(TMDB_ENRICHMENT_FIELD, False))
        tmdb_api_key = self._effective_tmdb_api_key()
        if tmdb_enrichment and not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_module"
            return self.async_show_form(
                step_id="seer",
                data_schema=self._seer_schema(defaults, self._effective_tmdb_api_key()),
                errors=errors,
            )

        self._data[SECTION_SEER] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            TMDB_ENRICHMENT_FIELD: tmdb_enrichment,
            TMDB_KEY_FIELD: tmdb_api_key if tmdb_enrichment else None,
            "max_items": user_input["max_items"],
            "trending": user_input["trending"],
            "discover": user_input["discover"],
            "popular_movies": user_input["popular_movies"],
            "popular_tv": user_input["popular_tv"],
        }
        return await self._next_step()

    async def async_step_immaculaterr(self, user_input: dict[str, Any] | None = None):
        """Configure Immaculaterr in options."""
        defaults = self._base_config.get(SECTION_IMMACULATERR) or {}
        errors: dict[str, str] = {}
        if not self._plex_discovery_attempted:
            self._discovered_plex_sections = await _async_discover_plex_sections(self.hass)
            self._plex_discovery_attempted = True

        if user_input is None:
            return self.async_show_form(
                step_id="immaculaterr",
                data_schema=self._immaculaterr_schema(
                    defaults,
                    self._discovered_plex_sections,
                    self._effective_tmdb_api_key(),
                ),
                errors=errors,
            )

        movie_library_section_keys = _normalize_section_keys(
            user_input.get("movie_library_section_keys")
        )
        tv_library_section_keys = _normalize_section_keys(
            user_input.get("tv_library_section_keys")
        )
        if not movie_library_section_keys:
            movie_key = _normalize_optional_text(user_input.get("movie_library_section_key"))
            if movie_key:
                movie_library_section_keys = [movie_key]
        if not tv_library_section_keys:
            tv_key = _normalize_optional_text(user_input.get("tv_library_section_key"))
            if tv_key:
                tv_library_section_keys = [tv_key]

        if not movie_library_section_keys and not tv_library_section_keys:
            errors["base"] = "missing_library_section_key"
            return self.async_show_form(
                step_id="immaculaterr",
                data_schema=self._immaculaterr_schema(
                    defaults,
                    self._discovered_plex_sections,
                    self._effective_tmdb_api_key(),
                ),
                errors=errors,
            )

        tmdb_enrichment = bool(user_input.get(TMDB_ENRICHMENT_FIELD, False))
        tmdb_api_key = self._effective_tmdb_api_key()
        if tmdb_enrichment and not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_module"
            return self.async_show_form(
                step_id="immaculaterr",
                data_schema=self._immaculaterr_schema(
                    defaults,
                    self._discovered_plex_sections,
                    self._effective_tmdb_api_key(),
                ),
                errors=errors,
            )

        self._data[SECTION_IMMACULATERR] = {
            "url": user_input["url"].strip(),
            "username": user_input["username"].strip(),
            "password": user_input["password"],
            "mode": user_input["mode"],
            "max_items": user_input["max_items"],
            TMDB_ENRICHMENT_FIELD: tmdb_enrichment,
            TMDB_KEY_FIELD: tmdb_api_key if tmdb_enrichment else None,
            "movie_library_section_key": (
                movie_library_section_keys[0] if movie_library_section_keys else None
            ),
            "tv_library_section_key": (
                tv_library_section_keys[0] if tv_library_section_keys else None
            ),
            "movie_library_section_keys": movie_library_section_keys,
            "tv_library_section_keys": tv_library_section_keys,
        }
        return await self._next_step()

    async def async_step_tmdb(self, user_input: dict[str, Any] | None = None):
        """Configure TMDB in options."""
        defaults = self._base_config.get(SECTION_TMDB) or {}
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="tmdb",
                data_schema=self._tmdb_schema(defaults, self._effective_tmdb_api_key()),
                errors=errors,
            )

        tmdb_api_key = (
            _normalize_optional_text(user_input.get(TMDB_KEY_FIELD))
            or self._effective_tmdb_api_key()
        )
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key"
            return self.async_show_form(
                step_id="tmdb",
                data_schema=self._tmdb_schema(defaults, self._effective_tmdb_api_key()),
                errors=errors,
            )
        self._remember_tmdb_api_key(tmdb_api_key)

        self._data[SECTION_TMDB] = {
            TMDB_KEY_FIELD: tmdb_api_key,
            "max_items": user_input["max_items"],
            "trending": user_input["trending"],
            "now_playing": user_input["now_playing"],
            "upcoming": user_input["upcoming"],
            "on_air": user_input["on_air"],
            "airing_today": user_input["airing_today"],
            "popular_movies": user_input["popular_movies"],
            "popular_tv": user_input["popular_tv"],
        }
        return await self._next_step()

    def _user_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    FIELD_ENABLE_SEER,
                    default=bool(self._base_config.get(SECTION_SEER)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_IMMACULATERR,
                    default=bool(self._base_config.get(SECTION_IMMACULATERR)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_TMDB,
                    default=bool(self._base_config.get(SECTION_TMDB)),
                ): bool,
            }
        )

    def _seer_schema(
        self,
        defaults: dict[str, Any],
        default_tmdb_api_key: str | None = None,
    ) -> vol.Schema:
        default_tmdb_enrichment_raw = defaults.get(TMDB_ENRICHMENT_FIELD)
        if default_tmdb_enrichment_raw is None:
            default_tmdb_enrichment = bool(
                defaults.get(TMDB_KEY_FIELD) or default_tmdb_api_key
            )
        else:
            default_tmdb_enrichment = bool(default_tmdb_enrichment_raw)
        return vol.Schema(
            {
                vol.Required("url", default=defaults.get("url", "")): str,
                vol.Required("api_key", default=defaults.get("api_key", "")): str,
                vol.Optional(
                    TMDB_ENRICHMENT_FIELD, default=default_tmdb_enrichment
                ): bool,
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Optional("trending", default=defaults.get("trending", True)): bool,
                vol.Optional("discover", default=defaults.get("discover", True)): bool,
                vol.Optional("popular_movies", default=defaults.get("popular_movies", False)): bool,
                vol.Optional("popular_tv", default=defaults.get("popular_tv", False)): bool,
            }
        )

    def _immaculaterr_schema(
        self,
        defaults: dict[str, Any],
        discovered_sections: list[dict[str, str]],
        default_tmdb_api_key: str | None = None,
    ) -> vol.Schema:
        default_tmdb_enrichment_raw = defaults.get(TMDB_ENRICHMENT_FIELD)
        if default_tmdb_enrichment_raw is None:
            default_tmdb_enrichment = bool(
                defaults.get(TMDB_KEY_FIELD) or default_tmdb_api_key
            )
        else:
            default_tmdb_enrichment = bool(default_tmdb_enrichment_raw)
        schema: dict[Any, Any] = {
            vol.Required("url", default=defaults.get("url", "")): str,
            vol.Required("username", default=defaults.get("username", "")): str,
            vol.Required("password", default=defaults.get("password", "")): str,
            vol.Required("mode", default=defaults.get("mode", "review")): (
                _immaculaterr_mode_selector()
            ),
            vol.Required(
                "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
            ): _int_field(),
            vol.Optional(
                TMDB_ENRICHMENT_FIELD, default=default_tmdb_enrichment
            ): bool,
        }

        default_movie_keys = _extract_section_keys(
            defaults,
            singular="movie_library_section_key",
            plural="movie_library_section_keys",
        )
        default_tv_keys = _extract_section_keys(
            defaults,
            singular="tv_library_section_key",
            plural="tv_library_section_keys",
        )

        movie_options = _build_section_options(discovered_sections, media_type="movie")
        tv_options = _build_section_options(discovered_sections, media_type="tv")
        default_movie_keys = _filter_keys_to_options(default_movie_keys, movie_options)
        default_tv_keys = _filter_keys_to_options(default_tv_keys, tv_options)

        if movie_options:
            schema[vol.Optional("movie_library_section_keys", default=default_movie_keys)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=movie_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            )
        else:
            schema[vol.Optional(
                "movie_library_section_key",
                default=defaults.get("movie_library_section_key") or "",
            )] = str

        if tv_options:
            schema[vol.Optional("tv_library_section_keys", default=default_tv_keys)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=tv_options,
                        multiple=True,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            )
        else:
            schema[vol.Optional(
                "tv_library_section_key",
                default=defaults.get("tv_library_section_key") or "",
            )] = str

        return vol.Schema(schema)

    def _tmdb_schema(
        self,
        defaults: dict[str, Any],
        default_tmdb_api_key: str | None = None,
    ) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required(
                    TMDB_KEY_FIELD,
                    default=defaults.get(TMDB_KEY_FIELD) or default_tmdb_api_key or "",
                ): str,
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Optional("trending", default=defaults.get("trending", True)): bool,
                vol.Optional("now_playing", default=defaults.get("now_playing", True)): bool,
                vol.Optional("upcoming", default=defaults.get("upcoming", True)): bool,
                vol.Optional("on_air", default=defaults.get("on_air", True)): bool,
                vol.Optional("airing_today", default=defaults.get("airing_today", False)): bool,
                vol.Optional("popular_movies", default=defaults.get("popular_movies", True)): bool,
                vol.Optional("popular_tv", default=defaults.get("popular_tv", True)): bool,
            }
        )

    def _selected_sections(self, user_input: dict[str, Any]) -> list[str]:
        sections: list[str] = []
        if user_input.get(FIELD_ENABLE_TMDB):
            sections.append(SECTION_TMDB)
        if user_input.get(FIELD_ENABLE_SEER):
            sections.append(SECTION_SEER)
        if user_input.get(FIELD_ENABLE_IMMACULATERR):
            sections.append(SECTION_IMMACULATERR)
        return sections

    async def _next_step(self):
        if self._sections:
            next_section = self._sections.pop(0)
            return await getattr(self, f"async_step_{next_section}")()

        updated = dict(self._base_config)
        for section in MANAGED_SECTIONS:
            if section in self._data:
                updated[section] = self._data[section]
            else:
                updated[section] = None

        _apply_shared_tmdb_api_key(updated, self._effective_tmdb_api_key())
        return self.async_create_entry(title="", data=updated)

    def _effective_tmdb_api_key(self) -> str | None:
        return self._shared_tmdb_api_key or _extract_shared_tmdb_api_key(self._data)

    def _remember_tmdb_api_key(self, tmdb_api_key: Any) -> None:
        normalized = _normalize_optional_text(tmdb_api_key)
        if normalized:
            self._shared_tmdb_api_key = normalized
