"""``SpatialIndex`` — throwing stub.

Every method raises ``NotImplementedError("spatial: not implemented")``. This file exists
so that ``spatial_test.py`` imports a real class with the right shape — constructor,
methods, properties — and fails on an assertion or on this explicit error, never on
``ImportError`` or ``AttributeError``. The implementer's only job is to replace these
bodies until ``python -m pytest src/spatial`` is green; the method signatures and the
public re-export list in ``__init__.py`` are the contract and do not move.

No implementation logic lives here on purpose (Rule 4 — tests come first). See
``src/spatial/README.md`` for the invariants each method must satisfy once implemented,
especially the invalidation contract ADR-011 calls out as a silent-wrong-answer risk.
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, EngineProtocol

__all__ = ["SpatialIndex"]

_NOT_IMPLEMENTED = "spatial: not implemented"


class SpatialIndex:
    """BVH over scene objects, answering broad-phase proximity queries.

    See ``README.md`` in this directory for the full contract. Constructed once per
    engine and kept alive across operations — it is a maintained structure, not a
    per-call rebuild (ADR-011).
    """

    def __init__(self, engine: EngineProtocol) -> None:
        self._engine = engine  # retained only so the stub's signature is exact

    def rebuild(self) -> None:
        """Full rebuild from ``engine.list_objects()``."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def insert(self, object_id: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def update(self, object_id: str) -> None:
        """The object moved or changed shape; its bounds are re-read from the engine."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def remove(self, object_id: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def invalidate(self, object_id: str) -> None:
        """Mark stale without re-reading yet; the next query must not return stale bounds."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def bounds_of(self, object_id: str) -> AABB:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def nearby(self, object_id: str, margin: float = 0.0) -> tuple[str, ...]:
        """Ids whose bounds overlap ``object_id``'s bounds expanded by ``margin``,
        excluding ``object_id`` itself."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def pairs_overlapping(self, margin: float = 0.0) -> tuple[tuple[str, str], ...]:
        """Every unordered overlapping pair, each reported once, deterministically ordered."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def in_region(self, region: AABB) -> tuple[str, ...]:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    def neighbours_of(self, object_ids: Sequence[str], margin: float = 0.0) -> tuple[str, ...]:
        """The scoping primitive ADR-011 requires: the given objects plus their
        neighbours, for scoped checks at thousands of objects."""
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def size(self) -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED)

    @property
    def stale_count(self) -> int:
        raise NotImplementedError(_NOT_IMPLEMENTED)
