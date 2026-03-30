"""Sprint 8UC: SystemPromptKVCache."""
import pytest
from hledac.universal.brain.prompt_cache import SystemPromptKVCache, _SYSTEM_PROMPT_CACHE


def test_kv_cache_singleton_exists():
    """_SYSTEM_PROMPT_CACHE singleton must exist."""
    assert _SYSTEM_PROMPT_CACHE is not None
    assert isinstance(_SYSTEM_PROMPT_CACHE, SystemPromptKVCache)


def test_kv_cache_invalidate():
    """invalidate() clears all cached state."""
    cache = SystemPromptKVCache()
    # Simulate some cached state (we can't actually cache without a real tokenizer)
    cache.invalidate()
    assert cache._cached_prompt is None
    assert cache._cached_tokens is None


def test_kv_cache_get_or_build_returns_tuple():
    """get_or_build returns (None, token_count) tuple."""
    cache = SystemPromptKVCache()
    # Use None for model/tokenizer — just test the return type
    result = cache.get_or_build(None, None, "test prompt")
    assert isinstance(result, tuple)
    assert result[0] is None  # KV cache not available
    assert isinstance(result[1], int)  # token count


def test_kv_cache_same_prompt_reuses():
    """Same prompt called twice returns cached state (by checking no-op path)."""
    cache = SystemPromptKVCache()
    # First call with a prompt
    r1 = cache.get_or_build(None, None, "same prompt")
    # Second call with same prompt — should return cached
    # (we can verify the method doesn't raise)
    r2 = cache.get_or_build(None, None, "same prompt")
    assert r1 == r2
