"""
Dynamické uvolňování modelů s LRU cache a ochranou proti thrashingu.
"""

import asyncio
import hashlib
import logging
import os
import threading
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# MLX import s fallback
try:
    import mlx.core as mx
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    mx = None

# ANE compilation tracking
_ane_lock = threading.Lock()
_ane_compile_counter = 0
ANE_COMPILE_LIMIT = 119  # Maximum ANE compilations before fallback

# Cache directory for MPSGraph packages
_CACHE_DIR = Path(__file__).parent.parent / "cache" / "mps_cache"


def _get_cache_dir() -> Path:
    """Get or create MPS cache directory."""
    global _CACHE_DIR
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.warning(f"Failed to create MPS cache dir: {e}")
    return _CACHE_DIR


def _can_compile_ane() -> bool:
    """
    Check if ANE compilation is still available (under limit).

    Returns:
        True if under the 119 compilation limit
    """
    global _ane_compile_counter
    with _ane_lock:
        return _ane_compile_counter < ANE_COMPILE_LIMIT


def _increment_compile_counter() -> bool:
    """
    Increment the ANE compile counter.

    Returns:
        True if increment succeeded, False if limit reached
    """
    global _ane_compile_counter
    with _ane_lock:
        if _ane_compile_counter >= ANE_COMPILE_LIMIT:
            return False
        _ane_compile_counter += 1
        return True


def _load_or_compile_mps(
    cache_key: str,
    build_fn: Callable[[], Any]
) -> Optional[Any]:
    """
    Load or compile MPSGraphPackage with persistent caching.

    Args:
        cache_key: Unique key for this compiled model
        build_fn: Function to build/compile the MPS graph

    Returns:
        Compiled MPSGraphPackage or None
    """
    cache_dir = _get_cache_dir()
    cache_path = cache_dir / f"{cache_key}.mpsgraph"

    # Try to load from cache
    if cache_path.exists():
        try:
            # For now, just return None and trigger rebuild
            # Full implementation would load compiled package
            logger.debug(f"MPS cache hit: {cache_key}")
            return None
        except Exception as e:
            logger.warning(f"Failed to load MPS cache: {e}")

    # Check compile limit
    if not _can_compile_ane():
        logger.warning("ANE compile limit reached, using fallback")
        return None

    # Compile
    if not _increment_compile_counter():
        return None

    try:
        result = build_fn()

        # Save to cache (if result supports serialization)
        try:
            # Simplified: just mark cache as valid
            cache_path.touch()
        except Exception as e:
            logger.debug(f"Failed to save MPS cache: {e}")

        logger.info(f"Compiled MPS graph: {cache_key} ({_ane_compile_counter}/{ANE_COMPILE_LIMIT})")
        return result

    except Exception as e:
        logger.error(f"MPS compilation failed: {e}")
        return None


def _load_coreml_model(
    name: str,
    mlx_model: Any,
    sample_inputs: Any
) -> Optional[Any]:
    """
    Load CoreML model with hash-based caching from path+mtime.

    Args:
        name: Model name/identifier
        mlx_model: MLX model to convert
        sample_inputs: Sample inputs for tracing

    Returns:
        CoreML model or None
    """
    # Check for coremltools
    try:
        import coremltools as ct
    except ImportError:
        logger.debug("coremltools not available")
        return None

    # Build cache key from path + mtime
    cache_dir = _get_cache_dir() / "coreml"
    cache_dir.mkdir(parents=True, exist_ok=True)

    model_path = Path(name)
    cache_key_parts = [str(model_path)]

    # Add mtime if path exists
    if model_path.exists():
        cache_key_parts.append(str(model_path.stat().st_mtime))
    elif hasattr(mlx_model, 'parameters'):
        # Use parameter hash as fallback
        try:
            param_str = str(sorted(mlx_model.parameters().items()))
            cache_key_parts.append(hashlib.md5(param_str.encode()).hexdigest()[:8])
        except Exception:
            pass

    cache_key = hashlib.sha256("".join(cache_key_parts).encode()).hexdigest()[:16]
    cache_path = cache_dir / f"{cache_key}.mlmodel"

    # Try loading cached model
    if cache_path.exists():
        try:
            model = ct.models.MLModel(str(cache_path))
            logger.debug(f"CoreML cache hit: {name}")
            return model
        except Exception as e:
            logger.warning(f"Failed to load cached CoreML model: {e}")

    # Compile new model
    if not _can_compile_ane():
        logger.warning("ANE compile limit reached for CoreML")
        return None

    if not _increment_compile_counter():
        return None

    try:
        # Convert MLX to CoreML (simplified)
        # Full implementation would use coremltools.convert
        logger.info(f"Compiling CoreML model: {name} ({_ane_compile_counter}/{ANE_COMPILE_LIMIT})")

        # Save to cache
        # Note: Actual conversion would save to cache_path
        return None

    except Exception as e:
        logger.error(f"CoreML conversion failed: {e}")
        return None


