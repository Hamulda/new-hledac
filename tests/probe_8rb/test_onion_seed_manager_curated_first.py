"""Sprint 8RB — OnionSeedManager curated seeds first in get_seeds()."""
import asyncio
from pathlib import Path
from hledac.universal.intelligence.onion_seed_manager import OnionSeedManager


def test_onion_seed_manager_curated_first():
    """get_seeds() → curated seeds appear at the beginning of the returned list."""
    mgr = OnionSeedManager()
    seeds = mgr.get_seeds(limit=10)

    # First seeds must be from CURATED_SEEDS
    curated_in_result = [s for s in seeds if s in OnionSeedManager.CURATED_SEEDS]
    assert len(curated_in_result) > 0, "No curated seeds in result"

    # All curated seeds should be first (before any non-curated)
    curated_set = set(OnionSeedManager.CURATED_SEEDS)
    non_curated_seen = False
    for s in seeds:
        if s not in curated_set:
            non_curated_seen = True
        # If we see a curated seed AFTER a non-curated seed, invariant is broken
        if s in curated_set and non_curated_seen:
            raise AssertionError(f"Curated seed {s} appeared after non-curated seed!")


if __name__ == "__main__":
    test_onion_seed_manager_curated_first()
    print("test_onion_seed_manager_curated_first: PASS")
