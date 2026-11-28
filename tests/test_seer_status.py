"""Actual-shaped Seerr requests retain distinct request/media enums (offline)."""
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from custom_components.mediarr.services.seer import SeerMediarrSensor
from custom_components.mediarr.services import seer_requests


class Response:
    status = 200

    def __init__(self, rows):
        self.rows = rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def json(self):
        return {"results": self.rows}


class Session:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(url)
        if url != "https://seer.invalid/api/v1/request":
            raise AssertionError("Unexpected transport destination")
        return Response(self.rows)


class SeerStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_unloading_requests_preserves_shared_http_session(self):
        hass = Mock()
        session = Mock(close=AsyncMock())
        with patch.object(seer_requests, 'async_get_clientsession', return_value=session) as shared:
            handler = seer_requests.SeerRequestHandler(hass, 'https://seer.invalid', 'synthetic')
        shared.assert_called_once_with(hass)
        self.assertIs(handler._session, session)
        hass.data = {'mediarr': {'seer_request_handler': handler}}
        await seer_requests.async_unload_services(hass, 'mediarr')
        session.close.assert_not_awaited()

    async def test_request_and_media_status_are_additive_and_independent(self):
        contract = json.loads((Path(__file__).parent / 'contracts/v1.json').read_text())
        for case in contract['seerr_cases']:
            request_status, media_status, kind = case['request_status'], case['media_status'], case['kind']
            with self.subTest(request=request_status, media=media_status):
                media = {'mediaType': kind, 'tmdbId': 91}
                if media_status is not None:
                    media['status'] = media_status
                session = Session([{'id': 401, 'status': request_status, 'media': media,
                                    'createdAt': '2026-01-02T03:04:05Z',
                                    'requestedBy': {'displayName': 'Synthetic user'}}])
                sensor = SeerMediarrSensor(session, 'synthetic', 'https://seer.invalid', 'synthetic', 10)
                sensor._get_tmdb_details = AsyncMock(return_value={'title': 'Synthetic request', 'overview': 'Fixture', 'year': '2026'})
                sensor._get_tmdb_images = AsyncMock(return_value=(None, None, None))
                await sensor.async_update()
                self.assertTrue(sensor.available)
                data = sensor.extra_state_attributes['data'][0]
                self.assertEqual(data['status'], request_status)
                self.assertEqual(data['request_status'], request_status)
                self.assertEqual(data['media_status'], media_status)
                self.assertEqual(data['request_id'], 401)
                self.assertEqual(data['tmdb_id'], 91)
                self.assertEqual(data['media_type'], kind)
                self.assertEqual(data['requested_date'], '2026-01-02')
                self.assertEqual(data['release'], '2026-01-02', 'legacy request date must remain intact, not an import timestamp')
                self.assertEqual(session.calls, ['https://seer.invalid/api/v1/request'])
                self.assertNotIn('has_file', data, 'request approval/completion must not invent file evidence')
