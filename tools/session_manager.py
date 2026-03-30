"""
Session Manager – ukládá cookies a credentials, automaticky je injectuje do fetch.
Sprint 46: Access to Unreachable Data (Sessions + Paywall + OSINT + Darknet)
Sprint 48: Async LMDB operations via executor, orjson serialization
"""

import asyncio
import concurrent.futures
import json
import logging
from typing import Dict, Optional
import time

import lmdb

# S48-P8: Try orjson for faster serialization, fallback to json
try:
    import orjson
    USE_ORJSON = True
except ImportError:
    USE_ORJSON = False
    import json

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages HTTP sessions with cookies/credentials persistence in LMDB."""

    def __init__(self, lmdb_env: lmdb.Environment):
        self._env = lmdb_env
        self._cache: Dict[str, Dict] = {}  # domain -> {cookies, headers, last_used}
        # S49-B: Thread pool executor for async LMDB operations
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    def _get_key(self, domain: str) -> bytes:
        return f"session:{domain}".encode()

    # S48-P8: Fast serialization
    def _serialize(self, data: Dict) -> bytes:
        if USE_ORJSON:
            return orjson.dumps(data)
        return json.dumps(data).encode()

    def _deserialize(self, data: bytes) -> Dict:
        if USE_ORJSON:
            return orjson.loads(data)
        return json.loads(data.decode())

    # S49-B: Sync LMDB operations for executor
    def _sync_get(self, key: bytes) -> Optional[Dict]:
        with self._env.begin() as txn:
            data = txn.get(key)
            return self._deserialize(data) if data else None

    def _sync_put(self, key: bytes, data: bytes) -> None:
        with self._env.begin(write=True) as txn:
            txn.put(key, data)

    def _sync_delete(self, key: bytes) -> None:
        with self._env.begin(write=True) as txn:
            txn.delete(key)

    # S49-B: Async LMDB operations via executor
    async def get_session(self, domain: str) -> Optional[Dict]:
        """Vrátí uložené session pro domain."""
        # Check RAM cache first
        if domain in self._cache:
            self._cache[domain]['last_used'] = time.time()
            return self._cache[domain]

        # S49-B: Async LMDB read via executor - non-blocking
        try:
            loop = asyncio.get_running_loop()
            data = await loop.run_in_executor(self._executor, self._sync_get, self._get_key(domain))
            if data:
                self._cache[domain] = data
                return data
        except Exception:
            pass
        return None

    async def save_session(self, domain: str, cookies: Dict, headers: Dict = None):
        """Uloží session pro domain."""
        session = {
            'cookies': cookies,
            'headers': headers or {},
            'created': time.time(),
            'last_used': time.time()
        }
        self._cache[domain] = session

        # S49-B: Async LMDB write via executor
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                self._executor,
                self._sync_put,
                self._get_key(domain),
                self._serialize(session)
            )
        except Exception as e:
            logger.warning(f"[SESSION] Failed to save {domain}: {e}")

    async def rotate_credentials(self, domain: str):
        """Zahodí staré session, přiští fetch zkusí znovu přihlásit."""
        if domain in self._cache:
            del self._cache[domain]

        # S49-B: Async LMDB delete via executor
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._sync_delete, self._get_key(domain))
        except Exception:
            pass

    async def close(self) -> None:
        """S49-B: Cleanup executor on shutdown."""
        self._executor.shutdown(wait=True)
