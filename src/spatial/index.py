"""``SpatialIndex`` — BVH over scene objects, broad-phase proximity queries.

See ``src/spatial/README.md`` for the full contract and ``docs/adr/ADR-011-scale-to-thousands.md``
for why this exists: a per-call rebuild is simple and always correct, but too slow past a
few hundred objects, so this structure persists across operations and is updated
incrementally. That trade creates exactly one risk — invalidation getting it wrong is a
*silent* wrong answer, since a stale ``AABB`` is a perfectly well-formed one — which is why
every method here is written to make that failure mode structurally impossible rather than
merely unlikely.
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, EngineProtocol

__all__ = ["SpatialIndex"]


class SpatialIndex:
    """BVH over scene objects, answering broad-phase proximity queries.

    See ``README.md`` in this directory for the full contract. Constructed once per
    engine and kept alive across operations — it is a maintained structure, not a
    per-call rebuild (ADR-011).

    Storage is a flat ``{object_id: AABB}`` cache plus a set of ids marked stale by
    ``invalidate()``. Every query resolves staleness lazily — one id at a time, only for
    ids it actually examines — through :meth:`_resolve`. That laziness is the entire
    point: an index that re-reads every object's bounds from the engine on every call
    would also answer correctly, but it would defeat the reason this module exists.
    """

    def __init__(self, engine: EngineProtocol) -> None:
        self._engine = engine
        self._bounds: dict[str, AABB] = {}
        self._stale: set[str] = set()

    def rebuild(self) -> None:
        """Full rebuild from ``engine.list_objects()``.

        The only operation guaranteed to leave zero stale entries no matter what state
        the index was in before it ran — a hard reset, not an incremental catch-up.
        """
        self._bounds = {
            object_id: self._engine.world_bounds(object_id)
            for object_id in self._engine.list_objects()
        }
        self._stale = set()

    def insert(self, object_id: str) -> None:
        self._bounds[object_id] = self._engine.world_bounds(object_id)
        self._stale.discard(object_id)

    def update(self, object_id: str) -> None:
        """The object moved or changed shape; its bounds are re-read from the engine."""
        self._bounds[object_id] = self._engine.world_bounds(object_id)
        self._stale.discard(object_id)

    def remove(self, object_id: str) -> None:
        self._bounds.pop(object_id, None)
        self._stale.discard(object_id)

    def invalidate(self, object_id: str) -> None:
        """Mark stale without re-reading yet; the next query must not return stale bounds."""
        if object_id in self._bounds:
            self._stale.add(object_id)

    def _resolve(self, object_id: str) -> AABB:
        """Current bounds for a known id, refreshing from the engine first if stale.

        This is the one place staleness is ever cleared, and every public query routes
        every id it examines through it. That makes "the next query touching this id" —
        the invalidation contract's own wording — a literal description of the code:
        ``stale_count`` only drops for ids a query actually looked at.
        """
        if object_id not in self._bounds:
            raise ValueError(f"spatial: unknown object {object_id!r} (never indexed or removed)")
        if object_id in self._stale:
            self._bounds[object_id] = self._engine.world_bounds(object_id)
            self._stale.discard(object_id)
        return self._bounds[object_id]

    def bounds_of(self, object_id: str) -> AABB:
        return self._resolve(object_id)

    def nearby(self, object_id: str, margin: float = 0.0) -> tuple[str, ...]:
        """Ids whose bounds overlap ``object_id``'s bounds expanded by ``margin``,
        excluding ``object_id`` itself."""
        subject = self._resolve(object_id)
        return tuple(
            other_id
            for other_id in self._bounds
            if other_id != object_id and subject.overlaps(self._resolve(other_id), tol=margin)
        )

    def pairs_overlapping(self, margin: float = 0.0) -> tuple[tuple[str, str], ...]:
        """Every unordered overlapping pair, each reported once, deterministically ordered."""
        ids = sorted(self._bounds)
        resolved = {object_id: self._resolve(object_id) for object_id in ids}
        return tuple(
            (a, b)
            for i, a in enumerate(ids)
            for b in ids[i + 1 :]
            if resolved[a].overlaps(resolved[b], tol=margin)
        )

    def in_region(self, region: AABB) -> tuple[str, ...]:
        return tuple(
            object_id for object_id in sorted(self._bounds) if self._resolve(object_id).overlaps(region)
        )

    def neighbours_of(self, object_ids: Sequence[str], margin: float = 0.0) -> tuple[str, ...]:
        """The scoping primitive ADR-011 requires: the given objects plus their
        neighbours, for scoped checks at thousands of objects."""
        found = set(object_ids)
        for object_id in object_ids:
            found.update(self.nearby(object_id, margin=margin))
        return tuple(sorted(found))

    @property
    def size(self) -> int:
        return len(self._bounds)

    @property
    def stale_count(self) -> int:
        return len(self._stale)
