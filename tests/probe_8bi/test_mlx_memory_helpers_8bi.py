from hledac.universal.utils.mlx_memory import format_mlx_memory_snapshot, clear_mlx_cache, configure_mlx_limits

def test_memory_snapshot_fail_open():
    snap = format_mlx_memory_snapshot()
    assert isinstance(snap, dict)
    assert "available" in snap

def test_limits_fail_open():
    result = configure_mlx_limits(cache_limit_mb=512, memory_limit_mb=None)
    assert isinstance(result, dict)
    assert "success" in result

def test_clear_cache_fail_open():
    ok = clear_mlx_cache()
    assert isinstance(ok, bool)
