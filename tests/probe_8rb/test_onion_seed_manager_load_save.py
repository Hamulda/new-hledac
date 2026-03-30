"""Sprint 8RB — OnionSeedManager load/save persistence."""
import asyncio
import tempfile
from pathlib import Path

from hledac.universal.intelligence.onion_seed_manager import OnionSeedManager


async def test_onion_seed_manager_load_save():
    """add_seed → save() → new instance → load() → seed survives."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "seeds.json"

        # Create manager, add a custom seed, save
        mgr1 = OnionSeedManager(seeds_path=path)
        mgr1.add_seed("http://test1234567890abcd.onion/")
        assert "http://test1234567890abcd.onion/" in mgr1._seeds
        await mgr1.save()

        # New instance — load from disk
        mgr2 = OnionSeedManager(seeds_path=path)
        await mgr2.load()
        assert "http://test1234567890abcd.onion/" in mgr2._seeds, \
            "Seed did not survive save/load cycle"


if __name__ == "__main__":
    asyncio.run(test_onion_seed_manager_load_save())
    print("test_onion_seed_manager_load_save: PASS")
