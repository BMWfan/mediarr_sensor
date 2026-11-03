"""Complete Plex catalog and manager download queues."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import re
import time

import aiohttp
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView, KEY_HASS
from homeassistant.components.http.auth import async_sign_path
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .media_details import DOMAIN, MediaDetailsError, public_details, ws_schema
from .server.plex import _resolve_connection_config


def configured_sources(hass):
    """Only integration configuration supplies destinations and credentials."""
    data = hass.data.get(DOMAIN, {})
    configs = [data.get("yaml_config", {}), data.get("metadata_yaml_config", {})]
    configs.extend(data.get("entries", {}).values())
    sources = []
    seen = set()
    for config in configs:
        if not isinstance(config, dict):
            continue
        for name in ["plex", "radarr", "radarr2", "sonarr", "sonarr2"]:
            section = config.get(name)
            if not isinstance(section, dict):
                continue
            if name == "plex":
                section = _resolve_connection_config(hass, section)
                if not section:
                    continue
            url = str(section.get("url") or "").rstrip("/")
            token = section.get("token") if name == "plex" else section.get("api_key")
            if not url.startswith(("http://", "https://")) or not token:
                continue
            identity = (name, url)
            if identity in seen:
                continue
            seen.add(identity)
            sources.append(
                {
                    "provider": name.rstrip("2"),
                    "url": url,
                    "token": token,
                    "verify_ssl": section.get("verify_ssl", True),
                }
            )
    return sources


def plex_item(raw):
    kind = "tv" if raw.get("type") == "show" else "movie"
    guids = [x.get("id", "") for x in raw.get("Guid", []) if isinstance(x, dict)] + [
        raw.get("guid", "")
    ]
    ids = {}
    for guid in guids:
        match = re.match(r"(tmdb|tvdb|imdb)://([A-Za-z0-9]+)(?:\?|$)", guid or "")
        if match:
            ids[match[1] + "_id"] = match[2]
        legacy = re.match(
            r"com\.plexapp\.agents\.(themoviedb|thetvdb|imdb)://([A-Za-z0-9]+)",
            guid or "",
        )
        if legacy:
            ids[
                {"themoviedb": "tmdb", "thetvdb": "tvdb", "imdb": "imdb"}[legacy[1]]
                + "_id"
            ] = legacy[2]
    watched = (
        raw.get("viewCount", 0) > 0
        if kind == "movie"
        else bool(
            raw.get("leafCount") and raw.get("viewedLeafCount", 0) >= raw["leafCount"]
        )
    )
    return {
        "title": raw.get("title", ""),
        "year": raw.get("year"),
        "media_type": kind,
        **ids,
        "overview": raw.get("summary", ""),
        "rating": raw.get("rating"),
        "runtime": round(raw.get("duration", 0) / 60000) or None,
        "watched": watched,
        "has_watched": bool(raw.get("viewCount") or raw.get("viewedLeafCount")),
        "last_watched": raw.get("lastViewedAt", 0),
        "added": raw.get("addedAt", 0),
        "in_progress": bool(raw.get("viewOffset", 0))
        or (
            kind == "tv" and 0 < raw.get("viewedLeafCount", 0) < raw.get("leafCount", 0)
        ),
        "_has_art": bool(raw.get("art")),
        "key": str(raw.get("ratingKey", "")),
        "cast": [
            {"name": x.get("tag", ""), "character": x.get("role", "")}
            for x in raw.get("Role", [])[:30]
        ],
        "genres": [x.get("tag", "") for x in raw.get("Genre", [])],
    }


def queue_state(records):
    result = {}
    for item in records:
        identity = item.get("movieId") or item.get("seriesId")
        if not identity:
            continue
        size = item.get("size") or 0
        remaining = item.get("sizeleft")
        progress = (
            round(max(0, min(100, (1 - remaining / size) * 100)))
            if size > 0 and isinstance(remaining, (int, float))
            else None
        )
        status = str(item.get("status") or "").lower()
        tracked = str(item.get("trackedDownloadState") or "").lower()
        if "import" in tracked:
            status = "importing"
        elif (
            item.get("errorMessage")
            or "warning" in str(item.get("trackedDownloadStatus", "")).lower()
        ):
            status = "warning"
        elif status not in {"paused", "queued", "downloading", "completed"}:
            status = "downloading"
        old = result.get(identity)
        if old is None or (progress or 0) > (old.get("download_progress") or 0):
            result[identity] = {
                "download_status": status,
                "download_progress": progress,
            }
    return result


class LibraryClient:
    def __init__(self, hass):
        self.hass = hass
        self.session = async_get_clientsession(hass)
        self.lock = asyncio.Lock()
        self.cached = None
        self.cached_at = 0
        self.image_urls = {}

    async def get(self, source, path, **params):
        headers = {
            "Accept": "application/json",
            ("X-Plex-Token" if source["provider"] == "plex" else "X-Api-Key"): source[
                "token"
            ],
        }
        try:
            async with self.session.get(
                source["url"] + path,
                params=params,
                headers=headers,
                ssl=None if source.get("verify_ssl", True) else False,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as response:
                if response.status != 200:
                    raise MediaDetailsError(
                        "library_unavailable",
                        "A configured media source could not be read.",
                    )
                return await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise MediaDetailsError(
                "library_unavailable", "A configured media source could not be reached."
            ) from None

    async def snapshot(self, refresh=False):
        async with self.lock:
            if (
                self.cached is not None
                and time.monotonic() - self.cached_at < 30
                and not refresh
            ):
                return self.cached
            sources = configured_sources(self.hass)
            if not any(s["provider"] == "plex" for s in sources):
                raise MediaDetailsError(
                    "plex_not_configured", "Configure Plex in the Mediarr integration."
                )
            groups = {"plex": [], "radarr": [], "sonarr": []}
            errors = []
            for index, source in enumerate(sources):
                try:
                    if source["provider"] == "plex":
                        sections = (
                            (await self.get(source, "/library/sections"))
                            .get("MediaContainer", {})
                            .get("Directory", [])
                        )
                        for section in sections:
                            if section.get("type") not in {"movie", "show"}:
                                continue
                            key = str(section.get("key", ""))
                            if not key.isdigit():
                                continue
                            start = 0
                            while True:
                                container = (
                                    await self.get(
                                        source,
                                        f"/library/sections/{key}/all",
                                        includeGuids=1,
                                        **{
                                            "X-Plex-Container-Start": start,
                                            "X-Plex-Container-Size": 100,
                                        },
                                    )
                                ).get("MediaContainer", {})
                                records = container.get("Metadata", [])
                                for raw in records:
                                    item = plex_item(raw)
                                    if item["key"].isdigit():
                                        item["_image_source"] = index
                                    groups["plex"].append(item)
                                start += len(records)
                                total = int(
                                    container.get(
                                        "totalSize", container.get("size", start)
                                    )
                                )
                                if start >= total:
                                    break
                                if not records:
                                    raise MediaDetailsError(
                                        "library_incomplete",
                                        "Plex returned an incomplete library page.",
                                    )
                    else:
                        provider = source["provider"]
                        kind = "movie" if provider == "radarr" else "tv"
                        records = await self.get(
                            source,
                            (
                                "/api/v3/movie"
                                if provider == "radarr"
                                else "/api/v3/series"
                            ),
                        )
                        queues = []
                        page = 1
                        while True:
                            q = await self.get(
                                source,
                                "/api/v3/queue",
                                page=page,
                                pageSize=100,
                                includeUnknownMovieItems="false",
                                includeUnknownSeriesItems="false",
                            )
                            batch = q.get("records", [])
                            queues.extend(batch)
                            if len(queues) >= q.get("totalRecords", len(queues)):
                                break
                            if not batch:
                                raise MediaDetailsError(
                                    "library_incomplete",
                                    "A download queue returned an incomplete page.",
                                )
                            page += 1
                        downloads = queue_state(queues)
                        for raw in records:
                            stats = raw.get("statistics") or {}
                            has_file = (
                                bool(raw.get("hasFile"))
                                if kind == "movie"
                                else bool(stats.get("episodeFileCount"))
                            )
                            item = {
                                "title": raw.get("title", ""),
                                "year": raw.get("year"),
                                "media_type": kind,
                                "tmdb_id": raw.get("tmdbId"),
                                "tvdb_id": raw.get("tvdbId"),
                                "imdb_id": raw.get("imdbId"),
                                "overview": raw.get("overview", ""),
                                "has_file": has_file,
                                "monitored": raw.get("monitored", True),
                                "release_date": (
                                    (
                                        raw.get("digitalRelease")
                                        or raw.get("physicalRelease")
                                        or raw.get("inCinemas")
                                    )
                                    if kind == "movie"
                                    else raw.get("nextAiring")
                                ),
                                "release_kind": (
                                    (
                                        "digital"
                                        if raw.get("digitalRelease")
                                        else (
                                            "physical"
                                            if raw.get("physicalRelease")
                                            else "cinema"
                                        )
                                    )
                                    if kind == "movie"
                                    else "episode"
                                ),
                                **downloads.get(raw.get("id"), {}),
                            }
                            # Unmonitored existing titles still belong to the managed catalog.
                            groups[provider].append(item)
                except MediaDetailsError as error:
                    errors.append({"provider": source["provider"], "code": error.code})
            self.cached = {"groups": groups, "errors": errors, "complete": not errors}
            self.cached_at = time.monotonic()
            return self.cached


class LibraryImageView(HomeAssistantView):
    url = "/api/mediarr/library_image/{source_id}/{rating_key}"
    name = "api:mediarr:library_image"
    requires_auth = True
    extra_urls = ["/api/mediarr/library_image/{source_id}/{rating_key}/{image_type}"]

    async def get(self, request, source_id, rating_key, image_type="thumb"):
        if image_type not in {"thumb", "art"}:
            raise web.HTTPNotFound()
        if not source_id.isdigit() or not rating_key.isdigit():
            raise web.HTTPNotFound()
        hass = request.app[KEY_HASS]
        sources = configured_sources(hass)
        if int(source_id) >= len(sources):
            raise web.HTTPNotFound()
        source = sources[int(source_id)]
        if source["provider"] != "plex":
            raise web.HTTPNotFound()
        try:
            async with async_get_clientsession(hass).get(
                source["url"] + f"/library/metadata/{rating_key}/{image_type}",
                headers={"X-Plex-Token": source["token"]},
                allow_redirects=False,
                ssl=None if source.get("verify_ssl", True) else False,
                timeout=aiohttp.ClientTimeout(total=12),
            ) as response:
                if response.status != 200 or not response.content_type.startswith(
                    "image/"
                ):
                    raise web.HTTPNotFound()
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 5 * 1024 * 1024:
                        raise web.HTTPRequestEntityTooLarge(
                            max_size=5 * 1024 * 1024, actual_size=len(body)
                        )
                return web.Response(
                    body=bytes(body),
                    content_type=response.content_type,
                    headers={"Cache-Control": "private, max-age=300"},
                )
        except (aiohttp.ClientError, TimeoutError):
            raise web.HTTPBadGateway() from None


@websocket_api.websocket_command(
    {
        "type": "mediarr/library",
        ws_schema.Optional("page", default=1): int,
        ws_schema.Optional("refresh", default=False): bool,
        ws_schema.Optional("language", default="en"): str,
    }
)
@websocket_api.async_response
async def websocket_library(hass, connection, msg):
    page = msg.get("page", 1)
    language = msg.get("language", "en")
    if (
        type(page) is not int
        or not 1 <= page <= 10000
        or not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?", language)
    ):
        connection.send_error(msg["id"], "invalid_format", "Invalid library request.")
        return
    client = hass.data[DOMAIN]["library_client"]
    try:
        snapshot = await client.snapshot(msg.get("refresh", False))
        rows = [
            (provider, item)
            for provider, items in snapshot["groups"].items()
            for item in items
        ]
        groups = {"plex": [], "radarr": [], "sonarr": []}
        for provider, item in rows[(page - 1) * 100 : page * 100]:
            public = {k: v for k, v in item.items() if not k.startswith("_")}
            if "_image_source" in item:
                path = (
                    f"/api/mediarr/library_image/{item['_image_source']}/{item['key']}"
                )
                cache_key = (connection.user.id, path)
                cached = client.image_urls.get(cache_key)
                if not cached or time.monotonic() - cached[0] > 3600:
                    cached = (
                        time.monotonic(),
                        async_sign_path(hass, path, timedelta(hours=2)),
                    )
                    client.image_urls[cache_key] = cached
                public["poster"] = cached[1]
                public["library_key"] = f"{item['_image_source']}:{item['key']}"
                if item.get("_has_art"):
                    art_path = path + "/art"
                    art_key = (connection.user.id, art_path)
                    art = client.image_urls.get(art_key)
                    if not art or time.monotonic() - art[0] > 3600:
                        art = (
                            time.monotonic(),
                            async_sign_path(hass, art_path, timedelta(hours=2)),
                        )
                        client.image_urls[art_key] = art
                    public["banner"] = art[1]
                public["key"] = f"/library/metadata/{item['key']}"
            groups[provider].append(public)
        connection.send_result(
            msg["id"],
            {
                "groups": groups,
                "page": page,
                "total_pages": max(1, (len(rows) + 99) // 100),
                "complete": snapshot["complete"],
                "errors": snapshot["errors"],
            },
        )
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))


def async_setup_library(hass):
    if hass.data[DOMAIN].get("library_client"):
        return
    hass.data[DOMAIN]["library_client"] = LibraryClient(hass)
    websocket_api.async_register_command(hass, websocket_library)
    hass.http.register_view(LibraryImageView)
    from .collections import websocket_collections

    websocket_api.async_register_command(hass, websocket_collections)
