"""Complete Plex catalog and manager download queues."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections import OrderedDict
from contextvars import ContextVar
from datetime import timedelta
import re
import time
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from aiohttp import web
from homeassistant.components import websocket_api
from homeassistant.components.http import HomeAssistantView, KEY_HASS
from homeassistant.components.http.auth import async_sign_path
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .media_details import DOMAIN, MediaDetailsError, public_details, ws_schema
from .server.plex import _resolve_connection_config
from .snapshot_cache import SnapshotCache, source_scope, MAX_STALE_SECONDS
from .series_progress import section_episode_progress, episode_progress


_FORCE_LIBRARY_HTTP = ContextVar("mediarr_library_force_http", default=False)

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


def manager_artwork(raw, cover_type):
    """Expose public CDN artwork, never authenticated manager URLs or queries."""
    for image in raw.get("images") or []:
        if not isinstance(image, dict) or image.get("coverType") != cover_type:
            continue
        try:
            parts = urlsplit(str(image.get("remoteUrl") or ""))
            port = parts.port
        except ValueError:
            continue
        if parts.scheme == "https" and parts.hostname in {
            "image.tmdb.org", "artworks.thetvdb.com", "www.thetvdb.com", "thetvdb.com", "assets.fanart.tv"
        } and not parts.username and not parts.password and port in (None, 443):
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return ""


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
        "_has_thumb": bool(raw.get("thumb")),
        "_thumb_revision": hashlib.sha256(str(raw.get("thumb") or "").encode()).hexdigest()[:16],
        "_art_revision": hashlib.sha256(str(raw.get("art") or "").encode()).hexdigest()[:16],
        "_episode_count": raw.get("leafCount"),
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
        if not hasattr(self, "_http_cache"):
            self._http_cache = OrderedDict()
            self._queue_versions = {}
        key = (source_scope([source]), path, json.dumps(params, sort_keys=True))
        cached = self._http_cache.get(key)
        ttl = 5 if path.endswith("/queue") else 60 if path.endswith("/all") or path == "/library/sections" or path in {"/api/v3/movie", "/api/v3/series"} else 0
        if not ttl:
            return await self._get_uncached(source, path, **params)
        if cached and not _FORCE_LIBRARY_HTTP.get() and time.monotonic()-cached[0] < ttl:
            self._http_cache.move_to_end(key)
            return cached[1]
        data = await self._get_uncached(source, path, **params)
        if path.endswith("/queue") and isinstance(data, dict):
            version = tuple(sorted((str(row.get("movieId") or row.get("seriesId") or row.get("id")), str(row.get("status", ""))) for row in data.get("records", [])))
            previous = self._queue_versions.get(key)
            self._queue_versions[key] = version
            if previous is not None and previous != version:
                # Import/cancellation changes require authoritative file-presence checks.
                # Percent changes alone do not invalidate the whole catalog.
                self._http_cache.clear()
                self._plex_catalogs = {}
                self._manager_changes = getattr(self, "_manager_changes", set())
                self._manager_changes.add(key[0])
        size = len(json.dumps(data).encode())
        if size <= 4 * 1024 * 1024:
            self._http_cache[key] = (time.monotonic(), data, size)
            while len(self._http_cache) > 128 or sum(row[2] for row in self._http_cache.values()) > 16 * 1024 * 1024:
                self._http_cache.popitem(last=False)
        return data

    async def _get_uncached(self, source, path, **params):
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
                data = await response.json(content_type=None)
                if source["provider"] == "plex" and (not isinstance(data, dict) or not isinstance(data.get("MediaContainer"), dict)):
                    raise MediaDetailsError("library_incomplete", "Plex returned an invalid library response.")
                if path in {"/api/v3/movie", "/api/v3/series"} and not isinstance(data, list):
                    raise MediaDetailsError("library_incomplete", "A media manager returned an invalid library response.")
                if path.endswith("/queue") and (not isinstance(data, dict) or not isinstance(data.get("records"), list)):
                    raise MediaDetailsError("library_incomplete", "A media manager returned an invalid queue response.")
                return data
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise MediaDetailsError(
                "library_unavailable", "A configured media source could not be reached."
            ) from None

    def _identity_rows(self, groups, previous=None):
        metadata = self.hass.data.get(DOMAIN, {}).get("metadata_client")
        old = {}
        if previous:
            for rows in previous["groups"].values():
                for row in rows:
                    old[(row.get("_source_id"), row.get("key"), row.get("media_type"), row.get("title"), row.get("year"))] = row
        result = {}
        for provider, rows in groups.items():
            result[provider] = []
            for row in rows:
                identifier = row.get("tmdb_id")
                if not identifier and metadata:
                    identifier = metadata.identity_for(row.get("media_type"), row.get("title"), row.get("year"), row.get("tvdb_id"), row.get("imdb_id"))
                if not identifier:
                    known = old.get((row.get("_source_id"), row.get("key"), row.get("media_type"), row.get("title"), row.get("year")), {})
                    identifier = known.get("tmdb_id")
                result[provider].append({**row, "tmdb_id": identifier} if identifier else row)
        return result

    def reconcile_identities(self):
        cache = getattr(self, "_snapshot_cache", None)
        if cache is None or cache.data is None:
            return
        groups = self._identity_rows(cache.data["groups"])
        if groups != cache.data["groups"]:
            cache.replace_groups(groups)

    async def snapshot(self, refresh=False, snapshot_id=None):
        if not hasattr(self, "_snapshot_cache"):
            self._snapshot_cache = SnapshotCache(self.hass, self._fetch_snapshot)
        return await self._snapshot_cache.read(configured_sources(self.hass), refresh, snapshot_id)

    async def _fetch_snapshot(self, sources, previous=None, force=False):
        token = _FORCE_LIBRARY_HTTP.set(force)
        try:
            return await self._collect_snapshot(sources, previous, force)
        finally:
            _FORCE_LIBRARY_HTTP.reset(token)

    async def _collect_snapshot(self, sources, previous=None, force=False):
        scope = source_scope(sources)
        if getattr(self, "_catalog_scope", None) != scope:
            self._catalog_scope = scope
            self._plex_catalogs = {}
            self._http_cache = OrderedDict()
            self._queue_versions = {}
            self._manager_changes = set()
        metadata = self.hass.data.get(DOMAIN, {}).get("metadata_client")
        if metadata:
            await metadata.ensure_identities()
        if not any(s["provider"] == "plex" for s in sources):
            raise MediaDetailsError(
                "plex_not_configured", "Configure Plex in the Mediarr integration."
            )
        groups = {"plex": [], "radarr": [], "sonarr": []}
        errors = []
        for index, source in enumerate(sources):
            provider = source["provider"]
            offset = len(groups[provider])
            error_offset = len(errors)
            scope_key = (source_scope(sources), index)
            catalogs = getattr(self, "_plex_catalogs", {})
            if provider == "plex" and not force and scope_key in catalogs and time.monotonic()-catalogs[scope_key][0] < 60:
                groups[provider].extend(catalogs[scope_key][1])
                errors.extend(catalogs[scope_key][2])
                continue
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
                        section_items = []
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
                                section_items.append(item)
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
                        if section.get("type") == "show":
                            try:
                                progress = await section_episode_progress(
                                    self, source, key
                                )
                                for item in section_items:
                                    item["episode_progress"] = progress.get(
                                        item["key"],
                                        episode_progress([])
                                        if item.get("_episode_count") == 0
                                        else {"available": False},
                                    )
                            except MediaDetailsError:
                                for item in section_items:
                                    item["episode_progress"] = {"available": False}
                                errors.append({
                                    "provider": "plex",
                                    "code": "episode_progress_unavailable",
                                })
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
                    changes = getattr(self, "_manager_changes", set())
                    if source_scope([source]) in changes:
                        changes.discard(source_scope([source]))
                        records = await self.get(source, "/api/v3/movie" if provider == "radarr" else "/api/v3/series")
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
                            "poster": manager_artwork(raw, "poster"),
                            "banner": manager_artwork(raw, "fanart"),
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
                rows = groups[provider][offset:]
                for row in rows:
                    row["_source_id"] = index
                    row["_source_checked_at"] = time.time()
                if provider == "plex":
                    self._plex_catalogs = catalogs
                    catalogs[scope_key] = (time.monotonic(), rows, errors[error_offset:])
            except MediaDetailsError as error:
                del groups[provider][offset:]
                if previous:
                    groups[provider].extend({**row, "availability_stale": True} for row in previous["groups"].get(provider, [])
                        if row.get("_source_id") == index and 0 <= time.time()-row.get("_source_checked_at", 0) < MAX_STALE_SECONDS)
                errors.append({"provider": source["provider"], "code": error.code})
        return {"groups": self._identity_rows(groups, previous), "errors": errors, "complete": not errors}

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
        client = hass.data[DOMAIN]["library_client"]
        image_scope = request.query.get("scope")
        if image_scope:
            if not hasattr(client, "_snapshot_cache"):
                await client.snapshot()
            cache = client._snapshot_cache
            if cache.scope != source_scope(sources) or cache.public_scope != image_scope:
                raise web.HTTPNotFound(headers={"Cache-Control": "no-store"})
        if not hasattr(client, "image_cache"):
            client.image_cache = OrderedDict()
        version = request.query.get("v", "")
        version = version if re.fullmatch(r"[0-9a-f]{16}", version) else ""
        key = (source_scope([source]), rating_key, image_type, version)
        cached = client.image_cache.get(key)
        ttl = 24 * 3600 if version else 300
        def image_response(body, content_type, etag):
            headers = {"Cache-Control": f"private, max-age={ttl}", "ETag": etag, "Vary": "Authorization, Cookie"}
            if request.headers.get("If-None-Match") == etag:
                return web.Response(status=304, headers=headers)
            return web.Response(body=body, content_type=content_type, headers=headers)
        if cached and time.monotonic()-cached[0] < ttl:
            client.image_cache.move_to_end(key)
            return image_response(cached[1], cached[2], cached[3])
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
                    raise web.HTTPNotFound(headers={"Cache-Control": "no-store"})
                body = bytearray()
                async for chunk in response.content.iter_chunked(65536):
                    body.extend(chunk)
                    if len(body) > 5 * 1024 * 1024:
                        raise web.HTTPRequestEntityTooLarge(
                            max_size=5 * 1024 * 1024, actual_size=len(body)
                        )
                body = bytes(body)
                etag = '"' + hashlib.sha256(body).hexdigest() + '"'
                client.image_cache[key] = (time.monotonic(), body, response.content_type, etag)
                while len(client.image_cache) > 256 or sum(len(row[1]) for row in client.image_cache.values()) > 32 * 1024 * 1024:
                    client.image_cache.popitem(last=False)
                return image_response(body, response.content_type, etag)
        except (aiohttp.ClientError, TimeoutError):
            raise web.HTTPBadGateway(headers={"Cache-Control": "no-store"}) from None


@websocket_api.websocket_command(
    {
        "type": "mediarr/library",
        ws_schema.Optional("page", default=1): int,
        ws_schema.Optional("refresh", default=False): bool,
        ws_schema.Optional("snapshot_id"): str,
        ws_schema.Optional("since_revision"): str,
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
        snapshot = await client.snapshot(msg.get("refresh", False), msg.get("snapshot_id"))
        if page == 1 and msg.get("since_revision") == snapshot["revision"]:
            connection.send_result(msg["id"], {"unchanged": True, "groups": {}, "page": 1, "total_pages": 1,
                "complete": snapshot["complete"], "errors": snapshot["errors"], "revision": snapshot["revision"], "cache": snapshot["cache"]})
            return
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
                if item.get("_thumb_revision"):
                    path += "?v=" + item["_thumb_revision"] + "&scope=" + snapshot["cache"]["scope_id"]
                cache_key = (connection.user.id, path)
                cached = client.image_urls.get(cache_key)
                if not cached or time.monotonic() - cached[0] > 3600:
                    cached = (
                        time.monotonic(),
                        async_sign_path(hass, path, timedelta(hours=2)),
                    )
                    client.image_urls[cache_key] = cached
                public["poster"] = cached[1] if item.get("_has_thumb", True) else ""
                public["library_key"] = f"{item['_image_source']}:{item['key']}"
                public["library_scope"] = snapshot["cache"]["scope_id"]
                if item.get("_has_art"):
                    art_path = f"/api/mediarr/library_image/{item['_image_source']}/{item['key']}/art"
                    if item.get("_art_revision"):
                        art_path += "?v=" + item["_art_revision"] + "&scope=" + snapshot["cache"]["scope_id"]
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
        while len(client.image_urls) > 4096:
            del client.image_urls[next(iter(client.image_urls))]
        connection.send_result(
            msg["id"],
            {
                "groups": groups,
                "page": page,
                "total_pages": max(1, (len(rows) + 99) // 100),
                "complete": snapshot["complete"],
                "errors": snapshot["errors"],
                "revision": snapshot["revision"],
                "cache": snapshot["cache"],
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
