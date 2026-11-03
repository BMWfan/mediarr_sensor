from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
import unittest
from custom_components.mediarr import playback as m


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    def test_player_list_hides_unauthorized_entities(self):
        entries = [
            SimpleNamespace(
                domain="media_player", platform="plex", entity_id="media_player.allowed"
            ),
            SimpleNamespace(
                domain="media_player", platform="plex", entity_id="media_player.hidden"
            ),
            SimpleNamespace(
                domain="media_player", platform="androidtv", entity_id="media_player.tv"
            ),
        ]
        user = SimpleNamespace(
            permissions=SimpleNamespace(
                check_entity=lambda entity, policy: entity == "media_player.allowed"
            )
        )
        hass = SimpleNamespace(
            states=SimpleNamespace(
                get=lambda entity: SimpleNamespace(
                    state="idle", attributes={"friendly_name": "Allowed Plex"}
                )
            )
        )
        with patch.object(
            m.er,
            "async_get",
            return_value=SimpleNamespace(entities={e.entity_id: e for e in entries}),
        ):
            self.assertEqual(
                m.players(hass, user),
                [
                    {
                        "entity_id": "media_player.allowed",
                        "name": "Allowed Plex",
                        "available": True,
                    }
                ],
            )

    async def test_exact_server_and_item_are_delegated_with_user_context(self):
        source = {"provider": "plex"}
        library = SimpleNamespace(
            get=AsyncMock(
                return_value={"MediaContainer": {"machineIdentifier": "server-fixture"}}
            )
        )
        hass = SimpleNamespace(
            data={"mediarr": {"library_client": library}},
            services=SimpleNamespace(async_call=AsyncMock()),
        )
        user = SimpleNamespace(id="alice")
        with patch.object(
            m,
            "players",
            return_value=[{"entity_id": "media_player.plex_tv", "available": True}],
        ), patch.object(m, "configured_sources", return_value=[source]):
            result = await m.play(hass, user, "media_player.plex_tv", "0:42")
        self.assertTrue(result["accepted"])
        call = hass.services.async_call.call_args
        self.assertEqual(call.args[:2], ("media_player", "play_media"))
        self.assertEqual(call.args[2]["media_content_id"], "plex://server-fixture/42")
        self.assertEqual(call.kwargs["context"].user_id, "alice")

    async def test_unavailable_or_unauthorized_player_cannot_trigger_service(self):
        hass = SimpleNamespace(services=SimpleNamespace(async_call=AsyncMock()))
        with patch.object(m, "players", return_value=[]), patch.object(
            m, "configured_sources", return_value=[{"provider": "plex"}]
        ):
            with self.assertRaises(m.MediaDetailsError):
                await m.play(
                    hass, SimpleNamespace(id="alice"), "media_player.other", "0:42"
                )
        hass.services.async_call.assert_not_called()

    async def test_service_failure_does_not_report_success(self):
        library = SimpleNamespace(
            get=AsyncMock(
                return_value={"MediaContainer": {"machineIdentifier": "server-fixture"}}
            )
        )
        hass = SimpleNamespace(
            data={"mediarr": {"library_client": library}},
            services=SimpleNamespace(
                async_call=AsyncMock(side_effect=RuntimeError("Fixture failure"))
            ),
        )
        with patch.object(
            m,
            "players",
            return_value=[{"entity_id": "media_player.plex_tv", "available": True}],
        ), patch.object(m, "configured_sources", return_value=[{"provider": "plex"}]):
            with self.assertRaises(m.MediaDetailsError):
                await m.play(
                    hass, SimpleNamespace(id="alice"), "media_player.plex_tv", "0:42"
                )
