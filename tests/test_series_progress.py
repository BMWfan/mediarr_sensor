import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from custom_components.mediarr.series_progress import (
    episode_progress,
    section_episode_progress,
)
from custom_components.mediarr.media_details import MediaDetailsError


def episode(season, number, **extra):
    return {
        "grandparentRatingKey": "7",
        "parentIndex": season,
        "index": number,
        **extra,
    }


class SeriesProgressTests(unittest.IsolatedAsyncioTestCase):
    def test_old_gaps_do_not_revive_watched_latest_season(self):
        progress = episode_progress(
            [episode(1, 1), episode(4, 1, viewCount=1), episode(4, 2, viewOffset=500)]
        )
        self.assertEqual(progress["unwatched_count"], 0)
        self.assertEqual(progress["position"], {"season": 4, "episode": 2})

    def test_only_later_available_episodes_and_next_season_are_counted(self):
        progress = episode_progress(
            [
                episode(1, 1),
                episode(4, 5, viewCount=1),
                episode(4, 6),
                episode(4, 7),
                episode(4, 9),
                episode(5, 1),
                episode(0, 9),
            ]
        )
        self.assertEqual(progress["unwatched_count"], 4)
        self.assertEqual(
            progress["ranges"],
            [
                {"season": 4, "first": 6, "last": 7},
                {"season": 4, "first": 9, "last": 9},
                {"season": 5, "first": 1, "last": 1},
            ],
        )

    def test_never_started_and_duplicate_episode_versions(self):
        progress = episode_progress([episode(1, 1), episode(1, 1), episode(1, 2)])
        self.assertFalse(progress["started"])
        self.assertEqual(progress["unwatched_count"], 2)
        self.assertFalse(episode_progress([{"index": "bad"}])["available"])

    async def test_section_pagination_groups_by_show_and_uses_episode_type(self):
        client = SimpleNamespace(
            get=AsyncMock(
                side_effect=[
                    {
                        "MediaContainer": {
                            "totalSize": 2,
                            "Metadata": [episode(1, 1, viewCount=1)],
                        }
                    },
                    {"MediaContainer": {"totalSize": 2, "Metadata": [episode(1, 2)]}},
                ]
            )
        )
        result = await section_episode_progress(client, {}, "3")
        self.assertEqual(result["7"]["unwatched_count"], 1)
        self.assertEqual(
            client.get.call_args_list[1].kwargs["X-Plex-Container-Start"], 1
        )
        self.assertEqual(client.get.call_args_list[0].kwargs["type"], 4)

    async def test_missing_page_is_not_reported_as_zero_new_episodes(self):
        client = SimpleNamespace(
            get=AsyncMock(
                return_value={"MediaContainer": {"totalSize": 1, "Metadata": []}}
            )
        )
        with self.assertRaises(MediaDetailsError):
            await section_episode_progress(client, {}, "3")
