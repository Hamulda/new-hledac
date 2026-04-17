# DEPRECATED — use brain.model_lifecycle
# COMPAT_BACKWARD surface (Sprint F181A): Do NOT use this as an import path for new code.
# Use brain.model_lifecycle directly.
#
# ROLE: COMPAT_BACKWARD — backward-compat re-export wrapper only.
# This module exists because some older imports reference it.
# It delegates 100% to brain.model_lifecycle.
# NO canonical state, NO production truth, NO new code should use this.
#
# Canonical owner: brain.model_lifecycle — holds all real implementation.
# This module: passive star-re-export of brain.model_lifecycle.
#
# SPRINT F186D: Authority Contract — this module is STRICTLY PASSIVE.
# - Zero canonical state (no _lifecycle_state, no model registry)
# - Zero production logic (only star-re-exports)
# - __deprecated__ = True prevents use as canonical import path
# - Any code treating this as a model authority is IN ERROR.
#
# Migration blocker: unknown external consumers still import from here.
# When all consumers migrated, this file should be deleted.
from brain.model_lifecycle import *  # noqa: F401, F403
__all__ = []
__deprecated__ = True  # prevent accidental star-imports
