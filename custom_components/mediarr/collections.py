"""Read existing Plex collections and smart-collection membership on demand."""

import re
import time
from homeassistant.components import websocket_api
from .library import configured_sources
from .media_details import DOMAIN, MediaDetailsError, ws_schema


async def plex_collections(client, collection_id=None):
    cache = getattr(client, "collection_cache", None)
    if cache is None:
        cache = client.collection_cache = {}
    cached = cache.get(collection_id)
    if cached and time.monotonic() - cached[0] < 300:
        return cached[1]
    sources = configured_sources(client.hass)
    if collection_id is not None:
        match = re.fullmatch(r"(\d+):(\d+)", collection_id)
        if (
            not match
            or int(match[1]) >= len(sources)
            or sources[int(match[1])]["provider"] != "plex"
        ):
            raise MediaDetailsError("invalid_format", "Invalid Plex collection.")
        index, key = match.groups()
        records = await paged(
            client, sources[int(index)], f"/library/collections/{key}/children"
        )
        result = {
            "keys": [
                f"{index}:{item['ratingKey']}"
                for item in records
                if str(item.get("ratingKey", "")).isdigit()
            ]
        }
    else:
        result = {"collections": []}
        for index, source in enumerate(sources):
            if source["provider"] != "plex":
                continue
            sections = (
                (await client.get(source, "/library/sections"))
                .get("MediaContainer", {})
                .get("Directory", [])
            )
            for section in sections:
                if (
                    section.get("type") not in {"movie", "show"}
                    or not str(section.get("key", "")).isdigit()
                ):
                    continue
                records = await paged(
                    client, source, f"/library/sections/{section['key']}/collections"
                )
                result["collections"].extend(
                    {
                        "id": f"{index}:{item['ratingKey']}",
                        "title": str(item.get("title", "")),
                        "smart": bool(item.get("smart")),
                    }
                    for item in records
                    if str(item.get("ratingKey", "")).isdigit() and item.get("title")
                )
    cache[collection_id] = (time.monotonic(), result)
    if len(cache) > 128:
        cache.pop(next(iter(cache)))
    return result


async def paged(client, source, path):
    records = []
    while True:
        data = (
            await client.get(
                source,
                path,
                **{
                    "X-Plex-Container-Start": len(records),
                    "X-Plex-Container-Size": 100,
                },
            )
        ).get("MediaContainer", {})
        batch = data.get("Metadata", [])
        records.extend(batch)
        if len(records) >= int(data.get("totalSize", data.get("size", len(records)))):
            return records
        if not batch:
            raise MediaDetailsError(
                "library_incomplete", "A Plex collection returned an incomplete page."
            )


@websocket_api.websocket_command(
    {"type": "mediarr/collections", ws_schema.Optional("collection_id"): str}
)
@websocket_api.async_response
async def websocket_collections(hass, connection, msg):
    try:
        result = await plex_collections(
            hass.data[DOMAIN]["library_client"], msg.get("collection_id")
        )
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], result)
