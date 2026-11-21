"""Private snapshot persistence, freshness, isolation and failure contracts."""
import asyncio
from copy import deepcopy
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from custom_components.mediarr.snapshot_cache import SnapshotCache, MAX_STALE_SECONDS
from custom_components.mediarr.media_details import MediaDetailsClient, MediaDetailsError
from custom_components.mediarr.library import LibraryClient, plex_item
from custom_components.mediarr import library as library_module


class MemoryStore:
    def __init__(self):
        self.data = None

    async def async_load(self):
        return deepcopy(self.data)

    def async_delay_save(self, factory, delay):
        self.data = deepcopy(factory())


SOURCES = [{"provider": "plex", "url": "https://fixture.invalid", "token": "synthetic-credential"}]


def snapshot(title="Film"):
    return {"groups": {"plex": [{"title": title, "_source_checked_at": time.time()}]}, "complete": True, "errors": []}


class SnapshotTests(unittest.IsolatedAsyncioTestCase):
    def cache(self, fetch=None, store=None):
        self.hass = SimpleNamespace(data={}, bus=SimpleNamespace(async_fire=Mock()))
        return SnapshotCache(self.hass, fetch or AsyncMock(return_value=snapshot()), store)

    async def test_persistent_restore_retains_identity_but_not_credentials(self):
        store = MemoryStore()
        first = self.cache(store=store)
        initial = await first.read(SOURCES)
        self.assertNotIn("synthetic-credential", json.dumps(store.data))
        self.assertNotIn("fixture.invalid", json.dumps(store.data))
        restored = self.cache(store=store)
        result = await restored.read(SOURCES)
        self.assertEqual(result, initial)
        restored.fetch.assert_not_awaited()

    async def test_broken_optional_storage_does_not_break_fresh_reads(self):
        store = SimpleNamespace(async_load=AsyncMock(side_effect=OSError('fixture')), async_delay_save=Mock(side_effect=OSError('fixture')))
        cache = self.cache(store=store)
        result = await cache.read(SOURCES)
        self.assertTrue(result['complete'])
        self.assertEqual(result['groups']['plex'][0]['title'], 'Film')

    async def test_expired_snapshot_revision_is_retryable_and_history_bounded(self):
        cache = self.cache()
        first = await cache.read(SOURCES)
        for index in range(6):
            cache.fetch.return_value = snapshot(str(index))
            await cache.read(SOURCES, force=True)
        self.assertEqual(len(cache.history), 4)
        with self.assertRaises(MediaDetailsError) as error:
            await cache.read(SOURCES, snapshot_id=first['revision'])
        self.assertEqual(error.exception.code, 'library_snapshot_expired')

    async def test_changed_credentials_and_expired_storage_do_not_restore(self):
        store = MemoryStore()
        await self.cache(store=store).read(SOURCES)
        changed = self.cache(store=store)
        await changed.read([{**SOURCES[0], "token": "other-fixture"}])
        changed.fetch.assert_awaited_once()
        store.data["checked"] = time.time() - MAX_STALE_SECONDS - 1
        expired = self.cache(store=store)
        await expired.read([{**SOURCES[0], "token": "other-fixture"}])
        expired.fetch.assert_awaited_once()

    async def test_concurrent_forced_readers_share_one_request(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        async def fetch(*args):
            entered.set()
            await finish.wait()
            return snapshot()
        cache = self.cache(AsyncMock(side_effect=fetch))
        readers = [asyncio.create_task(cache.read(SOURCES, force=True)) for _ in range(8)]
        await entered.wait()
        await asyncio.sleep(0)
        finish.set()
        results = await asyncio.gather(*readers)
        self.assertEqual(len({r["revision"] for r in results}), 1)
        cache.fetch.assert_awaited_once()

    async def test_stale_immediate_result_and_failed_refresh_keep_films(self):
        cache = self.cache()
        original = await cache.read(SOURCES)
        cache.checked -= 30
        cache.fetch.side_effect = MediaDetailsError("library_unavailable", "synthetic failure")
        stale = await cache.read(SOURCES)
        self.assertEqual(stale["groups"], original["groups"])
        self.assertEqual(stale["cache"]["state"], "stale")
        with self.assertRaises(MediaDetailsError):
            await cache.flight
        calls = cache.fetch.await_count
        failed = await cache.read(SOURCES)
        self.assertFalse(failed["complete"])
        self.assertEqual(failed["groups"], original["groups"])
        self.assertEqual(cache.fetch.await_count, calls, "backoff prevents request storms")
        self.assertGreater(cache.retry_at, time.monotonic())

    async def test_unchanged_revision_and_pinned_pages_are_stable(self):
        cache = self.cache()
        original = await cache.read(SOURCES)
        cache.fetch.return_value = snapshot()
        same = await cache.read(SOURCES, force=True)
        self.assertEqual(same["revision"], original["revision"])
        cache.fetch.return_value = snapshot("New film")
        changed = await cache.read(SOURCES, force=True)
        self.assertNotEqual(changed["revision"], original["revision"])
        pinned = await cache.read(SOURCES, snapshot_id=original["revision"])
        self.assertEqual(pinned["groups"]["plex"][0]["title"], "Film")
        self.assertEqual(original["groups"]["plex"][0]["title"], "Film")

    async def test_configuration_change_discards_old_inflight_response(self):
        entered, finish = asyncio.Event(), asyncio.Event()
        async def fetch(sources, *args):
            if sources == SOURCES:
                entered.set()
                await finish.wait()
                return snapshot("Old private film")
            return snapshot("New profile film")
        cache = self.cache(fetch)
        old = asyncio.create_task(cache.read(SOURCES))
        await entered.wait()
        new = await cache.read([{**SOURCES[0], "token": "new-profile"}])
        finish.set()
        with self.assertRaises(MediaDetailsError):
            await old
        self.assertEqual(cache.data["groups"], new["groups"])

    async def test_provider_failure_is_not_confirmed_deletion(self):
        client = object.__new__(LibraryClient)
        client.hass = SimpleNamespace(data={})
        previous = {"groups": {"plex": [{"title": "Keep me", "_source_id": 0, "_source_checked_at": time.time()}]}}
        sources = [{"provider": "plex"}]
        client.get = AsyncMock(side_effect=MediaDetailsError("library_unavailable", "Failure"))
        failed = await client._collect_snapshot(sources, previous, True)
        self.assertFalse(failed["complete"])
        self.assertEqual(failed["groups"]["plex"][0]["title"], "Keep me")
        self.assertTrue(failed["groups"]["plex"][0]["availability_stale"])
        client.get = AsyncMock(return_value={"MediaContainer": {"Directory": []}})
        empty = await client._collect_snapshot(sources, previous, True)
        self.assertTrue(empty["complete"])
        self.assertEqual(empty["groups"]["plex"], [])

    async def test_catalog_cache_never_caches_live_plex_identity(self):
        client = object.__new__(LibraryClient)
        client._get_uncached = AsyncMock(return_value={"MediaContainer": {}})
        await client.get(SOURCES[0], "/library/sections")
        await client.get(SOURCES[0], "/library/sections")
        self.assertEqual(client._get_uncached.await_count, 1)
        await client.get(SOURCES[0], "/identity")
        await client.get(SOURCES[0], "/identity")
        self.assertEqual(client._get_uncached.await_count, 3)

    async def test_queue_progress_does_not_invalidate_catalog_but_import_does(self):
        client = object.__new__(LibraryClient)
        queue = {"records": [{"movieId": 7, "status": "downloading", "sizeleft": 90}]}
        client._get_uncached = AsyncMock(side_effect=[[], queue, {"records": [{**queue["records"][0], "sizeleft": 30}]}, {"records": []}, []])
        source = {"provider": "radarr"}
        await client.get(source, "/api/v3/movie")
        with patch("custom_components.mediarr.library.time.monotonic", return_value=time.monotonic() - 10):
            await client.get(source, "/api/v3/queue")
        await client.get(source, "/api/v3/queue")
        await client.get(source, "/api/v3/movie")
        self.assertEqual(client._get_uncached.await_count, 3)
        client._http_cache = {k: v for k, v in client._http_cache.items() if not k[1].endswith('/queue')}
        await client.get(source, "/api/v3/queue")
        await client.get(source, "/api/v3/movie")
        self.assertEqual(client._get_uncached.await_count, 5)

    async def test_identity_survives_restart_without_creating_ownership(self):
        store = MemoryStore()
        client = MediaDetailsClient(None, lambda: "fixture")
        client.identity_store = store
        await client.ensure_identities()
        client.remember_identity({"media_type": "movie", "tmdb_id": 77, "title": "Film", "year": "2020", "imdb_id": "tt0000077"})
        restored = MediaDetailsClient(None, lambda: "fixture")
        restored.identity_store = store
        await restored.ensure_identities()
        self.assertEqual(restored.identity_for("movie", "Film", 2020), 77)
        self.assertEqual(restored.identity_for("movie", "Film", 2020, tvdb_id=123, imdb_id="tt0000077"), 77)
        self.assertIsNone(restored.identity_for("tv", "Film", 2020))
        self.assertIsNone(restored.identity_for("movie", "Film", 2021))
        self.assertIsNone(restored.identity_for("movie", "Film", 2020, imdb_id="tt9999999"))
        self.assertNotIn("has_file", json.dumps(store.data))
        restored.remember_identity({"media_type": "movie", "tmdb_id": 88, "title": "Film", "year": "2020"})
        self.assertIsNone(restored.identity_for("movie", "Film", 2020))

    def test_file_upgrade_does_not_change_added_time_or_art_versions(self):
        raw = {"ratingKey": "77", "type": "movie", "title": "Film", "addedAt": 1700000000,
               "updatedAt": 1700000000, "thumb": "/thumb/1", "art": "/art/1"}
        first = plex_item(raw)
        upgrade = plex_item({**raw, "updatedAt": 1800000000})
        self.assertEqual(first["added"], upgrade["added"])
        self.assertEqual(first["_thumb_revision"], upgrade["_thumb_revision"])
        self.assertEqual(first["_art_revision"], upgrade["_art_revision"])
        new_poster = plex_item({**raw, "thumb": "/thumb/2"})
        self.assertNotEqual(first["_thumb_revision"], new_poster["_thumb_revision"])
        self.assertEqual(first["_art_revision"], new_poster["_art_revision"])
        self.assertFalse(plex_item({**raw, "thumb": ""})["_has_thumb"])

    async def test_versioned_image_hit_uses_private_etag_without_upstream_read(self):
        from collections import OrderedDict
        from custom_components.mediarr.snapshot_cache import source_scope
        version = '1234567890abcdef'
        key = (source_scope(SOURCES), '77', 'thumb', version)
        client = SimpleNamespace(image_cache=OrderedDict({key: (time.monotonic(), b'image-fixture', 'image/png', '"fixture-etag"')}))
        hass = SimpleNamespace(data={'mediarr': {'library_client': client}})
        request = SimpleNamespace(app={library_module.KEY_HASS: hass}, query={'v': version}, headers={})
        with patch.object(library_module, 'configured_sources', return_value=SOURCES), patch.object(library_module, 'async_get_clientsession') as session:
            response = await library_module.LibraryImageView().get(request, '0', '77')
            self.assertEqual(response.status, 200)
            self.assertEqual(response.body, b'image-fixture')
            self.assertIn('private', response.headers['Cache-Control'])
            request.headers['If-None-Match'] = response.headers['ETag']
            response = await library_module.LibraryImageView().get(request, '0', '77')
            self.assertEqual(response.status, 304)
            session.assert_not_called()

    async def test_old_profile_image_scope_is_rejected(self):
        from aiohttp import web
        cache = SimpleNamespace(scope='old-config', public_scope='old-profile')
        hass = SimpleNamespace(data={'mediarr': {'library_client': SimpleNamespace(_snapshot_cache=cache)}})
        request = SimpleNamespace(app={library_module.KEY_HASS: hass}, query={'scope': 'old-profile'}, headers={})
        with patch.object(library_module, 'configured_sources', return_value=SOURCES):
            with self.assertRaises(web.HTTPNotFound) as error:
                await library_module.LibraryImageView().get(request, '0', '77')
            self.assertEqual(error.exception.headers['Cache-Control'], 'no-store')

    async def test_identical_metadata_requests_share_transport_and_known_id_skips_search(self):
        client = MediaDetailsClient(None, lambda: 'fixture')
        client.remember_identity({'media_type': 'movie', 'tmdb_id': 77, 'title': 'Film', 'year': '2020'})
        entered, finish = asyncio.Event(), asyncio.Event()
        async def transport(*args, **kwargs):
            entered.set()
            await finish.wait()
            return {'id': 77, 'title': 'Film', 'release_date': '2020-01-01', 'poster_path': '/poster.jpg', 'backdrop_path': '/backdrop.jpg'}
        client._get_uncached = AsyncMock(side_effect=transport)
        readers = [asyncio.create_task(client.details(media_type='movie', title='Film', year=2020)) for _ in range(4)]
        await entered.wait()
        await asyncio.sleep(0)
        finish.set()
        results = await asyncio.gather(*readers)
        client._get_uncached.assert_awaited_once()
        self.assertEqual(client._get_uncached.call_args.args[0], 'movie/77')
        self.assertTrue(all(result['tmdb_id'] == 77 for result in results))
        await client.details(media_type='movie', tmdb_id=77, title='Translated title')
        client._get_uncached.assert_awaited_once()
