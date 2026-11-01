"""Authenticated, cached title metadata for the Mediarr frontend."""
from __future__ import annotations

import asyncio
from collections import OrderedDict
from datetime import timedelta
import re
import time
import unicodedata

import aiohttp
from homeassistant.components import websocket_api
from homeassistant.components.websocket_api.messages import BASE_COMMAND_MESSAGE_SCHEMA

# Home Assistant moved its WebSocket validation from voluptuous to probatio.
if type(BASE_COMMAND_MESSAGE_SCHEMA).__module__.startswith("voluptuous"):
    import voluptuous as ws_schema
else:
    import probatio as ws_schema
from homeassistant.helpers.aiohttp_client import async_get_clientsession

DOMAIN = "mediarr"
COMMAND = "mediarr/media_details"
TMDB_BASE = "https://api.themoviedb.org/3"
CACHE_TTL = timedelta(hours=6).total_seconds()
CACHE_LIMIT = 256


class MediaDetailsError(Exception):
    """An intentionally credential-free error returned to the frontend."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def resolve_tmdb_key(domain_data: dict) -> str | None:
    """Use explicit TMDB keys, never a Plex/Seerr/Sonarr API credential."""
    configs = [domain_data.get("metadata_yaml_config", {}), domain_data.get("yaml_config", {})]
    configs.extend(domain_data.get("entries", {}).values())
    for config in configs:
        if not isinstance(config, dict):
            continue
        candidates = [config.get("tmdb_api_key")]
        candidates.extend(section.get("tmdb_api_key") for section in config.values() if isinstance(section, dict))
        for key in candidates:
            if isinstance(key, str) and key.strip():
                return key.strip()
    return None


def normalize_title(value: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", value).casefold())


def public_details(data: dict, kind: str) -> dict:
    """Return only title metadata, excluding transport/configuration data."""
    if not isinstance(data, dict) or type(data.get("id")) is not int or data["id"] <= 0:
        raise MediaDetailsError("metadata_unavailable", "TMDB returned invalid metadata.")
    credits = data.get("credits") or {}
    return {
        "media_type": kind,
        "tmdb_id": data["id"],
        "title": data.get("title") or data.get("name") or "",
        "original_title": data.get("original_title") or data.get("original_name") or "",
        "year": (data.get("release_date") or data.get("first_air_date") or "")[:4],
        "overview": data.get("overview") or "",
        "genres": [genre["name"] for genre in data.get("genres", []) if genre.get("name")],
        "runtime": data.get("runtime") or next(iter(data.get("episode_run_time") or []), None),
        "vote_average": data.get("vote_average"),
        "poster": f"https://image.tmdb.org/t/p/w500{data['poster_path']}" if data.get("poster_path") else "",
        "backdrop": f"https://image.tmdb.org/t/p/w1280{data['backdrop_path']}" if data.get("backdrop_path") else "",
        "cast": [{key: actor.get(key) for key in ("name", "character", "profile_path")}
                 for actor in credits.get("cast", [])[:30] if actor.get("name")],
        "directors": [person["name"] for person in credits.get("crew", [])
                      if person.get("job") == "Director" and person.get("name")],
        "imdb_id": (data.get("external_ids") or {}).get("imdb_id"),
        "tvdb_id": (data.get("external_ids") or {}).get("tvdb_id"),
    }


def public_streaming(data, region):
    """Keep subscription offers separate from rentals and purchases."""
    offers=(data.get("watch/providers") or {}).get("results",{}).get(region,{})
    def providers(kind):
        return [{"name":item["provider_name"],"id":item.get("provider_id")}
                for item in offers.get(kind,[]) if item.get("provider_name")]
    link=offers.get("link","")
    if not link.startswith("https://www.themoviedb.org/"):link=""
    return {"region":region,"subscription":providers("flatrate"),"rent":providers("rent"),
            "buy":providers("buy"),"link":link}


class MediaDetailsClient:
    """Fetch selected-title details with bounded caching and safe errors."""

    def __init__(self, session, key_resolver) -> None:
        self.session = session
        self.key_resolver = key_resolver
        self.cache: OrderedDict = OrderedDict()
        self.slots = asyncio.Semaphore(4)

    async def _get(self, endpoint: str, key: str, language: str, **params) -> dict:
        params["language"] = language
        headers = {"Accept": "application/json"}
        if re.fullmatch(r"[0-9a-fA-F]{32}", key):
            params["api_key"] = key
        else:
            headers["Authorization"] = f"Bearer {key}"
        try:
            async with self.session.get(f"{TMDB_BASE}/{endpoint}", params=params,
                                        headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as response:
                if response.status in (401, 403):
                    raise MediaDetailsError("metadata_auth", "The configured TMDB credential was rejected.")
                if response.status == 404:
                    raise MediaDetailsError("metadata_not_found", "No metadata found for this title.")
                if response.status != 200:
                    raise MediaDetailsError("metadata_unavailable", "TMDB metadata is temporarily unavailable.")
                return await response.json()
        except (aiohttp.ClientError, TimeoutError):
            raise MediaDetailsError("metadata_unavailable", "TMDB metadata could not be reached.") from None

    async def search(self, *, query, language="en", page=1) -> dict:
        """Search the catalog, never treating a result as library availability."""
        if not isinstance(query, str) or not 2 <= len(query.strip()) <= 128:
            raise MediaDetailsError("invalid_format", "Search requires 2 to 128 characters.")
        if type(page) is not int or not 1 <= page <= 5:
            raise MediaDetailsError("invalid_format", "Invalid search page.")
        if not isinstance(language, str) or not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?", language):
            raise MediaDetailsError("invalid_format", "Invalid language.")
        key = self.key_resolver()
        if not key:
            raise MediaDetailsError("tmdb_not_configured", "Configure a TMDB credential in the Mediarr integration.")
        cache_key = ("catalog", query.strip().casefold(), language, page)
        cached = self.cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1]
        data = await self._get("search/multi", key, language, query=query.strip(), page=page, include_adult="false")
        results = []
        for item in data.get("results", [])[:20]:
            if not isinstance(item, dict) or item.get("media_type") not in {"movie", "tv"} or item.get("adult"):
                continue
            if type(item.get("id")) is not int or item["id"] <= 0:
                continue
            results.append(public_details(item, item["media_type"]))
        result = {"results": results, "page": page,
                  "total_pages": min(max(int(data.get("total_pages") or 0), 0), 5)}
        self.cache[cache_key] = (time.monotonic(), result)
        self.cache.move_to_end(cache_key)
        while len(self.cache) > CACHE_LIMIT:
            self.cache.popitem(last=False)
        return result

    async def details(self, *, media_type="unknown", tmdb_id=None, title="", year=None, language="en", region="DE") -> dict:
        if not isinstance(region,str) or not re.fullmatch(r"[A-Z]{2}",region):
            raise MediaDetailsError("invalid_format", "Invalid region.")
        if media_type not in {"movie", "tv", "unknown"}:
            raise MediaDetailsError("invalid_format", "Invalid media type.")
        if tmdb_id is not None and (type(tmdb_id) is not int or not 0 < tmdb_id < 10**10):
            raise MediaDetailsError("invalid_format", "Invalid TMDB identifier.")
        if not isinstance(title, str) or len(title) > 256:
            raise MediaDetailsError("invalid_format", "Invalid title.")
        if year is not None and (type(year) is not int or not 1800 <= year <= 2200):
            raise MediaDetailsError("invalid_format", "Invalid year.")
        if not isinstance(language, str) or not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?", language):
            raise MediaDetailsError("invalid_format", "Invalid language.")
        if not tmdb_id and not title.strip():
            raise MediaDetailsError("invalid_format", "A title or TMDB ID is required.")
        key = self.key_resolver()
        if not key:
            raise MediaDetailsError("tmdb_not_configured", "Configure a TMDB credential in the Mediarr integration.")
        cache_key = (media_type, tmdb_id, title.strip(), year, language, region)
        cached = self.cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < CACHE_TTL:
            self.cache.move_to_end(cache_key)
            return cached[1]
        if media_type == "unknown" or not tmdb_id:
            endpoint = "search/multi" if media_type == "unknown" else f"search/{media_type}"
            data = await self._get(endpoint, key, language, query=title.strip())
            matches = {}
            for item in data.get("results", []):
                kind = item.get("media_type", media_type)
                if kind not in {"movie", "tv"}:
                    continue
                if tmdb_id and item.get("id") != tmdb_id:
                    continue
                titles = (item.get("title"), item.get("name"), item.get("original_title"), item.get("original_name"))
                if title.strip() and not any(normalize_title(value or "") == normalize_title(title) for value in titles):
                    continue
                item_year = (item.get("release_date") or item.get("first_air_date") or "")[:4]
                if year and item_year != str(year):
                    continue
                matches[(kind, item["id"])] = item
            if len(matches) != 1:
                code = "metadata_ambiguous" if matches else "metadata_not_found"
                raise MediaDetailsError(code, "This title could not be identified unambiguously.")
            media_type, tmdb_id = next(iter(matches))
        data = await self._get(f"{media_type}/{tmdb_id}", key, language, append_to_response="credits,external_ids,watch/providers")
        result = public_details(data, media_type)
        result["streaming"]=public_streaming(data,region)
        self.cache[cache_key] = (time.monotonic(), result)
        self.cache.move_to_end(cache_key)
        while len(self.cache) > CACHE_LIMIT:
            self.cache.popitem(last=False)
        return result


@websocket_api.websocket_command({
    "type": COMMAND,
    ws_schema.Optional("media_type", default="unknown"): ws_schema.In(["movie", "tv", "unknown"]),
    ws_schema.Optional("tmdb_id"): int,
    ws_schema.Optional("title", default=""): ws_schema.All(str, ws_schema.Length(max=256)),
    ws_schema.Optional("year"): int,
    ws_schema.Optional("language", default="en"): str,
    ws_schema.Optional("region", default="DE"): str,
})
@websocket_api.async_response
async def websocket_media_details(hass, connection, msg):
    """Use the authenticated HA WebSocket; credentials stay server-side."""
    client = hass.data[DOMAIN]["metadata_client"]
    try:
        async with client.slots:
            result = await client.details(**{key: msg[key] for key in
                ("media_type", "tmdb_id", "title", "year", "language", "region") if key in msg})
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command({
    "type": "mediarr/search",
    ws_schema.Required("query"): ws_schema.All(str, ws_schema.Length(min=2, max=128)),
    ws_schema.Optional("language", default="en"): str,
    ws_schema.Optional("page", default=1): int,
})
@websocket_api.async_response
async def websocket_media_search(hass, connection, msg):
    """Authenticated catalog search with the server's existing TMDB key."""
    client = hass.data[DOMAIN]["metadata_client"]
    try:
        async with client.slots:
            result = await client.search(query=msg["query"], language=msg.get("language", "en"), page=msg.get("page", 1))
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], result)


def async_setup_metadata(hass) -> None:
    """Register once; read current configuration for each request."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get("metadata_client"):
        return
    domain_data["metadata_client"] = MediaDetailsClient(
        async_get_clientsession(hass), lambda: resolve_tmdb_key(hass.data.get(DOMAIN, {})))
    websocket_api.async_register_command(hass, websocket_media_details)
    websocket_api.async_register_command(hass, websocket_media_search)
    from .library import async_setup_library
    async_setup_library(hass)
