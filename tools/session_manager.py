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
    """
    Manages HTTP sessions with cookies/credentials persistence in LMDB.

    AUTHORITY NOTE (Sprint 8UX):
        This module is the PERSISTED SESSION authority.
        It stores cookies and headers in LMDB, keyed by domain.
        It is SEPARATE from session_runtime.py (shared async HTTP surface).

        Split is intentional:
          - session_runtime.py: raw HTTP session pool, no credentials
          - SessionManager: credentialed session state, domain-scoped persistence

        FetchCoordinator._fetch_url() calls SessionManager.get_session()
        to inject cookies/headers into transport-layer fetch operations.

    OWNERSHIP BOUNDARY (F300K):
        - LMDB env is INJECTED via __init__ — SessionManager does NOT own it
        - ThreadPoolExecutor is OWNED locally, closed via close()
        - post-close: all methods guard against use-after-close

    CLOSE SEMANTICS (F300K):
        - close() is idempotent — safe to call multiple times
        - executor.shutdown(wait=False) — non-blocking, no event-loop stall
        - _cache is NOT cleared (by design — remains accessible for reads)
        - _closed flag guards all mutating operations post-close
    """

    def __init__(self, lmdb_env: lmdb.Environment):
        self._env = lmdb_env
        self._cache: Dict[str, Dict] = {}  # domain -> {cookies, headers, last_used}
        # S49-B: Thread pool executor for async LMDB operations
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
        # F300K: explicit closed state — guards post-close truthfulness
        self._closed: bool = False

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

    # F300K: Helper to check and guard closed state for read-only methods.
    # Returns cached data if available after close, else None.
    def _get_from_cache_after_close(self, domain: str) -> Optional[Dict]:
        if self._closed and domain in self._cache:
            return self._cache[domain]
        return None

    # S49-B: Async LMDB operations via executor
    async def get_session(self, domain: str) -> Optional[Dict]:
        """Vrátí uložené session pro domain."""
        # F300K: After close, return stale cached data (read-only, no LMDB write)
        if self._closed:
            cached = self._cache.get(domain)
            if cached:
                cached['last_used'] = time.time()
            return cached

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
        """Uloží session pro domain. F300K: no-op after close."""
        # F300K: Guard — mutate operations blocked after close
        if self._closed:
            logger.debug(f"[SESSION] save_session({domain}) — blocked, manager closed")
            return

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
        """Zahodí staré session, přiští fetch zkusí znovu přihlásit. F300K: no-op after close."""
        # F300K: Guard — mutate operations blocked after close
        if self._closed:
            logger.debug(f"[SESSION] rotate_credentials({domain}) — blocked, manager closed")
            return

        if domain in self._cache:
            del self._cache[domain]

        # S49-B: Async LMDB delete via executor
        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(self._executor, self._sync_delete, self._get_key(domain))
        except Exception:
            pass

    async def close(self) -> None:
        """
        F300K: Cleanup executor on shutdown.

        Idempotent — safe to call multiple times.
        Uses wait=False to avoid blocking the event loop.
        Mutating operations (save_session, rotate_credentials) are
        blocked after close. Read operations (get_session) continue
        to return stale cached data.
        """
        if self._closed:
            return
        self._closed = True
        # F300K: wait=False — non-blocking, no event-loop stall on M1 8GB UMA
        self._executor.shutdown(wait=False)
