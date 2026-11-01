"""Selected catalog IDs must reach Seerr unchanged; failures must reach HA."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from custom_components.mediarr.services.seer_requests import (
    SeerRequestHandler,
    MOVIE_REQUEST_SCHEMA,
    TV_REQUEST_SCHEMA,
    async_setup_services,
)
from homeassistant.exceptions import HomeAssistantError


class Response:
    def __init__(self, status=201):
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def text(self):
        return "Test rejection"


class Session:
    def __init__(self, status=201):
        self.calls = []
        self.status = status

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.status)


class RequestTests(unittest.IsolatedAsyncioTestCase):
    def handler(self):
        handler = object.__new__(SeerRequestHandler)
        handler._url = "https://seer.invalid"
        handler._headers = {}
        handler._session = Session()
        handler.async_search_media = AsyncMock(
            side_effect=AssertionError("Must not search by title with a known ID")
        )
        return handler

    async def test_movie_and_tv_use_selected_id_without_title_search(self):
        handler = self.handler()
        self.assertTrue(
            await handler.async_request_movie(
                SimpleNamespace(data={"name": "Remake", "tmdb_id": 99})
            )
        )
        self.assertEqual(
            handler._session.calls[-1][1]["json"], {"mediaType": "movie", "mediaId": 99}
        )
        self.assertTrue(
            await handler.async_request_tv(
                SimpleNamespace(data={"name": "Remake", "tmdb_id": 77, "season": "all"})
            )
        )
        self.assertEqual(
            handler._session.calls[-1][1]["json"],
            {"mediaType": "tv", "mediaId": 77, "seasons": "all"},
        )
        handler.async_search_media.assert_not_called()

    async def test_registered_services_report_rejection(self):
        callbacks = {}
        services = SimpleNamespace(
            has_service=lambda *args: False,
            async_register=lambda domain, name, callback, **kwargs: callbacks.update(
                {name: callback}
            ),
        )
        handler = SimpleNamespace(
            async_request_movie=AsyncMock(return_value=False),
            async_request_tv=AsyncMock(return_value=False),
        )
        hass = SimpleNamespace(
            services=services, data={"mediarr": {"seer_request_handler": handler}}
        )
        await async_setup_services(hass, "mediarr")
        for name in ["submit_movie_request", "submit_tv_request"]:
            with self.assertRaises(HomeAssistantError):
                await callbacks[name](SimpleNamespace(data={"name": "Rejected"}))

    def test_id_schema_and_backward_compatibility(self):
        for schema in [MOVIE_REQUEST_SCHEMA, TV_REQUEST_SCHEMA]:
            self.assertEqual(schema({"name": "Legacy"})["name"], "Legacy")
            self.assertEqual(schema({"name": "Selected", "tmdb_id": 99})["tmdb_id"], 99)
            for invalid in [True, 0, -1, "99"]:
                with self.assertRaises(Exception):
                    schema({"name": "Bad", "tmdb_id": invalid})
