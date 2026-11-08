"""Full-source pagination and honest queue/recommendation state."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest

from custom_components.mediarr import library as m


class LibraryTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client = object.__new__(m.LibraryClient)
        client.hass = SimpleNamespace(data={})
        client.cached = None
        client.cached_at = 0
        client.lock = asyncio.Lock()
        return client

    async def test_full_plex_pagination_and_all_manager_titles_with_queue(self):
        client = self.client()
        sources = [{"provider": "plex"}, {"provider": "radarr"}]
        first = [
            {
                "ratingKey": str(i),
                "type": "movie",
                "title": f"Movie {i}",
                "Guid": [{"id": f"tmdb://{i+1}"}],
            }
            for i in range(100)
        ]
        client.get = AsyncMock(
            side_effect=[
                {
                    "MediaContainer": {
                        "Directory": [
                            {"key": "1", "type": "movie"},
                            {"key": "2", "type": "artist"},
                        ]
                    }
                },
                {"MediaContainer": {"totalSize": 101, "Metadata": first}},
                {
                    "MediaContainer": {
                        "totalSize": 101,
                        "Metadata": [
                            {
                                "ratingKey": "101",
                                "type": "movie",
                                "title": "Old watched movie",
                                "viewCount": 1,
                                "Guid": [{"id": "tmdb://999"}],
                            }
                        ],
                    }
                },
                [
                    {
                        "id": 1,
                        "tmdbId": 500,
                        "title": "Future movie",
                        "hasFile": False,
                        "monitored": True,
                    }
                ],
                {
                    "records": [
                        {
                            "movieId": 1,
                            "size": 100,
                            "sizeleft": 32,
                            "status": "downloading",
                        }
                    ],
                    "totalRecords": 1,
                },
            ]
        )
        with patch.object(m, "configured_sources", return_value=sources):
            result = await client.snapshot()
        self.assertEqual(len(result["groups"]["plex"]), 101)
        self.assertTrue(result["groups"]["plex"][-1]["watched"])
        self.assertEqual(result["groups"]["radarr"][0]["download_progress"], 68)
        self.assertTrue(result["complete"])
        self.assertEqual(
            client.get.call_args_list[2].kwargs["X-Plex-Container-Start"], 100
        )
        with patch.object(
            m,
            "configured_sources",
            side_effect=AssertionError("Cached result expected"),
        ):
            self.assertEqual(await client.snapshot(), result)

    async def test_show_progress_and_cover_art_reach_library_snapshot(self):
        client = self.client()
        client.get = AsyncMock(side_effect=[
            {"MediaContainer":{"Directory":[{"key":"3","type":"show"}]}},
            {"MediaContainer":{"Metadata":[{"ratingKey":"7","type":"show","title":"Series","leafCount":3,"viewedLeafCount":1}],"totalSize":1}},
            {"MediaContainer":{"Metadata":[{"grandparentRatingKey":"7","parentIndex":4,"index":1,"viewCount":1},{"grandparentRatingKey":"7","parentIndex":4,"index":2}],"totalSize":2}},
        ])
        with patch.object(m,"configured_sources",return_value=[{"provider":"plex"}]):
            snapshot=await client.snapshot()
        self.assertEqual(snapshot["groups"]["plex"][0]["episode_progress"]["unwatched_count"],1)
        self.assertTrue(snapshot["complete"])

    async def test_episode_failure_keeps_show_with_explicit_unknown_status(self):
        client=self.client()
        client.get=AsyncMock(side_effect=[
            {"MediaContainer":{"Directory":[{"key":"3","type":"show"}]}},
            {"MediaContainer":{"Metadata":[{"ratingKey":"7","type":"show","title":"Series","leafCount":3}],"totalSize":1}},
            m.MediaDetailsError("library_unavailable","Unavailable"),
        ])
        with patch.object(m,"configured_sources",return_value=[{"provider":"plex"}]):
            result=await client.snapshot()
        self.assertEqual(result["groups"]["plex"][0]["episode_progress"],{"available":False})
        self.assertFalse(result["complete"])
        self.assertEqual(result["errors"][0]["code"],"episode_progress_unavailable")

    def test_manager_artwork_only_exposes_public_cdns_without_query_credentials(self):
        raw={"images":[{"coverType":"poster","remoteUrl":"https://private.invalid/poster?apikey=secret"},{"coverType":"poster","remoteUrl":"https://image.tmdb.org/t/p/original/test.jpg?token=secret"}]}
        self.assertEqual(m.manager_artwork(raw,"poster"),"https://image.tmdb.org/t/p/original/test.jpg")
        self.assertEqual(m.manager_artwork({"images":[{"coverType":"poster","remoteUrl":"https://image.tmdb.org:bad/file"}]},"poster"),"")
        self.assertEqual(m.manager_artwork(raw,"fanart"),"")

    async def test_partial_source_failure_is_explicit_and_preserves_other_sources(self):
        client = self.client()
        client.get = AsyncMock(
            side_effect=[
                m.MediaDetailsError("library_unavailable", "Unavailable"),
                [],
                {"records": [], "totalRecords": 0},
            ]
        )
        with patch.object(
            m,
            "configured_sources",
            return_value=[{"provider": "plex"}, {"provider": "radarr"}],
        ):
            result = await client.snapshot()
        self.assertFalse(result["complete"])
        self.assertEqual(result["errors"][0]["provider"], "plex")

    def test_queue_states_do_not_invent_percentages(self):
        result = m.queue_state(
            [
                {"movieId": 1, "status": "paused", "size": 0},
                {
                    "seriesId": 2,
                    "status": "completed",
                    "trackedDownloadState": "importPending",
                    "size": 100,
                    "sizeleft": 0,
                },
            ]
        )
        self.assertIsNone(result[1]["download_progress"])
        self.assertEqual(result[1]["download_status"], "paused")
        self.assertEqual(
            result[2], {"download_progress": 100, "download_status": "importing"}
        )

    def test_plex_ids_and_watched_state(self):
        result = m.plex_item(
            {
                "type": "show",
                "leafCount": 10,
                "viewedLeafCount": 3,
                "guid": "com.plexapp.agents.themoviedb://7?lang=en",
            }
        )
        self.assertFalse(result["watched"])
        self.assertTrue(result["has_watched"])
        self.assertEqual(result["tmdb_id"], "7")
        self.assertEqual(result["media_type"], "tv")

    def test_library_websocket_schema(self):
        parsed = m.websocket_library._ws_schema({"id": 1, "type": "mediarr/library"})
        self.assertEqual(parsed["page"], 1)
