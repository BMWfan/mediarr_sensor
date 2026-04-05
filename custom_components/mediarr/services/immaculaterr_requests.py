"""Home Assistant services for Immaculaterr Observatory actions."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from ..common.const import (
    ATTR_APPLY_IMMEDIATELY,
    ATTR_LIBRARY_SECTION_KEY,
    ATTR_MEDIA_TYPE,
    ATTR_SUGGESTION_ACTION,
    ATTR_SUGGESTION_ID,
    SERVICE_PROCESS_IMMACULATERR_SUGGESTION,
)
from .immaculaterr_client import ImmaculaterrClient

_LOGGER = logging.getLogger(__name__)

PROCESS_SUGGESTION_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_LIBRARY_SECTION_KEY): cv.string,
        vol.Required(ATTR_MEDIA_TYPE): vol.In(["movie", "tv"]),
        vol.Required(ATTR_SUGGESTION_ID): cv.positive_int,
        vol.Required(ATTR_SUGGESTION_ACTION): vol.In(
            ["approve", "reject", "remove", "undo", "keep"]
        ),
        vol.Optional(ATTR_APPLY_IMMEDIATELY, default=True): cv.boolean,
    }
)


class ImmaculaterrRequestHandler:
    """Thin service handler around the Immaculaterr client."""

    def __init__(self, url: str, username: str, password: str) -> None:
        self._client = ImmaculaterrClient(url, username, password)

    async def async_process_suggestion(self, call: ServiceCall) -> bool:
        try:
            media_type = call.data[ATTR_MEDIA_TYPE]
            library_section_key = call.data[ATTR_LIBRARY_SECTION_KEY]
            suggestion_id = call.data[ATTR_SUGGESTION_ID]
            action = call.data[ATTR_SUGGESTION_ACTION]
            apply_immediately = call.data.get(ATTR_APPLY_IMMEDIATELY, True)

            await self._client.async_record_decision(
                library_section_key=library_section_key,
                media_type=media_type,
                suggestion_id=suggestion_id,
                action=action,
            )

            if apply_immediately:
                await self._client.async_apply(
                    library_section_key=library_section_key,
                    media_type=media_type,
                )

            return True
        except Exception as err:
            _LOGGER.error("Error processing Immaculaterr suggestion: %s", err)
            return False

    async def close(self) -> None:
        await self._client.close()


async def async_setup_immaculaterr_services(
    hass: HomeAssistant, domain: str
) -> bool:
    """Register the Immaculaterr services if needed."""

    async def handle_process_suggestion(call: ServiceCall) -> None:
        handler = hass.data.get(domain, {}).get("immaculaterr_request_handler")
        if not handler:
            _LOGGER.error("Immaculaterr service called without a request handler")
            return
        await handler.async_process_suggestion(call)

    try:
        if not hass.services.has_service(domain, SERVICE_PROCESS_IMMACULATERR_SUGGESTION):
            hass.services.async_register(
                domain,
                SERVICE_PROCESS_IMMACULATERR_SUGGESTION,
                handle_process_suggestion,
                schema=PROCESS_SUGGESTION_SCHEMA,
            )
        return True
    except Exception as err:
        _LOGGER.error("Error setting up Immaculaterr services: %s", err)
        return False


async def async_unload_immaculaterr_services(
    hass: HomeAssistant, domain: str
) -> bool:
    handler = hass.data.get(domain, {}).get("immaculaterr_request_handler")
    if handler:
        await handler.close()

    if hass.services.has_service(domain, SERVICE_PROCESS_IMMACULATERR_SUGGESTION):
        hass.services.async_remove(domain, SERVICE_PROCESS_IMMACULATERR_SUGGESTION)

    return True
