# mediarr/__init__.py
"""The Mediarr integration."""
from __future__ import annotations
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from .config_helpers import get_entry_config
from .services.seer_requests import (
    SeerRequestHandler,
    async_setup_services,
    async_unload_services,
)
from .services.immaculaterr_requests import (
    ImmaculaterrRequestHandler,
    async_setup_immaculaterr_services,
    async_unload_immaculaterr_services,
)

DOMAIN = "mediarr"
PLATFORMS = [Platform.SENSOR]


def _ensure_domain_data(hass: HomeAssistant) -> dict[str, Any]:
    domain_data = hass.data.setdefault(DOMAIN, {})
    domain_data.setdefault("entries", {})
    return domain_data


def _any_entry_uses(domain_data: dict[str, Any], provider: str) -> bool:
    for entry_config in domain_data.get("entries", {}).values():
        if isinstance(entry_config, dict) and entry_config.get(provider):
            return True
    return False


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the Mediarr component."""
    if DOMAIN not in config:
        return True

    domain_data = _ensure_domain_data(hass)
    domain_config = config[DOMAIN]

    seer_config = domain_config.get("seer")
    if seer_config:
        domain_data["yaml_seer_enabled"] = True
        handler = SeerRequestHandler(
            hass,
            seer_config["url"],
            seer_config["api_key"]
        )

        domain_data["seer_request_handler"] = handler
        await async_setup_services(hass, DOMAIN)

    immaculaterr_config = domain_config.get("immaculaterr")
    if immaculaterr_config:
        domain_data["yaml_immaculaterr_enabled"] = True
        handler = ImmaculaterrRequestHandler(
            immaculaterr_config["url"],
            immaculaterr_config["username"],
            immaculaterr_config["password"],
        )

        domain_data["immaculaterr_request_handler"] = handler

        await async_setup_immaculaterr_services(hass, DOMAIN)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mediarr from a config entry."""
    domain_data = _ensure_domain_data(hass)
    entry_config = get_entry_config(entry)
    domain_data["entries"][entry.entry_id] = entry_config
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    seer_config = entry_config.get("seer")
    if seer_config:
        old_handler = domain_data.get("seer_request_handler")
        if old_handler:
            await old_handler.close()
        domain_data["seer_request_handler"] = SeerRequestHandler(
            hass,
            seer_config["url"],
            seer_config["api_key"],
        )
        await async_setup_services(hass, DOMAIN)

    immaculaterr_config = entry_config.get("immaculaterr")
    if immaculaterr_config:
        old_handler = domain_data.get("immaculaterr_request_handler")
        if old_handler:
            await old_handler.close()
        domain_data["immaculaterr_request_handler"] = ImmaculaterrRequestHandler(
            immaculaterr_config["url"],
            immaculaterr_config["username"],
            immaculaterr_config["password"],
        )
        await async_setup_immaculaterr_services(hass, DOMAIN)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if not unload_ok:
        return False

    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        return True

    domain_data.get("entries", {}).pop(entry.entry_id, None)

    if (
        not _any_entry_uses(domain_data, "seer")
        and not domain_data.get("yaml_seer_enabled")
    ):
        await async_unload_services(hass, DOMAIN)
        domain_data.pop("seer_request_handler", None)

    if (
        not _any_entry_uses(domain_data, "immaculaterr")
        and not domain_data.get("yaml_immaculaterr_enabled")
    ):
        await async_unload_immaculaterr_services(hass, DOMAIN)
        domain_data.pop("immaculaterr_request_handler", None)

    if (
        not domain_data.get("entries")
        and "seer_request_handler" not in domain_data
        and "immaculaterr_request_handler" not in domain_data
    ):
        hass.data.pop(DOMAIN, None)

    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)
