"""Bounded, source-scoped stale-while-revalidate cache for private HA data."""
from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import random
import time
import uuid

from homeassistant.helpers.storage import Store

from .media_details import MediaDetailsError

FRESH_SECONDS = 15
MAX_STALE_SECONDS = 24 * 3600
MAX_DISK_BYTES = 16 * 1024 * 1024


def source_scope(sources):
    # Credentials affect cache isolation, but never appear in persisted data or logs.
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


class SnapshotCache:
    def __init__(self, hass, fetch, store=None):
        self.hass, self.fetch = hass, fetch
        self.store = store
        if store is None and hasattr(hass, "config"):
            self.store = Store(hass, 1, "mediarr.library_cache", private=True)
        self.lock = asyncio.Lock()
        self.scope = None
        self.data = None
        self.public_scope = uuid.uuid4().hex
        self.checked = 0.0
        self.flight = None
        self.history = {}
        self.retry_at = 0.0
        self.failures = 0
        self.last_error = False
        self.stats = {"hits": 0, "refreshes": 0, "coalesced": 0}

    async def read(self, sources, force=False, snapshot_id=None):
        scope = source_scope(sources)
        async with self.lock:
            if self.scope != scope:
                self.scope, self.data, self.checked = scope, None, 0.0
                self.public_scope = uuid.uuid4().hex
                self.history.clear()
                self.flight = None
                self.retry_at, self.failures = 0.0, 0
                self.last_error = False
                if self.store:
                    try:
                        saved = await self.store.async_load()
                        age = time.time() - saved["checked"] if isinstance(saved, dict) else -1
                        if saved.get("scope") == scope and 0 <= age < MAX_STALE_SECONDS and isinstance(saved.get("data", {}).get("groups"), dict):
                            self.data = saved["data"]
                            self.checked = saved["checked"]
                            self.public_scope = saved.get("public_scope") or self.public_scope
                            self.history[self.data["revision"]] = (self.checked, self.data)
                    except (Exception,):
                        # A cache failure must not prevent a fresh, authenticated source read.
                        self.data = None
            if snapshot_id:
                record = self.history.get(snapshot_id)
                if not record or time.time() - record[0] > MAX_STALE_SECONDS:
                    raise MediaDetailsError("library_snapshot_expired", "Library snapshot expired; retry the first page.")
                return self._public(record[1], record[0])
            age = time.time() - self.checked
            if self.data is not None and 0 <= age < FRESH_SECONDS and self.data.get("complete") and not force:
                self.stats["hits"] += 1
                return self._public(self.data, self.checked)
            if self.data is not None and (age < 0 or age >= MAX_STALE_SECONDS):
                self.data = None
            if self.flight is None or self.flight.done():
                if not force and self.data is not None and time.monotonic() < self.retry_at:
                    return self._public(self.data, self.checked)
                create_task = getattr(self.hass, "async_create_background_task", None)
                self.flight = (create_task(self._refresh(sources, scope, force), "mediarr-library-cache")
                               if create_task else asyncio.create_task(self._refresh(sources, scope, force), name="mediarr-library-cache"))
                self.flight.add_done_callback(self._consume)
            else:
                self.stats["coalesced"] += 1
            flight = self.flight
            if self.data is not None and not force:
                return self._public(self.data, self.checked)
        # Do not hold the state lock during network I/O; one task serves all callers.
        return await asyncio.shield(flight)

    @staticmethod
    def _consume(task):
        if not task.cancelled():
            task.exception()  # Background errors must never become unhandled task warnings.

    def _public(self, data, checked):
        age = max(0, int(time.time() - checked))
        result = {**data, "cache": {"version": 1, "state": "fresh" if age < FRESH_SECONDS and data.get("complete") and not self.last_error else "stale", "age_seconds": age, "scope_id": self.public_scope}}
        if self.last_error:
            result = {**result, "complete": False, "errors": [{"code": "library_unavailable"}]}
        return result

    def _backoff(self):
        self.failures += 1
        self.retry_at = time.monotonic() + min(300, 15 * 2 ** min(self.failures - 1, 5)) * random.uniform(0.8, 1.2)

    def replace_groups(self, groups):
        if self.data is None:
            return
        self.data = {**self.data, "groups": groups, "revision": uuid.uuid4().hex}
        self.history[self.data["revision"]] = (self.checked, self.data)
        while len(self.history) > 4:
            del self.history[next(iter(self.history))]
        self._save()
        bus = getattr(self.hass, "bus", None)
        if bus:
            bus.async_fire("mediarr_library_updated", {"revision": self.data["revision"]})

    def _save(self):
        if not self.store or self.data is None:
            return
        payload = {"scope": self.scope, "public_scope": self.public_scope, "checked": self.checked, "data": deepcopy(self.data)}
        try:
            if len(json.dumps(payload).encode()) <= MAX_DISK_BYTES:
                self.store.async_delay_save(lambda: payload, 3)
        except Exception:
            # Optional cache storage must never turn a successful read into failure.
            pass

    async def _refresh(self, sources, scope, force):
        self.stats["refreshes"] += 1
        previous = self.data
        try:
            data = await self.fetch(sources, previous, force)
        except Exception:
            if self.scope == scope:
                self.last_error = True
                self._backoff()
                bus = getattr(self.hass, "bus", None)
                if bus and self.data:
                    bus.async_fire("mediarr_library_updated", {"revision": self.data["revision"]})
            raise
        if self.scope != scope:
            raise MediaDetailsError("library_config_changed", "Library configuration changed; retry.")
        def semantic(value):
            if isinstance(value, dict):
                return {key: semantic(item) for key, item in value.items() if key != "_source_checked_at"}
            if isinstance(value, list):
                return [semantic(item) for item in value]
            return value
        changed = previous is None or any(semantic(data.get(key)) != semantic(previous.get(key)) for key in ("groups", "errors", "complete"))
        data["revision"] = uuid.uuid4().hex if changed else previous["revision"]
        self.data, self.checked = data, time.time()
        self.last_error = False
        self.history[data["revision"]] = (self.checked, data)
        while len(self.history) > 4:
            del self.history[next(iter(self.history))]
        if data.get("complete"):
            self.failures, self.retry_at = 0, 0.0
        else:
            self._backoff()
        self._save()
        bus = getattr(self.hass, "bus", None)
        if bus:
            bus.async_fire("mediarr_library_updated", {"revision": data["revision"]})
        return self._public(data, self.checked)
