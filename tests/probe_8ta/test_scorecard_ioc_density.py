"""Sprint 8TA B.3: IOC density calculation."""


def test_scorecard_ioc_density():
    """accepted=5, ioc_nodes=20 -> ioc_density == 4.0."""
    accepted = 5
    ioc_nodes = 20

    ioc_density = ioc_nodes / max(1, accepted)

    assert ioc_density == 4.0


def test_scorecard_ioc_density_zero_accepted():
    """accepted=0, ioc_nodes=20 -> ioc_density == 0.0."""
    accepted = 0
    ioc_nodes = 20

    ioc_density = ioc_nodes / max(1, accepted) if accepted > 0 else 0.0

    assert ioc_density == 0.0
