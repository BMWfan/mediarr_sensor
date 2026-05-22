"""Config flow for the Mediarr integration."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any
from urllib.parse import urlencode, urlparse
import xml.etree.ElementTree as ET

import aiohttp
import async_timeout
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import DOMAIN, PLEX_AUTH_CALLBACK_PATH, async_resume_data_entry_flow
from .common.const import DEFAULT_DAYS, DEFAULT_MAX_ITEMS
from .config_helpers import get_entry_config

SECTION_SEER = "seer"
SECTION_IMMACULATERR = "immaculaterr"
SECTION_TMDB = "tmdb"
SECTION_PLEX = "plex"
SECTION_JELLYFIN = "jellyfin"
SECTION_SONARR = "sonarr"
SECTION_SONARR2 = "sonarr2"
SECTION_RADARR = "radarr"
SECTION_RADARR2 = "radarr2"
SECTION_TRAKT = "trakt"

FIELD_ENABLE_SEER = "seer"
FIELD_ENABLE_IMMACULATERR = "immaculaterr"
FIELD_ENABLE_TMDB = "tmdb"
FIELD_ENABLE_PLEX = "plex"
FIELD_ENABLE_JELLYFIN = "jellyfin"
FIELD_ENABLE_SONARR = "sonarr"
FIELD_ENABLE_SONARR2 = "sonarr2"
FIELD_ENABLE_RADARR = "radarr"
FIELD_ENABLE_RADARR2 = "radarr2"
FIELD_ENABLE_TRAKT = "trakt"
TMDB_KEY_FIELD = "tmdb_api_key"
TMDB_ENRICHMENT_FIELD = "tmdb_enrichment"
PLEX_AUTH_METHOD_FIELD = "auth_method"
PLEX_AUTH_METHOD_HOME_ASSISTANT = "home_assistant_plex"
PLEX_AUTH_METHOD_PLEX_ACCOUNT = "plex_account"
MANAGED_SECTIONS = (
    SECTION_SEER,
    SECTION_IMMACULATERR,
    SECTION_TMDB,
    SECTION_PLEX,
    SECTION_JELLYFIN,
    SECTION_SONARR,
    SECTION_SONARR2,
    SECTION_RADARR,
    SECTION_RADARR2,
    SECTION_TRAKT,
)
TMDB_KEY_SECTIONS = (
    SECTION_TMDB,
    SECTION_SEER,
    SECTION_IMMACULATERR,
    SECTION_PLEX,
    SECTION_JELLYFIN,
    SECTION_TRAKT,
)
_LOGGER = logging.getLogger(__name__)


def _normalize_optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalize_service_url(value: Any) -> str | None:
    """Normalize service URLs and default missing scheme to http."""
    text = _normalize_optional_text(value)
    if not text:
        return None
    if "://" not in text:
        text = f"http://{text}"
    return text.rstrip("/")


def _mask_token(token: str | None) -> str:
    token_value = str(token or "").strip()
    if not token_value:
        return "not set"
    if len(token_value) <= 8:
        return "*" * len(token_value)
    return f"{token_value[:4]}...{token_value[-4:]}"


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

    for section in TMDB_KEY_SECTIONS:
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

    for section in TMDB_KEY_SECTIONS:
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


def _extract_plex_connection_from_entry(
    entry: config_entries.ConfigEntry,
) -> dict[str, Any] | None:
    server_config = entry.data.get("server_config") or {}
    base_url = _normalize_service_url(server_config.get("url") or entry.data.get("url"))
    token = _normalize_optional_text(
        server_config.get("token") or entry.data.get("token")
    )
    verify_ssl = bool(server_config.get("verify_ssl", entry.data.get("verify_ssl", True)))
    if not base_url or not token:
        return None

    return {
        "entry_id": entry.entry_id,
        "source": _friendly_plex_source_name(entry, base_url),
        "url": base_url,
        "token": token,
        "verify_ssl": verify_ssl,
    }


def _get_ha_plex_connections(hass: HomeAssistant) -> list[dict[str, Any]]:
    connections: list[dict[str, Any]] = []
    for entry in hass.config_entries.async_entries("plex"):
        parsed = _extract_plex_connection_from_entry(entry)
        if parsed:
            connections.append(parsed)
    return connections


def _build_plex_connection_options(
    connections: list[dict[str, Any]],
) -> list[selector.SelectOptionDict]:
    options: list[selector.SelectOptionDict] = []
    for connection in connections:
        entry_id = str(connection.get("entry_id", "")).strip()
        if not entry_id:
            continue

        source = str(connection.get("source", "Plex")).strip() or "Plex"
        url = str(connection.get("url", "")).strip()
        host = _host_from_url(url)
        label = source
        if host and host.lower() not in source.lower():
            label = f"{source} ({host})"

        options.append(selector.SelectOptionDict(value=entry_id, label=label))

    options.sort(key=lambda item: str(item["label"]).lower())
    return options


def _find_ha_plex_connection(
    connections: list[dict[str, Any]],
    entry_id: str | None = None,
) -> dict[str, Any] | None:
    normalized_entry_id = _normalize_optional_text(entry_id)
    if normalized_entry_id:
        for connection in connections:
            if connection.get("entry_id") == normalized_entry_id:
                return connection
        return None

    return connections[0] if connections else None


def _plex_token_status_text(
    *,
    auth_method: str,
    selected_entry_id: str | None,
    ha_plex_connections: list[dict[str, Any]],
    token: str | None,
) -> str:
    if auth_method == PLEX_AUTH_METHOD_HOME_ASSISTANT:
        selected = _find_ha_plex_connection(ha_plex_connections, selected_entry_id)
        if selected:
            server_name = str(selected.get("source") or "Plex")
            return f"managed by Home Assistant Plex ({server_name})"
        return "waiting for Home Assistant Plex server selection"

    masked = _mask_token(token)
    if masked == "not set":
        return "not generated yet"
    return f"generated ({masked})"


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
        connection = _extract_plex_connection_from_entry(entry)
        if not connection:
            continue
        base_url = connection["url"]
        token = connection["token"]
        verify_ssl = connection["verify_ssl"]

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
            section["entry_id"] = entry.entry_id
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


def _immaculaterr_watched_kind_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(
                    value="recentlyWatched", label="Zuletzt Gesehen"
                ),
                selector.SelectOptionDict(
                    value="changeOfTaste", label="Geändertes Genre"
                ),
            ],
            mode=selector.SelectSelectorMode.LIST,
        )
    )


def _trakt_trending_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(value="both", label="Movies + Shows"),
                selector.SelectOptionDict(value="movies", label="Movies"),
                selector.SelectOptionDict(value="shows", label="Shows"),
            ],
            mode=selector.SelectSelectorMode.LIST,
        )
    )


def _plex_auth_method_selector() -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                selector.SelectOptionDict(
                    value=PLEX_AUTH_METHOD_HOME_ASSISTANT,
                    label="Home Assistant Plex integration",
                ),
                selector.SelectOptionDict(
                    value=PLEX_AUTH_METHOD_PLEX_ACCOUNT,
                    label="Plex account login (PIN)",
                ),
            ],
            mode=selector.SelectSelectorMode.LIST,
        )
    )


def _build_plex_headers(
    client_identifier: str,
    *,
    token: str | None = None,
) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "X-Plex-Product": "Mediarr",
        "X-Plex-Version": "1.0.0",
        "X-Plex-Client-Identifier": client_identifier,
        "X-Plex-Platform": "Home Assistant",
        "X-Plex-Device": "Home Assistant",
        "X-Plex-Device-Name": "Mediarr",
    }
    if token:
        headers["X-Plex-Token"] = token
    return headers


def _build_plex_auth_url(
    *,
    client_identifier: str,
    pin_code: str,
    forward_url: str | None = None,
) -> str:
    params = {
        "clientID": client_identifier,
        "code": pin_code,
        "context[device][product]": "Mediarr",
        "context[device][platform]": "Home Assistant",
        "context[device][device]": "Home Assistant",
        "context[device][version]": "1.0.0",
    }
    if forward_url:
        params["forwardUrl"] = forward_url
    return f"https://app.plex.tv/auth#?{urlencode(params)}"


def _build_plex_forward_url(hass: HomeAssistant, flow_id: str | None) -> str | None:
    """Build absolute callback URL for Plex auth redirect."""
    if not flow_id:
        return None

    base_url = _normalize_optional_text(getattr(hass.config, "external_url", None))
    if not base_url:
        base_url = _normalize_optional_text(getattr(hass.config, "internal_url", None))
    if not base_url:
        return None

    return f"{base_url.rstrip('/')}{PLEX_AUTH_CALLBACK_PATH}?flow_id={flow_id}"


async def _async_create_plex_pin(
    hass: HomeAssistant,
    *,
    client_identifier: str,
    forward_url: str | None = None,
) -> dict[str, Any]:
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(15):
        async with session.post(
            "https://plex.tv/api/v2/pins",
            params={"strong": "true"},
            headers=_build_plex_headers(client_identifier),
        ) as response:
            if response.status not in (200, 201):
                body = await response.text()
                raise RuntimeError(
                    f"Plex PIN creation failed (status={response.status}, response={body})"
                )
            payload = await response.json()

    pin_id = payload.get("id")
    code = payload.get("code")
    auth_url = payload.get("authUrl")
    if not pin_id or not code:
        raise RuntimeError("Plex PIN response missing id/code")

    computed_auth_url = _build_plex_auth_url(
        client_identifier=client_identifier,
        pin_code=str(code),
        forward_url=forward_url,
    )
    if not forward_url and auth_url:
        computed_auth_url = str(auth_url)

    return {
        "id": str(pin_id),
        "code": str(code),
        "auth_url": computed_auth_url,
    }


async def _async_poll_plex_pin_for_token(
    hass: HomeAssistant,
    *,
    client_identifier: str,
    pin_id: str,
) -> str | None:
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(15):
        async with session.get(
            f"https://plex.tv/api/v2/pins/{pin_id}",
            headers=_build_plex_headers(client_identifier),
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(
                    f"Plex PIN poll failed (status={response.status}, response={body})"
                )
            payload = await response.json()
    token = _normalize_optional_text(payload.get("authToken"))
    return token


def _parse_plex_server_resources(payload: Any) -> list[dict[str, Any]]:
    resources_raw: list[dict[str, Any]] = []
    if isinstance(payload, list):
        resources_raw = [item for item in payload if isinstance(item, dict)]
    elif isinstance(payload, dict):
        if isinstance(payload.get("MediaContainer"), dict):
            devices = payload["MediaContainer"].get("Device")
            if isinstance(devices, list):
                resources_raw = [item for item in devices if isinstance(item, dict)]
        elif isinstance(payload.get("resources"), list):
            resources_raw = [
                item for item in payload["resources"] if isinstance(item, dict)
            ]
        elif isinstance(payload.get("devices"), list):
            resources_raw = [
                item for item in payload["devices"] if isinstance(item, dict)
            ]

    parsed_resources: list[dict[str, Any]] = []
    for resource in resources_raw:
        provides = str(resource.get("provides") or "").lower()
        provides_parts = {part.strip() for part in provides.split(",") if part.strip()}
        if "server" not in provides_parts:
            continue

        connections_raw = resource.get("connections")
        if not isinstance(connections_raw, list):
            connections_raw = resource.get("Connection")
        connections: list[dict[str, Any]] = []
        if isinstance(connections_raw, list):
            for connection in connections_raw:
                if not isinstance(connection, dict):
                    continue
                protocol = _normalize_optional_text(connection.get("protocol")) or "http"
                address = _normalize_optional_text(connection.get("address"))
                port = _normalize_optional_text(connection.get("port"))
                uri = _normalize_service_url(connection.get("uri"))
                if not uri:
                    if address and port:
                        uri = _normalize_service_url(f"{protocol}://{address}:{port}")
                if not uri:
                    continue
                address_uri = (
                    _normalize_service_url(f"{protocol}://{address}:{port}")
                    if address and port
                    else None
                )
                connections.append(
                    {
                        "uri": uri,
                        "address_uri": address_uri,
                        "is_plex_direct": ".plex.direct" in str(uri).lower(),
                        "local": bool(connection.get("local")),
                        "relay": bool(connection.get("relay")),
                    }
                )

        if not connections:
            continue

        parsed_resources.append(
            {
                "client_identifier": _normalize_optional_text(
                    resource.get("clientIdentifier")
                )
                or "",
                "name": _normalize_optional_text(resource.get("name"))
                or _normalize_optional_text(resource.get("sourceTitle"))
                or "Plex server",
                "owned": bool(resource.get("owned", False)),
                "connections": connections,
            }
        )

    parsed_resources.sort(
        key=lambda item: (
            not bool(item.get("owned")),
            str(item.get("name", "")).lower(),
        )
    )
    return parsed_resources


def _pick_preferred_plex_connection(resource: dict[str, Any]) -> dict[str, Any] | None:
    connections = resource.get("connections")
    if not isinstance(connections, list):
        return None

    candidates = [candidate for candidate in connections if isinstance(candidate, dict)]
    if not candidates:
        return None

    candidates.sort(
        key=lambda connection: (
            not bool(connection.get("local")),
            bool(connection.get("relay")),
            bool(connection.get("is_plex_direct")),
            not str(connection.get("uri", "")).startswith("https://"),
        )
    )
    selected = dict(candidates[0])
    if (
        bool(selected.get("local"))
        and bool(selected.get("is_plex_direct"))
        and selected.get("address_uri")
    ):
        selected["uri"] = selected["address_uri"]
    return selected


async def _async_fetch_plex_server_resources(
    hass: HomeAssistant,
    *,
    client_identifier: str,
    plex_token: str,
) -> list[dict[str, Any]]:
    session = async_get_clientsession(hass)
    async with async_timeout.timeout(15):
        async with session.get(
            "https://plex.tv/api/v2/resources",
            params={"includeHttps": "1", "includeRelay": "1"},
            headers=_build_plex_headers(client_identifier, token=plex_token),
        ) as response:
            if response.status != 200:
                body = await response.text()
                raise RuntimeError(
                    f"Plex resources fetch failed (status={response.status}, response={body})"
                )
            payload = await response.json()
    return _parse_plex_server_resources(payload)


def _plex_server_select_schema(
    resources: list[dict[str, Any]],
    *,
    default_index: str = "0",
) -> vol.Schema:
    options = [
        selector.SelectOptionDict(
            value=str(idx),
            label=str(resource.get("name", "Plex server")),
        )
        for idx, resource in enumerate(resources)
    ]
    return vol.Schema(
        {
            vol.Required("server_index", default=default_index): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _plex_login_action_schema(
    *,
    token: str | None,
    allow_skip: bool,
) -> vol.Schema:
    """Render Plex auth action form with read-only token display."""
    token_display_value = str(token or "").strip()
    action_options = [selector.SelectOptionDict(value="oauth", label="OAuth")]
    if allow_skip:
        action_options.append(selector.SelectOptionDict(value="skip", label="Skip"))
    default_action = "skip" if allow_skip else "oauth"

    return vol.Schema(
        {
            vol.Optional(
                "token_display",
                default=token_display_value,
            ): str,
            vol.Required("auth_action", default=default_action): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=action_options,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
        }
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
        self._ha_plex_connections: list[dict[str, Any]] = []
        self._ha_plex_connections_loaded = False
        self._plex_client_identifier = uuid.uuid4().hex
        self._pending_plex_config: dict[str, Any] = {}
        self._plex_pin_payload: dict[str, Any] | None = None
        self._plex_auth_token: str | None = None
        self._plex_server_resources: list[dict[str, Any]] = []
        self._plex_pin_poll_task: asyncio.Task[Any] | None = None

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
            "enable_watched_collection": bool(user_input.get("enable_watched_collection", False)),
            "watched_collection_kind": user_input.get("watched_collection_kind", "recentlyWatched"),
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

    async def async_step_plex(self, user_input: dict[str, Any] | None = None):
        """Configure Plex sensor."""
        errors: dict[str, str] = {}
        self._load_ha_plex_connections()
        draft_auth_method = str(
            (user_input or {}).get(
                PLEX_AUTH_METHOD_FIELD,
                self._pending_plex_config.get(
                    PLEX_AUTH_METHOD_FIELD,
                    PLEX_AUTH_METHOD_HOME_ASSISTANT
                    if self._ha_plex_connections
                    else PLEX_AUTH_METHOD_PLEX_ACCOUNT,
                ),
            )
        )
        draft_entry_id = _normalize_optional_text(
            (user_input or {}).get("plex_entry_id")
            or self._pending_plex_config.get("plex_entry_id")
        )
        token_status = _plex_token_status_text(
            auth_method=draft_auth_method,
            selected_entry_id=draft_entry_id,
            ha_plex_connections=self._ha_plex_connections,
            token=self._plex_auth_token,
        )
        description_placeholders = {"token_status": token_status}

        if user_input is None:
            return self.async_show_form(
                step_id="plex",
                data_schema=self._plex_schema(self._ha_plex_connections),
                errors=errors,
                description_placeholders=description_placeholders,
            )

        tmdb_api_key = self._effective_tmdb_api_key()
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_dependency"
            return self.async_show_form(
                step_id="plex",
                data_schema=self._plex_schema(self._ha_plex_connections),
                errors=errors,
                description_placeholders=description_placeholders,
            )

        auth_method = str(
            user_input.get(PLEX_AUTH_METHOD_FIELD, PLEX_AUTH_METHOD_HOME_ASSISTANT)
        )
        max_items = user_input["max_items"]
        language = user_input["language"].strip() or "en"
        selected_entry_id = _normalize_optional_text(user_input.get("plex_entry_id"))

        self._pending_plex_config = {
            PLEX_AUTH_METHOD_FIELD: auth_method,
            "plex_entry_id": selected_entry_id,
            "max_items": max_items,
            "language": language,
            TMDB_KEY_FIELD: tmdb_api_key,
        }

        if auth_method == PLEX_AUTH_METHOD_HOME_ASSISTANT:
            selected_ha_connection = _find_ha_plex_connection(
                self._ha_plex_connections,
                selected_entry_id,
            )
            if not selected_ha_connection:
                errors["base"] = "missing_ha_plex_entry"
                return self.async_show_form(
                    step_id="plex",
                    data_schema=self._plex_schema(self._ha_plex_connections),
                    errors=errors,
                    description_placeholders=description_placeholders,
                )

            self._data[SECTION_PLEX] = {
                PLEX_AUTH_METHOD_FIELD: PLEX_AUTH_METHOD_HOME_ASSISTANT,
                "use_ha_plex": True,
                "plex_entry_id": selected_ha_connection.get("entry_id"),
                "url": selected_ha_connection["url"],
                "token": selected_ha_connection["token"],
                "verify_ssl": bool(selected_ha_connection.get("verify_ssl", True)),
                TMDB_KEY_FIELD: tmdb_api_key,
                "max_items": max_items,
                "language": language,
            }
            return await self._next_step()

        existing_token = _normalize_optional_text(
            (self._data.get(SECTION_PLEX) or {}).get("token")
        )
        self._plex_pin_payload = None
        self._plex_auth_token = existing_token
        self._plex_server_resources = []
        self._cancel_plex_pin_poll_task()
        return await self.async_step_plex_login()

    def _cancel_plex_pin_poll_task(self) -> None:
        """Cancel pending background Plex PIN polling task."""
        task = self._plex_pin_poll_task
        if task and not task.done():
            task.cancel()
        self._plex_pin_poll_task = None

    def _start_plex_pin_poll_task(self) -> None:
        """Start background task that auto-resumes flow after Plex auth."""
        self._cancel_plex_pin_poll_task()
        self._plex_pin_poll_task = self.hass.async_create_task(
            self._async_wait_for_plex_pin_and_resume()
        )

    async def _async_wait_for_plex_pin_and_resume(self) -> None:
        """Poll Plex PIN token in background and resume the flow when ready."""
        if not self._plex_pin_payload or not self.flow_id:
            return

        pin_id = _normalize_optional_text(self._plex_pin_payload.get("id"))
        if not pin_id:
            return

        try:
            # Keep this generous to cover slower browser login roundtrips.
            for _ in range(180):
                if self._plex_auth_token:
                    break
                token = await _async_poll_plex_pin_for_token(
                    self.hass,
                    client_identifier=self._plex_client_identifier,
                    pin_id=pin_id,
                )
                if token:
                    self._plex_auth_token = token
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # pragma: no cover - best effort fallback path
            _LOGGER.debug("Background Plex PIN polling failed: %s", err)
            return

        if not self._plex_auth_token:
            return

        resumed = await async_resume_data_entry_flow(
            self.hass,
            flow_id=self.flow_id,
            user_input={"callback": True},
        )
        if not resumed:
            _LOGGER.debug("Could not auto-resume flow %s after Plex auth", self.flow_id)

    async def async_step_plex_login(self, user_input: dict[str, Any] | None = None):
        """Handle Plex authentication actions (OAuth / Skip)."""
        errors: dict[str, str] = {}
        schema = _plex_login_action_schema(
            token=self._plex_auth_token,
            allow_skip=bool(self._plex_auth_token),
        )
        placeholders = {"token_status": _mask_token(self._plex_auth_token)}

        if user_input is None:
            return self.async_show_form(
                step_id="plex_login",
                data_schema=schema,
                errors=errors,
                description_placeholders=placeholders,
            )

        action = str(user_input.get("auth_action", "oauth"))
        if action == "skip":
            self._cancel_plex_pin_poll_task()
            if not self._plex_auth_token:
                errors["base"] = "plex_auth_pending"
                return self.async_show_form(
                    step_id="plex_login",
                    data_schema=schema,
                    errors=errors,
                    description_placeholders=placeholders,
                )
            return await self._continue_with_plex_account_token()

        try:
            self._plex_pin_payload = await _async_create_plex_pin(
                self.hass,
                client_identifier=self._plex_client_identifier,
                forward_url=_build_plex_forward_url(self.hass, self.flow_id),
            )
        except Exception as err:
            _LOGGER.error("Failed to create Plex PIN: %s", err)
            errors["base"] = "plex_pin_init_failed"
            return self.async_show_form(
                step_id="plex_login",
                data_schema=schema,
                errors=errors,
                description_placeholders=placeholders,
            )

        self._start_plex_pin_poll_task()
        return self.async_external_step(
            step_id="plex_login_external",
            url=str(self._plex_pin_payload.get("auth_url", "")),
        )

    async def async_step_plex_login_external(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle return from external Plex login."""
        del user_input
        return self.async_external_step_done(next_step_id="plex_login_finish")

    async def async_step_plex_login_finish(
        self, user_input: dict[str, Any] | None = None
    ):
        """Finalize Plex login after external step."""
        del user_input
        if not self._plex_pin_payload:
            return await self.async_step_plex_login()

        if not self._plex_auth_token:
            try:
                token: str | None = None
                for _ in range(20):
                    token = await _async_poll_plex_pin_for_token(
                        self.hass,
                        client_identifier=self._plex_client_identifier,
                        pin_id=self._plex_pin_payload["id"],
                    )
                    if token:
                        break
                    await asyncio.sleep(1)
                self._plex_auth_token = token
            except Exception as err:
                _LOGGER.error("Failed to poll Plex PIN: %s", err)
                return self._show_plex_login_action_error("plex_pin_poll_failed")

        if not self._plex_auth_token:
            return self._show_plex_login_action_error("plex_auth_pending")
        return await self._continue_with_plex_account_token()

    async def _continue_with_plex_account_token(self):
        """Load Plex servers using current token and continue flow."""
        self._cancel_plex_pin_poll_task()
        if not self._plex_auth_token:
            return self._show_plex_login_action_error("plex_auth_pending")

        try:
            self._plex_server_resources = await _async_fetch_plex_server_resources(
                self.hass,
                client_identifier=self._plex_client_identifier,
                plex_token=self._plex_auth_token,
            )
        except Exception as err:
            _LOGGER.error("Failed to load Plex servers: %s", err)
            return self._show_plex_login_action_error("plex_server_fetch_failed")

        if not self._plex_server_resources:
            return self._show_plex_login_action_error("plex_no_servers_found")
        if len(self._plex_server_resources) == 1:
            return await self._finish_plex_account_auth(self._plex_server_resources[0])
        return await self.async_step_plex_server()

    def _show_plex_login_action_error(self, error_key: str):
        """Show an error on the Plex auth action page."""
        return self.async_show_form(
            step_id="plex_login",
            data_schema=_plex_login_action_schema(
                token=self._plex_auth_token,
                allow_skip=bool(self._plex_auth_token),
            ),
            errors={"base": error_key},
            description_placeholders={"token_status": _mask_token(self._plex_auth_token)},
        )

    async def async_step_plex_server(self, user_input: dict[str, Any] | None = None):
        """Select Plex server after successful account authentication."""
        if not self._plex_server_resources:
            return await self.async_step_plex_login()

        schema = _plex_server_select_schema(self._plex_server_resources)
        if user_input is None:
            return self.async_show_form(step_id="plex_server", data_schema=schema)

        try:
            index = int(str(user_input["server_index"]))
            selected_server = self._plex_server_resources[index]
        except (ValueError, KeyError, IndexError):
            return self.async_show_form(
                step_id="plex_server",
                data_schema=schema,
                errors={"base": "plex_invalid_server_selection"},
            )
        return await self._finish_plex_account_auth(selected_server)

    async def _finish_plex_account_auth(self, server_resource: dict[str, Any]):
        connection = _pick_preferred_plex_connection(server_resource)
        if not connection or not connection.get("uri") or not self._plex_auth_token:
            return self.async_show_form(
                step_id="plex_server",
                data_schema=_plex_server_select_schema(self._plex_server_resources),
                errors={"base": "plex_invalid_server_selection"},
            )

        pending = dict(self._pending_plex_config)
        tmdb_api_key = pending.get(TMDB_KEY_FIELD)
        self._data[SECTION_PLEX] = {
            PLEX_AUTH_METHOD_FIELD: PLEX_AUTH_METHOD_PLEX_ACCOUNT,
            "use_ha_plex": False,
            "plex_entry_id": None,
            "url": str(connection["uri"]),
            "token": str(self._plex_auth_token),
            "verify_ssl": str(connection["uri"]).startswith("https://"),
            TMDB_KEY_FIELD: tmdb_api_key,
            "max_items": pending.get("max_items", DEFAULT_MAX_ITEMS),
            "language": pending.get("language", "en"),
        }
        return await self._next_step()

    async def async_step_jellyfin(self, user_input: dict[str, Any] | None = None):
        """Configure Jellyfin sensor."""
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="jellyfin",
                data_schema=self._jellyfin_schema(),
                errors=errors,
            )

        tmdb_api_key = self._effective_tmdb_api_key()
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_dependency"
            return self.async_show_form(
                step_id="jellyfin",
                data_schema=self._jellyfin_schema(),
                errors=errors,
            )

        self._data[SECTION_JELLYFIN] = {
            "url": user_input["url"].strip(),
            "token": user_input["token"].strip(),
            TMDB_KEY_FIELD: tmdb_api_key,
            "max_items": user_input["max_items"],
            "language": user_input["language"].strip() or "en",
        }
        return await self._next_step()

    async def async_step_sonarr(self, user_input: dict[str, Any] | None = None):
        """Configure Sonarr sensor."""
        if user_input is None:
            return self.async_show_form(
                step_id="sonarr",
                data_schema=self._sonarr_schema(),
                errors={},
            )

        self._data[SECTION_SONARR] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_sonarr2(self, user_input: dict[str, Any] | None = None):
        """Configure Sonarr2 sensor."""
        if user_input is None:
            return self.async_show_form(
                step_id="sonarr2",
                data_schema=self._sonarr_schema(),
                errors={},
            )

        self._data[SECTION_SONARR2] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_radarr(self, user_input: dict[str, Any] | None = None):
        """Configure Radarr sensor."""
        if user_input is None:
            return self.async_show_form(
                step_id="radarr",
                data_schema=self._radarr_schema(),
                errors={},
            )

        self._data[SECTION_RADARR] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_radarr2(self, user_input: dict[str, Any] | None = None):
        """Configure Radarr2 sensor."""
        if user_input is None:
            return self.async_show_form(
                step_id="radarr2",
                data_schema=self._radarr_schema(),
                errors={},
            )

        self._data[SECTION_RADARR2] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_trakt(self, user_input: dict[str, Any] | None = None):
        """Configure Trakt sensor."""
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="trakt",
                data_schema=self._trakt_schema(),
                errors=errors,
            )

        tmdb_api_key = self._effective_tmdb_api_key()
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_dependency"
            return self.async_show_form(
                step_id="trakt",
                data_schema=self._trakt_schema(),
                errors=errors,
            )

        self._data[SECTION_TRAKT] = {
            "client_id": user_input["client_id"].strip(),
            "client_secret": user_input["client_secret"].strip(),
            "trending_type": user_input["trending_type"],
            "max_items": user_input["max_items"],
            TMDB_KEY_FIELD: tmdb_api_key,
        }
        return await self._next_step()

    def _user_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional("title", default="Mediarr"): str,
                vol.Optional(FIELD_ENABLE_SEER, default=True): bool,
                vol.Optional(FIELD_ENABLE_IMMACULATERR, default=False): bool,
                vol.Optional(FIELD_ENABLE_TMDB, default=False): bool,
                vol.Optional(FIELD_ENABLE_PLEX, default=False): bool,
                vol.Optional(FIELD_ENABLE_JELLYFIN, default=False): bool,
                vol.Optional(FIELD_ENABLE_SONARR, default=False): bool,
                vol.Optional(FIELD_ENABLE_SONARR2, default=False): bool,
                vol.Optional(FIELD_ENABLE_RADARR, default=False): bool,
                vol.Optional(FIELD_ENABLE_RADARR2, default=False): bool,
                vol.Optional(FIELD_ENABLE_TRAKT, default=False): bool,
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

        schema[vol.Optional("enable_watched_collection", default=False)] = bool
        schema[vol.Optional(
            "watched_collection_kind", default="recentlyWatched"
        )] = _immaculaterr_watched_kind_selector()

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

    def _plex_schema(
        self,
        ha_plex_connections: list[dict[str, Any]] | None = None,
    ) -> vol.Schema:
        connection_options = _build_plex_connection_options(ha_plex_connections or [])
        default_auth_method = (
            PLEX_AUTH_METHOD_HOME_ASSISTANT
            if connection_options
            else PLEX_AUTH_METHOD_PLEX_ACCOUNT
        )
        default_entry_id = str(connection_options[0]["value"]) if connection_options else ""
        schema: dict[Any, Any] = {
            vol.Required(
                PLEX_AUTH_METHOD_FIELD,
                default=default_auth_method,
            ): _plex_auth_method_selector(),
        }
        if connection_options:
            schema[vol.Optional("plex_entry_id", default=default_entry_id)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=connection_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        schema[vol.Required("max_items", default=DEFAULT_MAX_ITEMS)] = _int_field()
        schema[vol.Optional("language", default="en")] = str
        return vol.Schema(schema)

    def _jellyfin_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url"): str,
                vol.Required("token"): str,
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Optional("language", default="en"): str,
            }
        )

    def _sonarr_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url"): str,
                vol.Required("api_key"): str,
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Required("days_to_check", default=DEFAULT_DAYS): _int_field(1, 365),
            }
        )

    def _radarr_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url"): str,
                vol.Required("api_key"): str,
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
                vol.Required("days_to_check", default=DEFAULT_DAYS): _int_field(1, 365),
            }
        )

    def _trakt_schema(self) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("client_id"): str,
                vol.Required("client_secret"): str,
                vol.Required("trending_type", default="both"): _trakt_trending_selector(),
                vol.Required("max_items", default=DEFAULT_MAX_ITEMS): _int_field(),
            }
        )

    def _selected_sections(self, user_input: dict[str, Any]) -> list[str]:
        sections: list[str] = []
        if user_input.get(FIELD_ENABLE_TMDB):
            sections.append(SECTION_TMDB)
        if user_input.get(FIELD_ENABLE_PLEX):
            sections.append(SECTION_PLEX)
        if user_input.get(FIELD_ENABLE_JELLYFIN):
            sections.append(SECTION_JELLYFIN)
        if user_input.get(FIELD_ENABLE_TRAKT):
            sections.append(SECTION_TRAKT)
        if user_input.get(FIELD_ENABLE_SEER):
            sections.append(SECTION_SEER)
        if user_input.get(FIELD_ENABLE_IMMACULATERR):
            sections.append(SECTION_IMMACULATERR)
        if user_input.get(FIELD_ENABLE_SONARR):
            sections.append(SECTION_SONARR)
        if user_input.get(FIELD_ENABLE_SONARR2):
            sections.append(SECTION_SONARR2)
        if user_input.get(FIELD_ENABLE_RADARR):
            sections.append(SECTION_RADARR)
        if user_input.get(FIELD_ENABLE_RADARR2):
            sections.append(SECTION_RADARR2)
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

    def _load_ha_plex_connections(self) -> None:
        if self._ha_plex_connections_loaded:
            return
        self._ha_plex_connections = _get_ha_plex_connections(self.hass)
        self._ha_plex_connections_loaded = True


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
        self._ha_plex_connections: list[dict[str, Any]] = []
        self._ha_plex_connections_loaded = False
        self._plex_client_identifier = uuid.uuid4().hex
        self._pending_plex_config: dict[str, Any] = {}
        self._plex_pin_payload: dict[str, Any] | None = None
        self._plex_auth_token: str | None = None
        self._plex_server_resources: list[dict[str, Any]] = []
        self._plex_pin_poll_task: asyncio.Task[Any] | None = None

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
            "enable_watched_collection": bool(user_input.get("enable_watched_collection", False)),
            "watched_collection_kind": user_input.get("watched_collection_kind", "recentlyWatched"),
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

    async def async_step_plex(self, user_input: dict[str, Any] | None = None):
        """Configure Plex in options."""
        defaults = self._base_config.get(SECTION_PLEX) or {}
        errors: dict[str, str] = {}
        self._load_ha_plex_connections()
        draft_auth_method = str(
            (user_input or {}).get(
                PLEX_AUTH_METHOD_FIELD,
                _normalize_optional_text(defaults.get(PLEX_AUTH_METHOD_FIELD))
                or (
                    PLEX_AUTH_METHOD_HOME_ASSISTANT
                    if bool(defaults.get("use_ha_plex"))
                    else PLEX_AUTH_METHOD_PLEX_ACCOUNT
                ),
            )
        )
        draft_entry_id = _normalize_optional_text(
            (user_input or {}).get("plex_entry_id") or defaults.get("plex_entry_id")
        )
        token_status = _plex_token_status_text(
            auth_method=draft_auth_method,
            selected_entry_id=draft_entry_id,
            ha_plex_connections=self._ha_plex_connections,
            token=_normalize_optional_text(defaults.get("token")) or self._plex_auth_token,
        )
        description_placeholders = {"token_status": token_status}

        if user_input is None:
            return self.async_show_form(
                step_id="plex",
                data_schema=self._plex_schema(defaults, self._ha_plex_connections),
                errors=errors,
                description_placeholders=description_placeholders,
            )

        tmdb_api_key = self._effective_tmdb_api_key()
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_dependency"
            return self.async_show_form(
                step_id="plex",
                data_schema=self._plex_schema(defaults, self._ha_plex_connections),
                errors=errors,
                description_placeholders=description_placeholders,
            )

        fallback_method = _normalize_optional_text(
            defaults.get(PLEX_AUTH_METHOD_FIELD)
        )
        if not fallback_method:
            fallback_method = (
                PLEX_AUTH_METHOD_HOME_ASSISTANT
                if bool(defaults.get("use_ha_plex"))
                else PLEX_AUTH_METHOD_PLEX_ACCOUNT
            )
        auth_method = str(
            user_input.get(PLEX_AUTH_METHOD_FIELD, fallback_method)
        )
        max_items = user_input["max_items"]
        language = user_input["language"].strip() or "en"
        selected_entry_id = _normalize_optional_text(
            user_input.get("plex_entry_id") or defaults.get("plex_entry_id")
        )

        self._pending_plex_config = {
            PLEX_AUTH_METHOD_FIELD: auth_method,
            "plex_entry_id": selected_entry_id,
            "max_items": max_items,
            "language": language,
            TMDB_KEY_FIELD: tmdb_api_key,
        }

        if auth_method == PLEX_AUTH_METHOD_HOME_ASSISTANT:
            selected_ha_connection = _find_ha_plex_connection(
                self._ha_plex_connections,
                selected_entry_id,
            )
            if not selected_ha_connection:
                errors["base"] = "missing_ha_plex_entry"
                return self.async_show_form(
                    step_id="plex",
                    data_schema=self._plex_schema(defaults, self._ha_plex_connections),
                    errors=errors,
                    description_placeholders=description_placeholders,
                )
            self._data[SECTION_PLEX] = {
                PLEX_AUTH_METHOD_FIELD: PLEX_AUTH_METHOD_HOME_ASSISTANT,
                "use_ha_plex": True,
                "plex_entry_id": selected_ha_connection.get("entry_id"),
                "url": selected_ha_connection["url"],
                "token": selected_ha_connection["token"],
                "verify_ssl": bool(selected_ha_connection.get("verify_ssl", True)),
                TMDB_KEY_FIELD: tmdb_api_key,
                "max_items": max_items,
                "language": language,
            }
            return await self._next_step()

        self._plex_pin_payload = None
        self._plex_auth_token = _normalize_optional_text(defaults.get("token"))
        self._plex_server_resources = []
        self._cancel_plex_pin_poll_task()
        return await self.async_step_plex_login()

    def _cancel_plex_pin_poll_task(self) -> None:
        """Cancel pending background Plex PIN polling task."""
        task = self._plex_pin_poll_task
        if task and not task.done():
            task.cancel()
        self._plex_pin_poll_task = None

    def _start_plex_pin_poll_task(self) -> None:
        """Start background task that auto-resumes options flow after Plex auth."""
        self._cancel_plex_pin_poll_task()
        self._plex_pin_poll_task = self.hass.async_create_task(
            self._async_wait_for_plex_pin_and_resume()
        )

    async def _async_wait_for_plex_pin_and_resume(self) -> None:
        """Poll Plex PIN token in background and resume options flow when ready."""
        if not self._plex_pin_payload or not self.flow_id:
            return

        pin_id = _normalize_optional_text(self._plex_pin_payload.get("id"))
        if not pin_id:
            return

        try:
            for _ in range(180):
                if self._plex_auth_token:
                    break
                token = await _async_poll_plex_pin_for_token(
                    self.hass,
                    client_identifier=self._plex_client_identifier,
                    pin_id=pin_id,
                )
                if token:
                    self._plex_auth_token = token
                    break
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        except Exception as err:  # pragma: no cover - best effort fallback path
            _LOGGER.debug("Background Plex PIN polling failed in options: %s", err)
            return

        if not self._plex_auth_token:
            return

        resumed = await async_resume_data_entry_flow(
            self.hass,
            flow_id=self.flow_id,
            user_input={"callback": True},
        )
        if not resumed:
            _LOGGER.debug(
                "Could not auto-resume options flow %s after Plex auth", self.flow_id
            )

    async def async_step_plex_login(self, user_input: dict[str, Any] | None = None):
        """Handle Plex authentication actions in options flow."""
        errors: dict[str, str] = {}
        schema = _plex_login_action_schema(
            token=self._plex_auth_token,
            allow_skip=bool(self._plex_auth_token),
        )
        placeholders = {"token_status": _mask_token(self._plex_auth_token)}

        if user_input is None:
            return self.async_show_form(
                step_id="plex_login",
                data_schema=schema,
                errors=errors,
                description_placeholders=placeholders,
            )

        action = str(user_input.get("auth_action", "oauth"))
        if action == "skip":
            self._cancel_plex_pin_poll_task()
            if not self._plex_auth_token:
                errors["base"] = "plex_auth_pending"
                return self.async_show_form(
                    step_id="plex_login",
                    data_schema=schema,
                    errors=errors,
                    description_placeholders=placeholders,
                )
            return await self._continue_with_plex_account_token_options()

        try:
            self._plex_pin_payload = await _async_create_plex_pin(
                self.hass,
                client_identifier=self._plex_client_identifier,
                forward_url=_build_plex_forward_url(self.hass, self.flow_id),
            )
        except Exception as err:
            _LOGGER.error("Failed to create Plex PIN in options: %s", err)
            errors["base"] = "plex_pin_init_failed"
            return self.async_show_form(
                step_id="plex_login",
                data_schema=schema,
                errors=errors,
                description_placeholders=placeholders,
            )

        self._start_plex_pin_poll_task()
        return self.async_external_step(
            step_id="plex_login_external",
            url=str(self._plex_pin_payload.get("auth_url", "")),
        )

    async def async_step_plex_login_external(
        self, user_input: dict[str, Any] | None = None
    ):
        """Handle return from external Plex login in options flow."""
        del user_input
        return self.async_external_step_done(next_step_id="plex_login_finish")

    async def async_step_plex_login_finish(
        self, user_input: dict[str, Any] | None = None
    ):
        """Finalize Plex login in options flow."""
        del user_input
        if not self._plex_pin_payload:
            return await self.async_step_plex_login()

        if not self._plex_auth_token:
            try:
                token: str | None = None
                for _ in range(20):
                    token = await _async_poll_plex_pin_for_token(
                        self.hass,
                        client_identifier=self._plex_client_identifier,
                        pin_id=self._plex_pin_payload["id"],
                    )
                    if token:
                        break
                    await asyncio.sleep(1)
                self._plex_auth_token = token
            except Exception as err:
                _LOGGER.error("Failed to poll Plex PIN in options: %s", err)
                return self._show_plex_login_action_error_options("plex_pin_poll_failed")

        if not self._plex_auth_token:
            return self._show_plex_login_action_error_options("plex_auth_pending")
        return await self._continue_with_plex_account_token_options()

    async def _continue_with_plex_account_token_options(self):
        """Load Plex servers using current token and continue options flow."""
        self._cancel_plex_pin_poll_task()
        if not self._plex_auth_token:
            return self._show_plex_login_action_error_options("plex_auth_pending")

        try:
            self._plex_server_resources = await _async_fetch_plex_server_resources(
                self.hass,
                client_identifier=self._plex_client_identifier,
                plex_token=self._plex_auth_token,
            )
        except Exception as err:
            _LOGGER.error("Failed to load Plex servers in options: %s", err)
            return self._show_plex_login_action_error_options("plex_server_fetch_failed")

        if not self._plex_server_resources:
            return self._show_plex_login_action_error_options("plex_no_servers_found")
        if len(self._plex_server_resources) == 1:
            return await self._finish_plex_account_auth_options(
                self._plex_server_resources[0]
            )
        return await self.async_step_plex_server()

    def _show_plex_login_action_error_options(self, error_key: str):
        """Show an error on the Plex auth action page in options flow."""
        return self.async_show_form(
            step_id="plex_login",
            data_schema=_plex_login_action_schema(
                token=self._plex_auth_token,
                allow_skip=bool(self._plex_auth_token),
            ),
            errors={"base": error_key},
            description_placeholders={"token_status": _mask_token(self._plex_auth_token)},
        )

    async def async_step_plex_server(self, user_input: dict[str, Any] | None = None):
        """Select Plex server after account authentication in options."""
        if not self._plex_server_resources:
            return await self.async_step_plex_login()

        schema = _plex_server_select_schema(self._plex_server_resources)
        if user_input is None:
            return self.async_show_form(step_id="plex_server", data_schema=schema)

        try:
            index = int(str(user_input["server_index"]))
            selected_server = self._plex_server_resources[index]
        except (ValueError, KeyError, IndexError):
            return self.async_show_form(
                step_id="plex_server",
                data_schema=schema,
                errors={"base": "plex_invalid_server_selection"},
            )
        return await self._finish_plex_account_auth_options(selected_server)

    async def _finish_plex_account_auth_options(self, server_resource: dict[str, Any]):
        connection = _pick_preferred_plex_connection(server_resource)
        if not connection or not connection.get("uri") or not self._plex_auth_token:
            return self.async_show_form(
                step_id="plex_server",
                data_schema=_plex_server_select_schema(self._plex_server_resources),
                errors={"base": "plex_invalid_server_selection"},
            )

        pending = dict(self._pending_plex_config)
        self._data[SECTION_PLEX] = {
            PLEX_AUTH_METHOD_FIELD: PLEX_AUTH_METHOD_PLEX_ACCOUNT,
            "use_ha_plex": False,
            "plex_entry_id": None,
            "url": str(connection["uri"]),
            "token": str(self._plex_auth_token),
            "verify_ssl": str(connection["uri"]).startswith("https://"),
            TMDB_KEY_FIELD: pending.get(TMDB_KEY_FIELD),
            "max_items": pending.get("max_items", DEFAULT_MAX_ITEMS),
            "language": pending.get("language", "en"),
        }
        return await self._next_step()

    async def async_step_jellyfin(self, user_input: dict[str, Any] | None = None):
        """Configure Jellyfin in options."""
        defaults = self._base_config.get(SECTION_JELLYFIN) or {}
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="jellyfin",
                data_schema=self._jellyfin_schema(defaults),
                errors=errors,
            )

        tmdb_api_key = self._effective_tmdb_api_key()
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_dependency"
            return self.async_show_form(
                step_id="jellyfin",
                data_schema=self._jellyfin_schema(defaults),
                errors=errors,
            )

        self._data[SECTION_JELLYFIN] = {
            "url": user_input["url"].strip(),
            "token": user_input["token"].strip(),
            TMDB_KEY_FIELD: tmdb_api_key,
            "max_items": user_input["max_items"],
            "language": user_input["language"].strip() or "en",
        }
        return await self._next_step()

    async def async_step_sonarr(self, user_input: dict[str, Any] | None = None):
        """Configure Sonarr in options."""
        defaults = self._base_config.get(SECTION_SONARR) or {}
        if user_input is None:
            return self.async_show_form(
                step_id="sonarr",
                data_schema=self._sonarr_schema(defaults),
                errors={},
            )

        self._data[SECTION_SONARR] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_sonarr2(self, user_input: dict[str, Any] | None = None):
        """Configure Sonarr2 in options."""
        defaults = self._base_config.get(SECTION_SONARR2) or {}
        if user_input is None:
            return self.async_show_form(
                step_id="sonarr2",
                data_schema=self._sonarr_schema(defaults),
                errors={},
            )

        self._data[SECTION_SONARR2] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_radarr(self, user_input: dict[str, Any] | None = None):
        """Configure Radarr in options."""
        defaults = self._base_config.get(SECTION_RADARR) or {}
        if user_input is None:
            return self.async_show_form(
                step_id="radarr",
                data_schema=self._radarr_schema(defaults),
                errors={},
            )

        self._data[SECTION_RADARR] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_radarr2(self, user_input: dict[str, Any] | None = None):
        """Configure Radarr2 in options."""
        defaults = self._base_config.get(SECTION_RADARR2) or {}
        if user_input is None:
            return self.async_show_form(
                step_id="radarr2",
                data_schema=self._radarr_schema(defaults),
                errors={},
            )

        self._data[SECTION_RADARR2] = {
            "url": user_input["url"].strip(),
            "api_key": user_input["api_key"].strip(),
            "max_items": user_input["max_items"],
            "days_to_check": user_input["days_to_check"],
        }
        return await self._next_step()

    async def async_step_trakt(self, user_input: dict[str, Any] | None = None):
        """Configure Trakt in options."""
        defaults = self._base_config.get(SECTION_TRAKT) or {}
        errors: dict[str, str] = {}
        if user_input is None:
            return self.async_show_form(
                step_id="trakt",
                data_schema=self._trakt_schema(defaults),
                errors=errors,
            )

        tmdb_api_key = self._effective_tmdb_api_key()
        if not tmdb_api_key:
            errors["base"] = "missing_tmdb_api_key_for_dependency"
            return self.async_show_form(
                step_id="trakt",
                data_schema=self._trakt_schema(defaults),
                errors=errors,
            )

        self._data[SECTION_TRAKT] = {
            "client_id": user_input["client_id"].strip(),
            "client_secret": user_input["client_secret"].strip(),
            "trending_type": user_input["trending_type"],
            "max_items": user_input["max_items"],
            TMDB_KEY_FIELD: tmdb_api_key,
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
                vol.Optional(
                    FIELD_ENABLE_PLEX,
                    default=bool(self._base_config.get(SECTION_PLEX)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_JELLYFIN,
                    default=bool(self._base_config.get(SECTION_JELLYFIN)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_SONARR,
                    default=bool(self._base_config.get(SECTION_SONARR)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_SONARR2,
                    default=bool(self._base_config.get(SECTION_SONARR2)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_RADARR,
                    default=bool(self._base_config.get(SECTION_RADARR)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_RADARR2,
                    default=bool(self._base_config.get(SECTION_RADARR2)),
                ): bool,
                vol.Optional(
                    FIELD_ENABLE_TRAKT,
                    default=bool(self._base_config.get(SECTION_TRAKT)),
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

        schema[vol.Optional(
            "enable_watched_collection",
            default=bool(defaults.get("enable_watched_collection", False)),
        )] = bool
        schema[vol.Optional(
            "watched_collection_kind",
            default=defaults.get("watched_collection_kind", "recentlyWatched"),
        )] = _immaculaterr_watched_kind_selector()

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

    def _plex_schema(
        self,
        defaults: dict[str, Any],
        ha_plex_connections: list[dict[str, Any]] | None = None,
    ) -> vol.Schema:
        connection_options = _build_plex_connection_options(ha_plex_connections or [])
        default_auth_method = _normalize_optional_text(
            defaults.get(PLEX_AUTH_METHOD_FIELD)
        )
        if not default_auth_method:
            default_auth_method = (
                PLEX_AUTH_METHOD_HOME_ASSISTANT
                if bool(defaults.get("use_ha_plex"))
                else PLEX_AUTH_METHOD_PLEX_ACCOUNT
            )
        if default_auth_method == PLEX_AUTH_METHOD_HOME_ASSISTANT and not connection_options:
            default_auth_method = PLEX_AUTH_METHOD_PLEX_ACCOUNT

        default_entry_id = str(defaults.get("plex_entry_id") or "")
        if connection_options:
            allowed_ids = {str(option["value"]) for option in connection_options}
            if default_entry_id not in allowed_ids:
                default_entry_id = str(connection_options[0]["value"])

        schema: dict[Any, Any] = {
            vol.Required(
                PLEX_AUTH_METHOD_FIELD,
                default=default_auth_method,
            ): _plex_auth_method_selector(),
        }
        if connection_options:
            schema[vol.Optional("plex_entry_id", default=default_entry_id)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=connection_options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
        schema[vol.Required(
            "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
        )] = _int_field()
        schema[vol.Optional("language", default=defaults.get("language", "en"))] = str
        return vol.Schema(schema)

    def _jellyfin_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url", default=defaults.get("url", "")): str,
                vol.Required("token", default=defaults.get("token", "")): str,
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Optional("language", default=defaults.get("language", "en")): str,
            }
        )

    def _sonarr_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url", default=defaults.get("url", "")): str,
                vol.Required("api_key", default=defaults.get("api_key", "")): str,
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Required(
                    "days_to_check", default=defaults.get("days_to_check", DEFAULT_DAYS)
                ): _int_field(1, 365),
            }
        )

    def _radarr_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("url", default=defaults.get("url", "")): str,
                vol.Required("api_key", default=defaults.get("api_key", "")): str,
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
                vol.Required(
                    "days_to_check", default=defaults.get("days_to_check", DEFAULT_DAYS)
                ): _int_field(1, 365),
            }
        )

    def _trakt_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Required("client_id", default=defaults.get("client_id", "")): str,
                vol.Required(
                    "client_secret", default=defaults.get("client_secret", "")
                ): str,
                vol.Required(
                    "trending_type",
                    default=defaults.get("trending_type", "both"),
                ): _trakt_trending_selector(),
                vol.Required(
                    "max_items", default=defaults.get("max_items", DEFAULT_MAX_ITEMS)
                ): _int_field(),
            }
        )

    def _selected_sections(self, user_input: dict[str, Any]) -> list[str]:
        sections: list[str] = []
        if user_input.get(FIELD_ENABLE_TMDB):
            sections.append(SECTION_TMDB)
        if user_input.get(FIELD_ENABLE_PLEX):
            sections.append(SECTION_PLEX)
        if user_input.get(FIELD_ENABLE_JELLYFIN):
            sections.append(SECTION_JELLYFIN)
        if user_input.get(FIELD_ENABLE_TRAKT):
            sections.append(SECTION_TRAKT)
        if user_input.get(FIELD_ENABLE_SEER):
            sections.append(SECTION_SEER)
        if user_input.get(FIELD_ENABLE_IMMACULATERR):
            sections.append(SECTION_IMMACULATERR)
        if user_input.get(FIELD_ENABLE_SONARR):
            sections.append(SECTION_SONARR)
        if user_input.get(FIELD_ENABLE_SONARR2):
            sections.append(SECTION_SONARR2)
        if user_input.get(FIELD_ENABLE_RADARR):
            sections.append(SECTION_RADARR)
        if user_input.get(FIELD_ENABLE_RADARR2):
            sections.append(SECTION_RADARR2)
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

    def _load_ha_plex_connections(self) -> None:
        if self._ha_plex_connections_loaded:
            return
        self._ha_plex_connections = _get_ha_plex_connections(self.hass)
        self._ha_plex_connections_loaded = True
