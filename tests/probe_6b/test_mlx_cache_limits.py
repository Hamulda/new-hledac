"""
Sprint 6B: MLX Cache Limits Tests
=================================

Tests for MLX buffer initialization:
- 2.5GB cache limit set
- 2.5GB wired limit set
- init_mlx_buffers() called at module load
"""

import unittest


class TestMLXCacheLimits(unittest.TestCase):
    """Tests for MLX 2.5GB cache/wired limits."""

    def test_init_mlx_buffers_exists(self):
        """Test init_mlx_buffers function exists."""
        from hledac.universal.utils import mlx_cache
        self.assertTrue(hasattr(mlx_cache, 'init_mlx_buffers'))
        self.assertTrue(callable(mlx_cache.init_mlx_buffers))

    def test_mlx_constants_defined(self):
        """Test MLX cache/wired limit constants are 2.5GB."""
        from hledac.universal.utils import mlx_cache

        expected = 2684354560  # 2.5GB
        self.assertEqual(mlx_cache._MLX_CACHE_LIMIT, expected)
        self.assertEqual(mlx_cache._MLX_WIRED_LIMIT, expected)

    def test_init_mlx_buffers_is_called(self):
        """Test init_mlx_buffers() is called at module load."""
        import hledac.universal.utils.mlx_cache as mlx_cache_module

        source_file = mlx_cache_module.__file__
        with open(source_file, 'r') as f:
            content = f.read()

        # Should have "init_mlx_buffers()" call at module level
        # The call appears after the function definition, before the decorator
        self.assertIn("init_mlx_buffers()", content)
        # Verify it's called as a statement (not inside a function/class)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'init_mlx_buffers()' in line:
                # Found at module level - not indented inside a function
                stripped = line.rstrip()
                if stripped and not stripped.startswith('#'):
                    # Should be at column 0 or only whitespace before it
                    self.assertEqual(len(line) - len(line.lstrip()), 0,
                                    f"init_mlx_buffers() found indented at line {i+1}")
                break


class TestMLXCacheInitIntegration(unittest.TestCase):
    """Integration tests for MLX cache init."""

    def test_mlx_initialized_flag_exists(self):
        """Test _MLX_INITIALIZED flag exists."""
        from hledac.universal.utils import mlx_cache
        self.assertTrue(hasattr(mlx_cache, '_MLX_INITIALIZED'))


if __name__ == "__main__":
    unittest.main()
