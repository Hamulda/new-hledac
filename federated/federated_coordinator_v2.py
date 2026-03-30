"""
Archived: federated_coordinator_v2.py was archived.
This shim provides backward compatibility for any code importing FederatedCoordinatorV2.

Unique v2 features (risk-level routing, NymPolicy integration) were NOT migrated
as v2 is not actively used in the codebase.

Canonical: Use hledac.universal.transport with TorTransport/NymTransport
            + hledac.universal.federated.model_store.ModelStore
Archived: This file was federated_coordinator_v2.py.bak.20260304_002416
"""

import warnings
warnings.warn(
    "FederatedCoordinatorV2 is deprecated. Use transport-based approach instead.",
    DeprecationWarning,
    stacklevel=2
)


class FederatedCoordinatorV2:
    """Deprecated: This class is archived. Use transport + model_store instead."""
    pass


__all__ = ["FederatedCoordinatorV2"]
