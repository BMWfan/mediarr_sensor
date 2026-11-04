"""Delegate playback to authorized HA Plex players, retaining exact server/item IDs."""

import re
from homeassistant.auth.permissions.const import POLICY_CONTROL
from homeassistant.components import websocket_api
from homeassistant.core import Context
from homeassistant.helpers import entity_registry as er
from .library import configured_sources
from .media_details import DOMAIN, MediaDetailsError, ws_schema


def players(hass, user):
    result = []
    for entry in er.async_get(hass).entities.values():
        if (
            entry.domain != "media_player"
            or entry.platform != "plex"
            or not user.permissions.check_entity(entry.entity_id, POLICY_CONTROL)
        ):
            continue
        state = hass.states.get(entry.entity_id)
        reason = (
            "disabled"
            if getattr(entry, "disabled_by", None)
            else (
                "not_loaded"
                if not state
                else (
                    state.state
                    if state.state in {"unknown", "unavailable"}
                    else "available"
                )
            )
        )
        result.append(
            {
                "entity_id": entry.entity_id,
                "name": (
                    state.attributes.get("friendly_name", entry.entity_id)
                    if state
                    else entry.entity_id
                ),
                "available": reason == "available",
                "reason": reason,
            }
        )
    return result


async def play(hass, user, entity_id, library_key):
    allowed = next(
        (
            item
            for item in players(hass, user)
            if item["entity_id"] == entity_id and item["available"]
        ),
        None,
    )
    match = re.fullmatch(r"(\d+):(\d+)", library_key)
    sources = configured_sources(hass)
    if (
        not allowed
        or not match
        or int(match[1]) >= len(sources)
        or sources[int(match[1])]["provider"] != "plex"
    ):
        raise MediaDetailsError(
            "playback_unavailable", "Choose an available, authorized Plex player."
        )
    source = sources[int(match[1])]
    identity = (
        (await hass.data[DOMAIN]["library_client"].get(source, "/identity"))
        .get("MediaContainer", {})
        .get("machineIdentifier", "")
    )
    if not isinstance(identity, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]{1,128}", identity
    ):
        raise MediaDetailsError(
            "playback_unavailable", "The Plex server could not be identified."
        )
    try:
        await hass.services.async_call(
            "media_player",
            "play_media",
            {
                "entity_id": entity_id,
                "media_content_type": "plex",
                "media_content_id": f"plex://{identity}/{match[2]}",
            },
            blocking=True,
            context=Context(user_id=user.id),
        )
    except Exception:
        raise MediaDetailsError(
            "playback_unavailable",
            "Home Assistant could not start this title on the selected Plex player.",
        ) from None
    return {"accepted": True}


@websocket_api.websocket_command({"type": "mediarr/players"})
@websocket_api.async_response
async def websocket_players(hass, connection, msg):
    connection.send_result(msg["id"], {"players": players(hass, connection.user)})


@websocket_api.websocket_command(
    {
        "type": "mediarr/play",
        ws_schema.Required("entity_id"): str,
        ws_schema.Required("library_key"): str,
    }
)
@websocket_api.async_response
async def websocket_play(hass, connection, msg):
    try:
        result = await play(hass, connection.user, msg["entity_id"], msg["library_key"])
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], result)


def async_setup_playback(hass):
    websocket_api.async_register_command(hass, websocket_players)
    websocket_api.async_register_command(hass, websocket_play)
