"""Producer-side contract checks use real backend functions with synthetic state."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from custom_components.mediarr.request_capabilities import capabilities
from custom_components.mediarr.media_details import websocket_media_details, MediaDetailsError

CONTRACT = json.loads((Path(__file__).parent / 'contracts/v1.json').read_text())


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_unconfigured_backend_returns_independent_disabled_capabilities(self):
        self.assertEqual(await capabilities(SimpleNamespace(data={})), CONTRACT['missing_capabilities'])

    async def test_metadata_command_preserves_typed_identity_and_optional_fields(self):
        # HA's async_response wrapper schedules a task. Capture and await it.
        for result in [CONTRACT['details'], {'media_type': 'tv', 'tmdb_id': 77}]:
            tasks = []
            client = SimpleNamespace(slots=asyncio.Semaphore(1), details=AsyncMock(return_value=result))
            hass = SimpleNamespace(data={'mediarr': {'metadata_client': client}},
                async_create_background_task=lambda coro, *args, **kwargs: tasks.append(asyncio.create_task(coro)))
            connection = SimpleNamespace(send_result=Mock(), send_error=Mock(),
                async_create_task=lambda coro: tasks.append(asyncio.create_task(coro)))
            websocket_media_details(hass, connection, {'id': 3, 'type': 'mediarr/media_details', 'media_type': 'tv', 'tmdb_id': 77})
            await asyncio.gather(*tasks)
            connection.send_result.assert_called_once_with(3, result)
            connection.send_error.assert_not_called()
            client.details.assert_awaited_once_with(media_type='tv', tmdb_id=77)

    async def test_metadata_errors_use_error_envelope_without_success(self):
        tasks = []
        client = SimpleNamespace(slots=asyncio.Semaphore(1),
            details=AsyncMock(side_effect=MediaDetailsError('metadata_unavailable', 'Unavailable')))
        hass = SimpleNamespace(data={'mediarr': {'metadata_client': client}},
                async_create_background_task=lambda coro, *args, **kwargs: tasks.append(asyncio.create_task(coro)))
        connection = SimpleNamespace(send_result=Mock(), send_error=Mock(),
            async_create_task=lambda coro: tasks.append(asyncio.create_task(coro)))
        websocket_media_details(hass, connection, {'id': 4, 'type': 'mediarr/media_details', 'tmdb_id': 77})
        await asyncio.gather(*tasks)
        connection.send_error.assert_called_once_with(4, 'metadata_unavailable', 'Unavailable')
        connection.send_result.assert_not_called()
