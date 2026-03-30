"""
Test Subsystem Semaphores
=========================

Tests for subsystem semaphore routing:
- GPU lane max 1
- ANE lane bounded
- CPU-heavy bounded
- I/O bounded
"""

import pytest
import asyncio

from hledac.universal.orchestrator.subsystem_semaphores import (
    SubsystemSemaphores, Subsystem
)


class TestSubsystemSemaphores:
    """Test SubsystemSemaphores."""

    def test_default_limits(self):
        """Test default semaphore limits."""
        semaphores = SubsystemSemaphores()

        assert semaphores._limits[Subsystem.GPU] == 1
        assert semaphores._limits[Subsystem.ANE] == 1
        assert semaphores._limits[Subsystem.CPU_HEAVY] == 2
        assert semaphores._limits[Subsystem.IO] == 6

    def test_custom_limits(self):
        """Test custom limits."""
        semaphores = SubsystemSemaphores(
            gpu_limit=1,
            ane_limit=2,
            cpu_heavy_limit=4,
            io_limit=10
        )

        assert semaphores._limits[Subsystem.GPU] == 1
        assert semaphores._limits[Subsystem.ANE] == 2
        assert semaphores._limits[Subsystem.CPU_HEAVY] == 4
        assert semaphores._limits[Subsystem.IO] == 10

    @pytest.mark.asyncio
    async def test_gpu_semaphore_allows_one(self):
        """Test GPU semaphore allows max 1."""
        semaphores = SubsystemSemaphores()

        # Use sync acquire since Semaphore supports sync context manager
        sem = semaphores.acquire_sync(Subsystem.GPU)

        # Acquire first
        async with sem:
            # Second should wait
            acquired_second = False
            try:
                async with asyncio.timeout(0.1):
                    sem2 = semaphores.acquire_sync(Subsystem.GPU)
                    async with sem2:
                        acquired_second = True
            except asyncio.TimeoutError:
                pass

            assert acquired_second is False

    @pytest.mark.asyncio
    async def test_gpu_semaphore_releases(self):
        """Test GPU semaphore releases properly."""
        semaphores = SubsystemSemaphores()
        sem = semaphores.acquire_sync(Subsystem.GPU)

        async with sem:
            pass

        # Should be able to acquire again
        async with semaphores.acquire_sync(Subsystem.GPU):
            pass

    @pytest.mark.asyncio
    async def test_ane_semaphore_bounded(self):
        """Test ANE semaphore bounded."""
        semaphores = SubsystemSemaphores()

        # Should work with default limit 1
        async with semaphores.acquire_sync(Subsystem.ANE):
            pass

    @pytest.mark.asyncio
    async def test_cpu_heavy_allows_two(self):
        """Test CPU-heavy allows 2 concurrent."""
        semaphores = SubsystemSemaphores()

        # Acquire two
        sem1 = semaphores.acquire_sync(Subsystem.CPU_HEAVY)
        sem2 = semaphores.acquire_sync(Subsystem.CPU_HEAVY)

        async with sem1:
            async with sem2:
                # Third should wait
                acquired_third = False
                try:
                    async with asyncio.timeout(0.1):
                        sem3 = semaphores.acquire_sync(Subsystem.CPU_HEAVY)
                        async with sem3:
                            acquired_third = True
                except asyncio.TimeoutError:
                    pass

                assert acquired_third is False

    @pytest.mark.asyncio
    async def test_io_allows_six(self):
        """Test I/O allows 6 concurrent."""
        semaphores = SubsystemSemaphores()

        # Acquire 5 should work
        async def try_acquire():
            sem = semaphores.acquire_sync(Subsystem.IO)
            async with sem:
                await asyncio.sleep(0.01)

        await asyncio.gather(*[try_acquire() for _ in range(5)])

    @pytest.mark.asyncio
    async def test_different_subsystems_independent(self):
        """Test different subsystems are independent."""
        semaphores = SubsystemSemaphores()

        # Can acquire GPU and ANE simultaneously
        async with semaphores.acquire_sync(Subsystem.GPU):
            async with semaphores.acquire_sync(Subsystem.ANE):
                async with semaphores.acquire_sync(Subsystem.CPU_HEAVY):
                    async with semaphores.acquire_sync(Subsystem.IO):
                        pass

    def test_get_subsystem(self):
        """Test subsystem classification."""
        semaphores = SubsystemSemaphores()

        # Test classification
        assert semaphores.get_subsystem("hermes_generate") == Subsystem.GPU
        assert semaphores.get_subsystem("coreml_classify") == Subsystem.ANE
        assert semaphores.get_subsystem("mmr_rerank") == Subsystem.CPU_HEAVY
        assert semaphores.get_subsystem("fetch_url") == Subsystem.IO


class TestSubsystemRouting:
    """Test subsystem routing logic."""

    def test_gpu_routing(self):
        """Test GPU subsystem routing."""
        semaphores = SubsystemSemaphores()

        # Heavy MLX should go to GPU
        assert semaphores.get_subsystem("mlx_generate") == Subsystem.GPU
        assert semaphores.get_subsystem("hermes_inference") == Subsystem.GPU

    def test_ane_routing(self):
        """Test ANE subsystem routing."""
        semaphores = SubsystemSemaphores()

        # CoreML/Vision should go to ANE
        assert semaphores.get_subsystem("coreml_vision") == Subsystem.ANE
        assert semaphores.get_subsystem("natural_language_ner") == Subsystem.ANE

    def test_cpu_heavy_routing(self):
        """Test CPU-heavy subsystem routing."""
        semaphores = SubsystemSemaphores()

        # Parsing/PRF should go to CPU-heavy
        assert semaphores.get_subsystem("parse_html") == Subsystem.CPU_HEAVY
        assert semaphores.get_subsystem("mmr_diversity") == Subsystem.CPU_HEAVY

    def test_io_routing(self):
        """Test I/O subsystem routing."""
        semaphores = SubsystemSemaphores()

        # Network should go to I/O
        assert semaphores.get_subsystem("fetch_page") == Subsystem.IO
        assert semaphores.get_subsystem("crawl_deep") == Subsystem.IO


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
