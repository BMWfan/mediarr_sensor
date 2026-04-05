"""Shared Immaculaterr API client for sensors and services."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp
import async_timeout

_LOGGER = logging.getLogger(__name__)


class ImmaculaterrClient:
    """Small session-aware API client for Immaculaterr."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self._url = url.rstrip("/")
        self._username = username
        self._password = password
        self._owns_session = session is None
        self._session = session or aiohttp.ClientSession(
            cookie_jar=aiohttp.CookieJar(unsafe=True)
        )
        self._authenticated = False
        self._auth_lock = asyncio.Lock()

    async def _login(self) -> None:
        """Authenticate and persist the session cookie in the jar."""
        payload = {"username": self._username, "password": self._password}
        async with async_timeout.timeout(10):
            async with self._session.post(
                f"{self._url}/api/auth/login",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as response:
                if response.status not in (200, 201):
                    response_text = await response.text()
                    raise RuntimeError(
                        "Immaculaterr login failed "
                        f"(status={response.status}, response={response_text})"
                    )

        self._authenticated = True

    async def _ensure_authenticated(self, force: bool = False) -> None:
        if self._authenticated and not force:
            return

        async with self._auth_lock:
            if self._authenticated and not force:
                return
            await self._login()

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Issue an authenticated request and return JSON."""
        await self._ensure_authenticated()

        headers = {"Accept": "application/json"}
        if json_data is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(2):
            async with async_timeout.timeout(15):
                async with self._session.request(
                    method,
                    f"{self._url}{path}",
                    params=params,
                    json=json_data,
                    headers=headers,
                ) as response:
                    if response.status == 401 and attempt == 0:
                        _LOGGER.debug(
                            "Immaculaterr session expired, retrying after re-login"
                        )
                        self._authenticated = False
                        await self._ensure_authenticated(force=True)
                        continue

                    if response.status not in (200, 201):
                        response_text = await response.text()
                        raise RuntimeError(
                            "Immaculaterr request failed "
                            f"(path={path}, status={response.status}, "
                            f"response={response_text})"
                        )

                    data = await response.json()
                    return data if isinstance(data, dict) else {"items": data}

        raise RuntimeError(f"Immaculaterr request retry budget exhausted for {path}")

    async def async_fetch_suggestions(
        self, media_type: str, library_section_key: str, mode: str = "review"
    ) -> dict[str, Any]:
        endpoint = "/api/observatory/immaculate-taste/movies"
        if media_type == "tv":
            endpoint = "/api/observatory/immaculate-taste/tv"

        return await self._request_json(
            "GET",
            endpoint,
            params={
                "librarySectionKey": library_section_key,
                "mode": mode,
            },
        )

    async def async_record_decision(
        self,
        *,
        library_section_key: str,
        media_type: str,
        suggestion_id: int,
        action: str,
    ) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/observatory/immaculate-taste/decisions",
            json_data={
                "librarySectionKey": library_section_key,
                "mediaType": media_type,
                "decisions": [{"id": suggestion_id, "action": action}],
            },
        )

    async def async_apply(
        self, *, library_section_key: str, media_type: str
    ) -> dict[str, Any]:
        return await self._request_json(
            "POST",
            "/api/observatory/immaculate-taste/apply",
            json_data={
                "librarySectionKey": library_section_key,
                "mediaType": media_type,
            },
        )

    async def close(self) -> None:
        if self._owns_session and self._session:
            await self._session.close()