class DynamicModelManager:
    """
    Dynamický správce modelů s LRU cache a ochranou proti thrashingu.

    Features:
        - LRU cache s max_loaded_models limitom
        - Ochrana proti thrashingu (min_reload_interval)
        - Idle timeout pro automatické uvolnění
        - Logování všech operací
    """

    def __init__(
        self,
        base_manager,
        idle_timeout: float = 180.0,
        min_reload_interval: float = 60.0,
        max_loaded_models: int = 2
    ):
        """
        Initialize DynamicModelManager.

        Args:
            base_manager: Základní ModelManager s load/release metodami
            idle_timeout: Sekundy nečinnosti před uvolněním modelu
            min_reload_interval: Minimální sekundy mezi unload a reload (ochrana proti thrashingu)
            max_loaded_models: Maximální počet současně načtených modelů
        """
        self.base_manager = base_manager
        self.idle_timeout = idle_timeout
        self.min_reload_interval = min_reload_interval
        self.max_loaded_models = max_loaded_models

        # LRU cache: model_name -> last_access_time
        self._lru: OrderedDict[str, float] = OrderedDict()
        self.last_unloaded: Dict[str, float] = {}

        # Active context holders
        self._active_contexts: Dict[str, Any] = {}

        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        logger.info(
            f"DynamicModelManager initialized: max_loaded={max_loaded_models}, "
            f"idle_timeout={idle_timeout}s, min_reload={min_reload_interval}s"
        )

    async def start(self) -> None:
        """Spustí background cleanup loop."""
        if self._running:
            return
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("DynamicModelManager cleanup loop started")

    async def stop(self) -> None:
        """Zastaví background cleanup loop."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("DynamicModelManager cleanup loop stopped")

    async def acquire(self, model_name: str) -> Any:
        """
        Získá model z cache nebo ho načte.

        Args:
            model_name: Název modelu k načtení

        Returns:
            Model instance
        """
        now = time.time()

        # Thrashing protection: pokud byl model nedávno uvolněn, počkáme
        last_unload = self.last_unloaded.get(model_name, 0)
        if now - last_unload < self.min_reload_interval:
            wait_time = self.min_reload_interval - (now - last_unload)
            logger.debug(f"Thrashing protection: waiting {wait_time:.1f}s before reload {model_name}")
            await asyncio.sleep(wait_time)

        # Pokud je model v LRU cache, použijeme ho
        if model_name in self._lru:
            self._lru.move_to_end(model_name)
            self._lru[model_name] = time.time()
            logger.debug(f"Model {model_name} found in LRU cache")
            return await self.base_manager.acquire_model(model_name)

        # LRU eviction: pokud je cache plný, uvolníme nejstarší model
        if len(self._lru) >= self.max_loaded_models:
            oldest_name, _ = self._lru.popitem(last=False)
            logger.info(f"LRU eviction: unloading {oldest_name}")
            await self.base_manager.release_model(oldest_name)
            self.last_unloaded[oldest_name] = time.time()

            # Clear MLX cache po uvolnění
            if MLX_AVAILABLE:
                try:
                    mx.metal.clear_cache()
                except Exception as e:
                    logger.debug(f"MLX cache clear failed: {e}")

        # Přidáme do LRU a načteme model
        self._lru[model_name] = time.time()
        logger.info(f"Loading model {model_name}")

        return await self.base_manager.acquire_model(model_name)

    @asynccontextmanager
    async def acquire_context(self, model_name: str):
        """
        Context manager pro bezpečné použití modelu.

        Usage:
            async with dynamic_manager.acquire_context("hermes") as model:
                result = await model.generate(...)
        """
        model = await self.acquire(model_name)
        try:
            yield model
        finally:
            # Update LRU timestamp
            if model_name in self._lru:
                self._lru[model_name] = time.time()

    async def release(self, model_name: str) -> None:
        """
        Uvolní model z aktivního použití.

        Args:
            model_name: Název modelu k uvolnění
        """
        if model_name in self._lru:
            # Jen odstraníme z LRU, model zůstává v paměti
            del self._lru[model_name]
            logger.debug(f"Model {model_name} removed from LRU (still in memory)")

        await self.base_manager.release_model(model_name)

    async def force_unload(self, model_name: str) -> None:
        """
        Vynutí okamžité uvolnění modelu.

        Args:
            model_name: Název modelu k uvolnění
        """
        if model_name in self._lru:
            del self._lru[model_name]

        await self.base_manager.release_model(model_name)
        self.last_unloaded[model_name] = time.time()

        if MLX_AVAILABLE:
            try:
                mx.metal.clear_cache()
            except Exception as e:
                logger.debug(f"MLX cache clear failed: {e}")

        logger.info(f"Force unload: {model_name}")

    async def _cleanup_loop(self) -> None:
        """Background loop pro kontrolu idle timeoutu."""
        while self._running:
            try:
                await asyncio.sleep(60)  # Kontrolu každou minutu
                await self._check_idle_timeout()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Cleanup loop error: {e}")

    async def _check_idle_timeout(self) -> None:
        """Zkontroluje modely a uvolní ty s překročeným idle timeoutem."""
        now = time.time()
        to_remove = []

        # LRU je seřazeno od nejstaršího
        for model_name, last_access in self._lru.items():
            idle_time = now - last_access
            if idle_time > self.idle_timeout:
                to_remove.append(model_name)
            else:
                # LRU je seřazené, takže můžeme přestat po prvním ne-starém
                break

        for model_name in to_remove:
            idle_time = now - self._lru[model_name]
            del self._lru[model_name]
            await self.base_manager.release_model(model_name)
            self.last_unloaded[model_name] = now

            logger.info(f"Idle timeout: unloaded {model_name} after {idle_time:.1f}s")

        if to_remove and MLX_AVAILABLE:
            try:
                mx.metal.clear_cache()
            except Exception as e:
                logger.debug(f"MLX cache clear failed: {e}")

    def get_loaded_models(self) -> list:
        """Vrátí seznam aktuálně načtených modelů."""
        return list(self._lru.keys())

    def is_loaded(self, model_name: str) -> bool:
        """Zkontroluje, zda je model načten."""
        return model_name in self._lru

    def get_stats(self) -> Dict[str, Any]:
        """Vrátí statistiky o cache."""
        return {
            "loaded_models": len(self._lru),
            "max_loaded": self.max_loaded_models,
            "models": list(self._lru.keys()),
            "last_unloaded": list(self.last_unloaded.keys()),
            "idle_timeout": self.idle_timeout,
            "min_reload_interval": self.min_reload_interval
        }
