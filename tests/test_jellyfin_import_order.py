"""Grouped TV imports retain the most recent episode timestamp."""
import unittest
from unittest.mock import AsyncMock, Mock

from custom_components.mediarr.server.jellyfin import JellyfinMediarrSensor


class JellyfinImportOrderTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_day_episodes_sort_by_latest_import(self):
        rows = [
            dict(title="Series", number="S01E01", episode="First", added_at="2026-01-02T08:00:00Z"),
            dict(title="Film", number="", added_at="2026-01-02T12:00:00Z"),
            dict(title="Series", number="S01E02", episode="Second", added_at="2026-01-02T16:00:00Z"),
        ]
        sensor = Mock()
        sensor._max_items = 10
        sensor._get_libraries = AsyncMock(return_value={"movies": [], "tvshows": ["library"]})
        sensor._fetch_recently_added = AsyncMock(return_value=rows)
        sensor._process_item = AsyncMock(side_effect=lambda row: dict(row, added="2026-01-02"))
        sensor._clean_unused_images = AsyncMock()
        await JellyfinMediarrSensor.async_update(sensor)
        self.assertTrue(sensor._available)
        series, film = sensor._attributes["data"]
        self.assertEqual((series["title"], film["title"]), ("Series", "Film"))
        self.assertEqual(series["added_at"], rows[2]["added_at"])
        self.assertEqual(series["number"], "S01E02")
