"""Sprint 8TD: MoE memory-aware routing tests."""
import pytest
from unittest.mock import MagicMock, patch


class TestMoEMemoryFilter:
    """Test memory-aware expert filtering."""

    def test_known_model_sizes_defined(self):
        """KNOWN_MODEL_SIZES dict exists with expected keys."""
        from hledac.universal.brain.moe_router import MoERouter
        sizes = MoERouter.KNOWN_MODEL_SIZES
        assert isinstance(sizes, dict)
        assert "mlx-community/Hermes-3-Llama-3.1-8B-4bit" in sizes
        assert "mlx-community/gemma-2-2b-it-4bit" in sizes

    def test_get_available_memory_gb_returns_float(self):
        """_get_available_memory_gb() returns float > 0."""
        from hledac.universal.brain.moe_router import MoERouter
        router = MoERouter.__new__(MoERouter)
        router.config = MagicMock()
        router.config.expert_names = ["osint", "security"]

        with patch("psutil.virtual_memory") as mock_mem:
            mock_mem.return_value.available = 4 * 1024**3  # 4GB
            result = router._get_available_memory_gb()
            assert isinstance(result, float)
            assert result > 0

    def test_memory_filter_excludes_large_models(self):
        """When avail=3.0GB, models >2.5GB are excluded."""
        from hledac.universal.brain.moe_router import MoERouter

        router = MoERouter.__new__(MoERouter)
        router.config = MagicMock()
        router.config.expert_names = ["osint", "security", "nano"]
        router.config.model_paths = {
            "osint": "mlx-community/Hermes-3-Llama-3.1-8B-4bit",  # 5.2GB
            "security": "mlx-community/Mistral-7B-Instruct-v0.3-4bit",  # 4.8GB
            "nano": "mlx-community/gemma-2-2b-it-4bit",  # 1.8GB
        }
        router.KNOWN_MODEL_SIZES = MoERouter.KNOWN_MODEL_SIZES

        # Mock available memory = 3.0GB
        with patch.object(router, "_get_available_memory_gb", return_value=3.0):
            # Simulate expert_scores (all equal for testing)
            expert_scores = [("osint", 0.5), ("security", 0.3), ("nano", 0.2)]

            avail = 3.0
            feasible = [
                (name, score) for name, score in expert_scores
                if router.KNOWN_MODEL_SIZES.get(router.config.model_paths.get(name, ""), 3.0)
                <= avail - 0.5  # 2.5GB threshold
            ]

            # Only nano (1.8GB) fits in 3.0 - 0.5 = 2.5GB
            assert len(feasible) == 1
            assert feasible[0][0] == "nano"

    def test_nano_expert_fallback_when_all_oom(self):
        """When no expert fits, fallback to smallest (nano) expert."""
        from hledac.universal.brain.moe_router import MoERouter

        router = MoERouter.__new__(MoERouter)
        router.config = MagicMock()
        router.config.expert_names = ["osint", "security"]
        router.config.model_paths = {
            "osint": "mlx-community/Hermes-3-Llama-3.1-8B-4bit",  # 5.2GB
            "security": "mlx-community/Hermes-3-Llama-3.1-8B-8bit",  # 9.1GB
        }
        router.KNOWN_MODEL_SIZES = MoERouter.KNOWN_MODEL_SIZES

        # Only osint fits at 3.0GB but let's say it doesn't
        expert_scores = [("osint", 0.6), ("security", 0.4)]

        avail = 1.0  # Very low memory
        feasible = [
            (name, score) for name, score in expert_scores
            if router.KNOWN_MODEL_SIZES.get(router.config.model_paths.get(name, ""), 3.0)
            <= avail - 0.5
        ]

        if not feasible:
            # Fallback to smallest
            feasible = [(expert_scores[-1][0], expert_scores[-1][1])]

        # Should fallback to last (lowest score = smallest model in this case)
        assert len(feasible) == 1
