"""Config flow for the Mediarr integration."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback

from . import DOMAIN
from .common.const import DEFAULT_MAX_ITEMS
from .config_helpers import get_entry_config

SECTION_SEER = "seer"
SECTION_IMMACULATERR = "immaculaterr"
SECTION_TMDB = "tmdb"
MANAGED_SECTIONS = (SECTION_SEER, SECTION_IMMACULATERR, SECTION_TMDB)


def _int_field(min_value: int = 1, max_value: int = 250) -> Any:
    return vol.All(vol.Coerce(int), vol.Range(min=min_value, max=max_value))


class MediarrConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mediarr."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._sections: list[str] = []
        self._title: str = "Mediarr"

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
        if user_input is None:
            return self.async_show_form(step_id="seer", data_schema=self._seer_schema())

        self._data[SECTION_SEER] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "tmdb_api_key": user_input.get("tmdb_api_key", "").strip() or None,
            "max_items": user_input["max_items"],
            "trending": user_input["trending"],
            "discover": user_input["discover"],
            "popular_movies": user_input["popular_movies"],
            "popular_tv": user_input["popular_tv"],
        }
        return await self._next_step()

    async def async_step_immaculaterr(self, user_input: dict[str, Any] | None = None):
        """Configure Immaculaterr."""
        if user_input is None:
            return self.async_show_form(
                step_id="immaculaterr", data_schema=self._immaculaterr_schema()
            )

        self._data[SECTION_IMMACULATERR] = {
            "url": user_input["url"].strip(),
            "username": user_input["username"].strip(),
            "password": user_input["password"],
            "mode": user_input["mode"],
            "max_items": user_input["max_items"],
            "tmdb_api_key": user_input.get("tmdb_api_key", "").strip() or None,
            "movie_library_section_key": (
                user_input.get("movie_library_section_key", "").strip() or None
            ),
            "tv_library_section_key": (
                user_input.get("tv_library_section_key", "").strip() or None
            ),
        }
        return await self._next_step()

    async def async_step_tmdb(self, user_input: dict[str, Any] | None = None):
        """Configure TMDB discovery sensors."""
        if user_input is None:
            return self.async_show_form(step_id="tmdb", data_schema=self._tmdb_schema())

        self._data[SECTION_TMDB] = {
            "tmdb_api_key": user_input["tmdb_api_key"].strip(),
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
                vol.Optional("setup_seer", default=True): bool,
                vol.Optional("setup_immaculaterr", default=False): bool,
                vol.Optional("setup_tmdb", default=False): bool,
            }
        )

    def _seer_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url"): str,
                vol.Required("api_key"): str,
                vol.Optional("tmdb_api_key", default=""): str,
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Optional("trending", default=True): bool,
                vol.Optional("discover", default=True): bool,
                vol.Optional("popular_movies", default=False): bool,
                vol.Optional("popular_tv", default=False): bool,
            }
        )

    def _immaculaterr_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url"): str,
                vol.Required("username"): str,
                vol.Required("password"): str,
                vol.Required("mode", default="review"): vol.In(["review", "pendingApproval"]),
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Optional("tmdb_api_key", default=""): str,
                vol.Optional("movie_library_section_key", default=""): str,
                vol.Optional("tv_library_section_key", default=""): str,
            }
        )

    def _tmdb_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("tmdb_api_key"): str,
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
        if user_input.get("setup_seer"):
            sections.append(SECTION_SEER)
        if user_input.get("setup_immaculaterr"):
            sections.append(SECTION_IMMACULATERR)
        if user_input.get("setup_tmdb"):
            sections.append(SECTION_TMDB)
        return sections

    async def _next_step(self):
        if not self._sections:
            return self.async_create_entry(title=self._title, data=self._data)

        next_section = self._sections.pop(0)
        return await getattr(self, f"async_step_{next_section}")()


class MediarrOptionsFlow(config_entries.OptionsFlow):
    """Handle Mediarr options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry
        self._base_config = get_entry_config(config_entry)
        self._data: dict[str, Any] = {}
        self._sections: list[str] = []

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
        if user_input is None:
            return self.async_show_form(step_id="seer", data_schema=self._seer_schema(defaults))

        self._data[SECTION_SEER] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "tmdb_api_key": user_input.get("tmdb_api_key", "").strip() or None,
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
        if user_input is None:
            return self.async_show_form(
                step_id="immaculaterr", data_schema=self._immaculaterr_schema(defaults)
            )

        self._data[SECTION_IMMACULATERR] = {
            "url": user_input["url"].strip(),
            "username": user_input["username"].strip(),
            "password": user_input["password"],
            "mode": user_input["mode"],
            "max_items": user_input["max_items"],
            "tmdb_api_key": user_input.get("tmdb_api_key", "").strip() or None,
            "movie_library_section_key": (
                user_input.get("movie_library_section_key", "").strip() or None
            ),
            "tv_library_section_key": (
                user_input.get("tv_library_section_key", "").strip() or None
            ),
        }
        return await self._next_step()

    async def async_step_tmdb(self, user_input: dict[str, Any] | None = None):
        """Configure TMDB in options."""
        defaults = self._base_config.get(SECTION_TMDB) or {}
        if user_input is None:
            return self.async_show_form(step_id="tmdb", data_schema=self._tmdb_schema(defaults))

        self._data[SECTION_TMDB] = {
            "tmdb_api_key": user_input["tmdb_api_key"].strip(),
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
                    "setup_seer", default=bool(self._base_config.get(SECTION_SEER))
                ): bool,
                vol.Optional(
                    "setup_immaculaterr",
                    default=bool(self._base_config.get(SECTION_IMMACULATERR)),
                ): bool,
                vol.Optional(
                    "setup_tmdb", default=bool(self._base_config.get(SECTION_TMDB))
                ): bool,
            }
        )

    def _seer_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url", default=defaults.get("url", "")): str,
                vol.Required("api_key", default=defaults.get("api_key", "")): str,
                vol.Optional("tmdb_api_key", default=defaults.get("tmdb_api_key") or ""): str,
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Optional("trending", default=defaults.get("trending", True)): bool,
                vol.Optional("discover", default=defaults.get("discover", True)): bool,
                vol.Optional("popular_movies", default=defaults.get("popular_movies", False)): bool,
                vol.Optional("popular_tv", default=defaults.get("popular_tv", False)): bool,
            }
        )

    def _immaculaterr_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url", default=defaults.get("url", "")): str,
                vol.Required("username", default=defaults.get("username", "")): str,
                vol.Required("password", default=defaults.get("password", "")): str,
                vol.Required("mode", default=defaults.get("mode", "review")): vol.In(
                    ["review", "pendingApproval"]
                ),
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Optional("tmdb_api_key", default=defaults.get("tmdb_api_key") or ""): str,
                vol.Optional(
                    "movie_library_section_key",
                    default=defaults.get("movie_library_section_key") or "",
                ): str,
                vol.Optional(
                    "tv_library_section_key",
                    default=defaults.get("tv_library_section_key") or "",
                ): str,
            }
        )

    def _tmdb_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("tmdb_api_key", default=defaults.get("tmdb_api_key", "")): str,
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
        if user_input.get("setup_seer"):
            sections.append(SECTION_SEER)
        if user_input.get("setup_immaculaterr"):
            sections.append(SECTION_IMMACULATERR)
        if user_input.get("setup_tmdb"):
            sections.append(SECTION_TMDB)
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

        return self.async_create_entry(title="", data=updated)
