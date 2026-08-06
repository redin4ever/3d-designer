"""``spatial`` — BVH over scene objects, broad-phase proximity queries (ADR-011).

Barrel: re-exports only. See ``README.md`` for the interface and its invariants.
"""

from .index import SpatialIndex

__all__ = ["SpatialIndex"]
