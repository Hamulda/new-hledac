"""
Archived: model_store_v2.py was merged into model_store.py.
This shim provides backward compatibility for any code importing from model_store_v2.

Unique v2 features (AES-GCM encryption, version headers, async API, MLX support)
were NOT migrated as v2 is not actively used in the codebase.

Canonical: hledac.universal.federated.model_store.ModelStore
Archived: This file was model_store_v2.py.bak.20260304_002337
"""

from hledac.universal.federated.model_store import ModelStore

__all__ = ["ModelStore"]
