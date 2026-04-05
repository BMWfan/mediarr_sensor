"""Immaculaterr Observatory sensors for Mediarr."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from ..common.tmdb_sensor import TMDBMediaSensor
from .immaculaterr_client import ImmaculaterrClient

_LOGGER = logging.getLogger(__name__)


class ImmaculaterrMediarrSensor(TMDBMediaSensor):
    """Surface Immaculaterr Observatory suggestions as a sensor."""

    def __init__(
        self,
        url: str,
        username: str,
        password: str,
        media_type: str,
        library_section_key: str,
        max_items: int,
        mode: str = "review",
        tmdb_api_key: str | None = None,
    ) -> None:
        super().__init__(None, tmdb_api_key)
        self._url = url.rstrip("/")
        self._client = ImmaculaterrClient(url, username, password)
        self._session = self._client._session
        self._media_type = media_type
        self._library_section_key = str(library_section_key).strip()
        self._max_items = max_items
        self._mode = mode if mode in ("review", "pendingApproval") else "review"
        self._name = (
            "Immaculaterr Mediarr Movies"
            if media_type == "movie"
            else "Immaculaterr Mediarr TV"
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def unique_id(self) -> str:
        return (
            f"immaculaterr_mediarr_"
            f"{self._media_type}_{self._library_section_key}_{self._url}"
        )

    def _normalize_item_id(self, item: dict[str, Any]) -> int | None:
        raw_id = item.get("id")
        if isinstance(raw_id, int) and raw_id > 0:
            return raw_id
        if isinstance(raw_id, str) and raw_id.isdigit():
            value = int(raw_id)
            return value if value > 0 else None
        return None

    def _resolve_tmdb_id(self, item: dict[str, Any]) -> int | None:
        if self._media_type == "movie":
            return self._normalize_item_id(item)

        raw_tmdb_id = item.get("tmdbId")
        if isinstance(raw_tmdb_id, int) and raw_tmdb_id > 0:
            return raw_tmdb_id
        if isinstance(raw_tmdb_id, str) and raw_tmdb_id.isdigit():
            value = int(raw_tmdb_id)
            return value if value > 0 else None
        return None

    async def _build_card_item(
        self,
        item: dict[str, Any],
        approval_required: bool,
    ) -> dict[str, Any] | None:
        suggestion_id = self._normalize_item_id(item)
        if not suggestion_id:
            return None

        tmdb_id = self._resolve_tmdb_id(item)
        details: dict[str, Any] | None = None
        poster_url = item.get("posterUrl") or ""
        banner_url = ""
        fanart_url = ""

        if tmdb_id and self._tmdb_api_key:
            details = await self._get_tmdb_details(tmdb_id, self._media_type)
            fetched_poster, backdrop_url, main_backdrop_url = await self._get_tmdb_images(
                tmdb_id, self._media_type
            )
            poster_url = poster_url or fetched_poster or ""
            banner_url = backdrop_url or poster_url
            fanart_url = main_backdrop_url or backdrop_url or poster_url

        sent_at = item.get("sentToRadarrAt") or item.get("sentToSonarrAt")
        title = item.get("title") or (details or {}).get("title") or "Unknown"

        return {
            "id": suggestion_id,
            "tmdb_id": tmdb_id,
            "title": title,
            "overview": (details or {}).get("overview", ""),
            "year": (details or {}).get("year", ""),
            "poster": str(poster_url or ""),
            "banner": str(banner_url or poster_url or ""),
            "fanart": str(fanart_url or poster_url or ""),
            "type": "Movie" if self._media_type == "movie" else "TV Show",
            "media_type": self._media_type,
            "library_section_key": self._library_section_key,
            "download_approval": item.get("downloadApproval"),
            "approval_required_from_observatory": approval_required,
            "score": item.get("points"),
            "tmdb_vote_avg": item.get("tmdbVoteAvg"),
            "sent_at": sent_at,
            "status": item.get("status"),
        }

    async def async_update(self) -> None:
        try:
            payload = await self._client.async_fetch_suggestions(
                self._media_type,
                self._library_section_key,
                self._mode,
            )
            raw_items = payload.get("items", [])
            approval_required = bool(
                payload.get("approvalRequiredFromObservatory", False)
            )

            tasks = [
                self._build_card_item(item, approval_required)
                for item in raw_items[: self._max_items]
                if isinstance(item, dict)
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            card_items = []
            for result in results:
                if isinstance(result, Exception):
                    _LOGGER.error("Error processing Immaculaterr item: %s", result)
                    continue
                if result:
                    card_items.append(result)

            self._state = len(card_items)
            self._attributes = {
                "data": card_items,
                "media_type": self._media_type,
                "library_section_key": self._library_section_key,
                "mode": self._mode,
                "approval_required_from_observatory": approval_required,
            }
            self._available = True
        except Exception as err:
            _LOGGER.error("Error updating Immaculaterr sensor (%s): %s", self._name, err)
            self._state = 0
            self._attributes = {
                "data": [],
                "media_type": self._media_type,
                "library_section_key": self._library_section_key,
                "mode": self._mode,
            }
            self._available = False

    async def async_will_remove_from_hass(self) -> None:
        await self._client.close()
