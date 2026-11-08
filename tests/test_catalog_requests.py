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
    def __init__(self, status=201, data=None):
        self.status = status
        self.data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def text(self):
        return "Test rejection"

    async def json(self):
        return self.data


class Session:
    def __init__(self, status=201, get_status=200, data=None):
        self.calls = []
        self.status = status
        self.get_status=get_status
        self.data=data

    def get(self,url,**kwargs):
        self.calls.append((url,kwargs))
        return Response(self.get_status,self.data)

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.status)


class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_title_search_passes_raw_unicode_query_and_never_uses_wrong_type(self):
        handler=self.handler()
        handler._session=Session(data={"results":[{"id":7,"mediaType":"movie"}]})
        query="Léon & die Nacht"
        result=await SeerRequestHandler.async_search_media(handler,query,"movie")
        self.assertEqual(result["id"],7)
        self.assertEqual(handler._session.calls[0][1]["params"],{"query":query})
        self.assertIsNone(await SeerRequestHandler.async_search_media(handler,query,"tv"))

    async def test_latest_season_uses_real_positive_season_and_rejects_lookup_failure(self):
        handler=self.handler()
        handler._session=Session(data={"seasons":[{"seasonNumber":0},{"seasonNumber":1},{"seasonNumber":4}]})
        call=SimpleNamespace(data={"name":"Series","tmdb_id":77,"season":"latest"})
        self.assertTrue(await handler.async_request_tv(call))
        self.assertEqual(handler._session.calls[-1][1]["json"]["seasons"],[4])
        for status,data in [(503,None),(200,{"seasons":[]})]:
            handler._session=Session(get_status=status,data=data)
            self.assertFalse(await handler.async_request_tv(call))
            self.assertEqual(len(handler._session.calls),1,"failed season lookup must never silently request season one")

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
