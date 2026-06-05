"""CacheManager — Python port of managers/cacheManager.js.

IndexedDB-backed asset cache (models / animations), driven from Python by bridging
the IndexedDB request events to asyncio Futures.
"""

import asyncio

from js import window, indexedDB

from .jsutil import proxy

DB_NAME = "VRM_Assets_Cache"
DB_VERSION = 1
STORES = {"models": "models", "animations": "animations"}


def _future():
    return asyncio.get_event_loop().create_future()


class CacheManager:
    def __init__(self):
        self.db = None

    async def open_db(self):
        if self.db:
            return self.db
        fut = _future()
        request = indexedDB.open(DB_NAME, DB_VERSION)

        def on_error(event=None):
            if not fut.done():
                fut.set_exception(RuntimeError("Error opening database"))
        request.onerror = proxy(on_error)

        def on_success(event):
            self.db = event.target.result
            if not fut.done():
                fut.set_result(self.db)
        request.onsuccess = proxy(on_success)

        def on_upgrade(event):
            db = event.target.result
            if not db.objectStoreNames.contains(STORES["models"]):
                db.createObjectStore(STORES["models"])
            if not db.objectStoreNames.contains(STORES["animations"]):
                db.createObjectStore(STORES["animations"])
        request.onupgradeneeded = proxy(on_upgrade)

        return await fut

    async def _request(self, store_name, mode, op):
        db = await self.open_db()
        fut = _future()
        transaction = db.transaction([store_name], mode)
        store = transaction.objectStore(store_name)
        request = op(store)

        def on_success(event=None):
            if not fut.done():
                fut.set_result(request.result)
        request.onsuccess = proxy(on_success)

        def on_error(event=None):
            if not fut.done():
                fut.set_exception(RuntimeError(str(request.error)))
        request.onerror = proxy(on_error)

        return await fut

    async def get_cached(self, store_name, key):
        try:
            return await self._request(store_name, "readonly", lambda s: s.get(key))
        except Exception as error:  # noqa: BLE001
            print(f"CacheManager: getCached failed {error}")
            return None

    async def set_cached(self, store_name, key, data):
        try:
            return await self._request(store_name, "readwrite", lambda s: s.put(data, key))
        except Exception as error:  # noqa: BLE001
            print(f"CacheManager: setCached failed {error}")

    async def delete_cached(self, store_name, key):
        try:
            return await self._request(store_name, "readwrite", lambda s: s.delete(key))
        except Exception as error:  # noqa: BLE001
            print(f"CacheManager: deleteCached failed {error}")

    async def list_keys(self, store_name):
        try:
            return await self._request(store_name, "readonly", lambda s: s.getAllKeys())
        except Exception as error:  # noqa: BLE001
            print(f"CacheManager: listKeys failed {error}")
            return []

    async def get_all(self, store_name):
        try:
            return await self._request(store_name, "readonly", lambda s: s.getAll())
        except Exception as error:  # noqa: BLE001
            print(f"CacheManager: getAll failed {error}")
            return []

    async def clear_cache(self):
        try:
            db = await self.open_db()
            transaction = db.transaction([STORES["models"], STORES["animations"]], "readwrite")
            transaction.objectStore(STORES["models"]).clear()
            transaction.objectStore(STORES["animations"]).clear()
            print("CacheManager: Cache cleared")
        except Exception as error:  # noqa: BLE001
            print(f"CacheManager: Failed to clear cache {error}")

    # camelCase aliases for parity
    getCached = get_cached
    setCached = set_cached
    deleteCached = delete_cached
    listKeys = list_keys
    getAll = get_all
    clearCache = clear_cache


# Singleton, mirroring the JS `export const cacheManager`
cache_manager = CacheManager()
