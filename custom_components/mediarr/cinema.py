"""Cinema discovery and per-HA-user TMDB accounts; no local recommendation model."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import re
import time
from urllib.parse import quote

import aiohttp
from homeassistant.components import websocket_api
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .media_details import (
    DOMAIN,
    MediaDetailsError,
    public_details,
    resolve_tmdb_key,
    ws_schema,
)


def tmdb_application_token(data):
    configs = [
        *data.get("entries", {}).values(),
        data.get("yaml_config", {}),
        data.get("metadata_yaml_config", {}),
    ]
    for config in configs:
        if not isinstance(config, dict):
            continue
        sections = [config, *[v for v in config.values() if isinstance(v, dict)]]
        for section in sections:
            token = section.get("tmdb_read_access_token")
            if isinstance(token, str) and token.strip():
                return token.strip()
    key = resolve_tmdb_key(data)
    return key if key and not re.fullmatch(r"[0-9a-fA-F]{32}", key) else None


def catalog_items(data, kind=None):
    items = []
    for raw in data.get("results", [])[:40]:
        if not isinstance(raw, dict):
            continue
        media_type = raw.get("media_type", kind)
        if (
            media_type not in {"movie", "tv"}
            or raw.get("adult")
            or type(raw.get("id")) is not int
            or raw["id"] <= 0
        ):
            continue
        item = public_details(raw, media_type)
        item["release_date"] = (
            raw.get("release_date") or raw.get("first_air_date") or ""
        )
        items.append(item)
    return items


class CinemaClient:
    def __init__(self, hass):
        self.hass = hass
        self.metadata = hass.data[DOMAIN]["metadata_client"]
        self.store = Store(hass, 1, "mediarr.tmdb_accounts", private=True)
        self.accounts = None
        self.pending = {}
        self.lock = asyncio.Lock()
        self.cache = {}

    async def load_accounts(self):
        if self.accounts is None:
            self.accounts = (await self.store.async_load()) or {}
            if not isinstance(self.accounts, dict):
                self.accounts = {}

    async def api4(self, method, endpoint, token, payload=None, **params):
        try:
            async with self.metadata.session.request(
                method,
                f"https://api.themoviedb.org/4/{endpoint}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                },
                json=payload,
                params=params,
                allow_redirects=False,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as response:
                if response.status in (401, 403):
                    raise MediaDetailsError(
                        "tmdb_account_auth",
                        "TMDB authorization was rejected. Reconnect your account.",
                    )
                if response.status not in (200, 201):
                    raise MediaDetailsError(
                        "tmdb_account_unavailable", "TMDB account could not be reached."
                    )
                result = await response.json()
                if result.get("success") is False:
                    raise MediaDetailsError(
                        "tmdb_account_pending",
                        "Approve the request on TMDB before confirming.",
                    )
                return result
        except (aiohttp.ClientError, TimeoutError, ValueError):
            raise MediaDetailsError(
                "tmdb_account_unavailable", "TMDB account could not be reached."
            ) from None

    async def account(self, user_id, action):
        async with self.lock:
            await self.load_accounts()
            token = tmdb_application_token(self.hass.data[DOMAIN])
            if action == "disconnect":
                self.accounts.pop(user_id, None)
                self.pending.pop(user_id, None)
                self.cache = {k: v for k, v in self.cache.items() if k[0] != user_id}
                await self.store.async_save(self.accounts)
            elif action == "start":
                if not token:
                    raise MediaDetailsError(
                        "tmdb_read_token_required",
                        "Configure the TMDB API Read Access Token in the integration's TMDB options.",
                    )
                pending = self.pending.get(user_id)
                if not pending or time.monotonic() - pending[1] > 600:
                    result = await self.api4("POST", "auth/request_token", token, {})
                    request_token = result.get("request_token")
                    if (
                        not isinstance(request_token, str)
                        or not 1 <= len(request_token) <= 4096
                    ):
                        raise MediaDetailsError(
                            "tmdb_account_unavailable",
                            "TMDB did not issue an authorization request.",
                        )
                    pending = self.pending[user_id] = (request_token, time.monotonic())
                return {
                    "connected": bool(self.accounts.get(user_id)),
                    "can_connect": True,
                    "authorization_url": "https://www.themoviedb.org/auth/access?request_token="
                    + quote(pending[0], safe=""),
                }
            elif action == "finish":
                pending = self.pending.get(user_id)
                if not token or not pending or time.monotonic() - pending[1] > 600:
                    raise MediaDetailsError(
                        "tmdb_account_expired", "Start a new TMDB account connection."
                    )
                try:
                    result = await self.api4(
                        "POST",
                        "auth/access_token",
                        token,
                        {"request_token": pending[0]},
                    )
                except MediaDetailsError as error:
                    if error.code == "tmdb_account_auth":
                        self.pending.pop(user_id, None)
                    raise
                access = result.get("access_token")
                account_id = result.get("account_id")
                if (
                    not isinstance(access, str)
                    or not access
                    or not isinstance(account_id, str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", account_id)
                ):
                    raise MediaDetailsError(
                        "tmdb_account_pending",
                        "Approve the request on TMDB before confirming.",
                    )
                self.accounts[user_id] = {
                    "access_token": access,
                    "account_id": account_id,
                }
                await self.store.async_save(self.accounts)
                self.pending.pop(user_id, None)
                self.cache = {k: v for k, v in self.cache.items() if k[0] != user_id}
            return {
                "connected": bool(self.accounts.get(user_id)),
                "can_connect": bool(token),
            }

    async def discover(self, user_id, language, period, region):
        status = await self.account(user_id, "status")
        cache_key = (user_id, language, period, region)
        cached = self.cache.get(cache_key)
        if cached and time.monotonic() - cached[0] < 300:
            return cached[1]
        errors = {}
        key = self.metadata.key_resolver()

        async def public(endpoint, kind=None, **params):
            if not key:
                raise MediaDetailsError(
                    "tmdb_not_configured", "Configure TMDB in the Mediarr integration."
                )
            async with self.metadata.slots:
                return catalog_items(
                    await self.metadata._get(endpoint, key, language, **params), kind
                )

        async def personal():
            account = (self.accounts or {}).get(user_id)
            if not account:
                raise MediaDetailsError(
                    "tmdb_account_not_connected",
                    "Connect your TMDB account for personal recommendations.",
                )

            async def fetch(kind):
                async with self.metadata.slots:
                    data = await self.api4(
                        "GET",
                        f"account/{account['account_id']}/{kind}/recommendations",
                        account["access_token"],
                        language=language,
                        page=1,
                    )
                    return catalog_items(data, kind)

            movies, shows = await asyncio.gather(fetch("movie"), fetch("tv"))
            # Preserve the upstream ranking within each media type, no local scoring.
            return (
                [item for pair in zip(movies, shows) for item in pair]
                + movies[len(shows) :]
                + shows[len(movies) :]
            )

        async def upcoming():
            today_date = dt_util.now().date()
            today = today_date.isoformat()
            movies, shows = await asyncio.gather(
                public(
                    "discover/movie",
                    "movie",
                    **{
                        "primary_release_date.gte": today,
                        "primary_release_date.lte": (
                            today_date + timedelta(days=180)
                        ).isoformat(),
                        "sort_by": "popularity.desc",
                        "region": region,
                        "include_adult": "false",
                    },
                ),
                public(
                    "discover/tv",
                    "tv",
                    **{
                        "first_air_date.gte": today,
                        "first_air_date.lte": (
                            today_date + timedelta(days=180)
                        ).isoformat(),
                        "sort_by": "popularity.desc",
                        "include_adult": "false",
                    },
                ),
            )
            return movies + shows

        names = ["trending", "personal", "upcoming"]
        values = await asyncio.gather(
            public(f"trending/all/{period}"),
            personal(),
            upcoming(),
            return_exceptions=True,
        )
        result = {"account": status, "errors": errors}
        for name, value in zip(names, values):
            if isinstance(value, Exception):
                result[name] = []
                errors[name] = (
                    value.code
                    if isinstance(value, MediaDetailsError)
                    else "metadata_unavailable"
                )
            else:
                result[name] = value
        if not any(code != "tmdb_account_not_connected" for code in errors.values()):
            self.cache[cache_key] = (time.monotonic(), result)
        if len(self.cache) > 64:
            self.cache.pop(next(iter(self.cache)))
        return result


@websocket_api.websocket_command(
    {
        "type": "mediarr/cinema",
        ws_schema.Optional("language", default="en"): str,
        ws_schema.Optional("region", default="DE"): str,
        ws_schema.Optional("period", default="week"): ws_schema.In(["day", "week"]),
    }
)
@websocket_api.async_response
async def websocket_cinema(hass, connection, msg):
    language, region = msg.get("language", "en"), msg.get("region", "DE")
    if not re.fullmatch(
        r"[a-zA-Z]{2,3}(?:-[a-zA-Z]{2})?", language
    ) or not re.fullmatch(r"[A-Z]{2}", region):
        connection.send_error(
            msg["id"], "invalid_format", "Invalid language or region."
        )
        return
    try:
        result = await hass.data[DOMAIN]["cinema_client"].discover(
            connection.user.id, language, msg.get("period", "week"), region
        )
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], result)


@websocket_api.websocket_command(
    {
        "type": "mediarr/tmdb_account",
        ws_schema.Optional("action", default="status"): ws_schema.In(
            ["status", "start", "finish", "disconnect"]
        ),
    }
)
@websocket_api.async_response
async def websocket_tmdb_account(hass, connection, msg):
    try:
        result = await hass.data[DOMAIN]["cinema_client"].account(
            connection.user.id, msg.get("action", "status")
        )
    except MediaDetailsError as error:
        connection.send_error(msg["id"], error.code, str(error))
    else:
        connection.send_result(msg["id"], result)


def async_setup_cinema(hass):
    if hass.data[DOMAIN].get("cinema_client"):
        return
    hass.data[DOMAIN]["cinema_client"] = CinemaClient(hass)
    websocket_api.async_register_command(hass, websocket_cinema)
    websocket_api.async_register_command(hass, websocket_tmdb_account)
