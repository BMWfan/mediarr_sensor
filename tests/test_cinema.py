"""TMDB remains the recommendation provider; accounts stay private per HA user."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from custom_components.mediarr import cinema as m
from custom_components.mediarr.collections import plex_collections


class CinemaTests(unittest.IsolatedAsyncioTestCase):
    def test_tmdb_options_accept_separate_application_read_token(self):
        from custom_components.mediarr.config_flow import (
            MediarrConfigFlow,
            MediarrOptionsFlow,
        )

        flow = object.__new__(MediarrConfigFlow)
        schema = flow._tmdb_schema("a" * 32)
        values = {
            "tmdb_api_key": "a" * 32,
            "tmdb_read_access_token": "application-fixture",
            "max_items": 10,
        }
        self.assertEqual(
            schema(values)["tmdb_read_access_token"], "application-fixture"
        )
        options = object.__new__(MediarrOptionsFlow)
        self.assertEqual(
            options._tmdb_schema({}, "a" * 32)(values)["tmdb_api_key"], "a" * 32
        )

    def client(self):
        client = object.__new__(m.CinemaClient)
        client.hass = SimpleNamespace(
            data={
                "mediarr": {
                    "yaml_config": {
                        "tmdb": {"tmdb_read_access_token": "application-fixture"}
                    }
                }
            }
        )
        client.metadata = SimpleNamespace(
            key_resolver=lambda: "catalog-fixture",
            slots=asyncio.Semaphore(4),
            _get=AsyncMock(return_value={"results": []}),
        )
        client.accounts = {}
        client.pending = {}
        client.cache = {}
        client.lock = asyncio.Lock()
        client.store = SimpleNamespace(async_save=AsyncMock())
        return client

    async def test_account_approval_is_per_user_and_never_returns_access_tokens(self):
        client = self.client()
        client.api4 = AsyncMock(
            side_effect=[
                {"request_token": "request-fixture"},
                {
                    "account_id": "account-fixture",
                    "access_token": "private-user-fixture",
                },
            ]
        )
        start = await client.account("alice", "start")
        self.assertIn("request_token=request-fixture", start["authorization_url"])
        again = await client.account("alice", "start")
        self.assertEqual(start, again)
        self.assertEqual(client.api4.await_count, 1)
        finished = await client.account("alice", "finish")
        self.assertEqual(finished, {"connected": True, "can_connect": True})
        self.assertNotIn("private-user-fixture", str(finished))
        self.assertFalse((await client.account("bob", "status"))["connected"])
        with self.assertRaises(m.MediaDetailsError):
            await client.account("bob", "finish")
        self.assertEqual(
            client.accounts["alice"]["access_token"], "private-user-fixture"
        )
        await client.account("bob", "disconnect")
        self.assertIn("alice", client.accounts)
        await client.account("alice", "disconnect")
        self.assertNotIn("alice", client.accounts)

    async def test_recommendations_use_native_account_api_and_preserve_ranking(self):
        client = self.client()
        client.accounts = {
            "alice": {"account_id": "alice-account", "access_token": "alice-only-token"}
        }

        async def api(method, endpoint, token, *args, **kwargs):
            self.assertEqual(token, "alice-only-token")
            self.assertTrue(endpoint.startswith("account/alice-account/"))
            return {
                "results": [
                    {"id": 8, "title": "First", "name": "First"},
                    {"id": 3, "title": "Second", "name": "Second"},
                ]
            }

        client.api4 = api
        result = await client.discover("alice", "de", "week", "DE")
        self.assertEqual(
            [(x["media_type"], x["tmdb_id"]) for x in result["personal"]],
            [("movie", 8), ("tv", 8), ("movie", 3), ("tv", 3)],
        )
        self.assertNotIn("alice-only-token", str(result))
        other = await client.discover("bob", "de", "week", "DE")
        self.assertEqual(other["personal"], [])
        self.assertEqual(other["errors"]["personal"], "tmdb_account_not_connected")

    async def test_no_account_does_not_block_trending_or_upcoming(self):
        client = self.client()

        async def get(endpoint, *args, **kwargs):
            if endpoint.startswith("trending"):
                return {
                    "results": [
                        {"id": 1, "title": "Trending", "media_type": "movie"},
                        {"id": 2, "name": "Actor", "media_type": "person"},
                    ]
                }
            return {
                "results": [
                    {
                        "id": 3,
                        "title": "Future",
                        "name": "Future",
                        "release_date": "2030-01-01",
                    }
                ]
            }

        client.metadata._get = get
        result = await client.discover("alice", "de", "day", "DE")
        self.assertEqual(len(result["trending"]), 1)
        self.assertEqual(len(result["upcoming"]), 2)
        self.assertEqual(result["personal"], [])

    def test_application_read_token_is_not_confused_with_v3_api_key(self):
        self.assertIsNone(
            m.tmdb_application_token({"yaml_config": {"tmdb_api_key": "a" * 32}})
        )
        self.assertEqual(
            m.tmdb_application_token(
                {
                    "yaml_config": {
                        "tmdb": {"tmdb_read_access_token": "explicit-fixture"}
                    }
                }
            ),
            "explicit-fixture",
        )

    def test_schema_disallows_account_impersonation(self):
        with self.assertRaises(Exception):
            m.websocket_tmdb_account._ws_schema(
                {
                    "id": 1,
                    "type": "mediarr/tmdb_account",
                    "action": "status",
                    "user_id": "other",
                }
            )

    async def test_smart_collection_membership_is_read_from_plex(self):
        client = SimpleNamespace(
            hass=SimpleNamespace(),
            get=AsyncMock(
                side_effect=[
                    {"MediaContainer": {"Directory": [{"key": "1", "type": "movie"}]}},
                    {
                        "MediaContainer": {
                            "Metadata": [
                                {
                                    "ratingKey": "42",
                                    "title": "Unwatched thrillers",
                                    "smart": 1,
                                }
                            ],
                            "size": 1,
                        }
                    },
                    {
                        "MediaContainer": {
                            "Metadata": [{"ratingKey": "7"}, {"ratingKey": "8"}],
                            "size": 2,
                        }
                    },
                ]
            ),
        )
        with patch(
            "custom_components.mediarr.collections.configured_sources",
            return_value=[{"provider": "plex"}],
        ):
            listed = await plex_collections(client)
            self.assertEqual(listed["collections"][0]["id"], "0:42")
            self.assertTrue(listed["collections"][0]["smart"])
            self.assertEqual(
                (await plex_collections(client, "0:42"))["keys"], ["0:7", "0:8"]
            )
            with self.assertRaises(m.MediaDetailsError):
                await plex_collections(client, "0:../../secret")
