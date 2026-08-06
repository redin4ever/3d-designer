"""Which object pairs the automatic check has to compare (ADR-011, Gate B F-014).

``_new_problems`` used to call ``measure.inspect``, whose own docstring says it *excludes*
the pairwise checks — while every ``ActionReport`` went out stamped
``checks_scope: "changed+neighbours"``. A 4 m room produced 39 real clipping defects and
nothing reported one. The report was not wrong about what it found; it was wrong about what
it had looked at, which is the worse of the two.

The pairs come from ``spatial``'s maintained BVH rather than a sweep. A whole-scene pairwise
comparison is O(n²) and, at the cadence the user actually asked for — after every geometry
change — that is the difference between a check that runs and a check that gets switched
off. The index is kept alive across operations and updated incrementally, which is the whole
reason ``src/spatial/`` exists.
"""

from __future__ import annotations

import threading
from typing import Iterable, Sequence

from contracts import EngineProtocol
from spatial import SpatialIndex

__all__ = ["NeighbourIndex"]


class NeighbourIndex:
    """A ``SpatialIndex`` kept in step with the live engine, and the pair queries over it.

    Owns its own mutex. The per-operation check runs on the writer's thread while
    ``can_promote`` can be called from any inspect agent's thread at the same moment, and a
    BVH mutated by one while the other reads it answers with bounds for objects that no
    longer exist — a *silent* wrong answer, since a stale ``AABB`` is a perfectly well-formed
    one.
    """

    def __init__(self, engine: EngineProtocol) -> None:
        self._engine = engine
        self._index = SpatialIndex(engine)
        self._known: set[str] = set()
        self._guard = threading.Lock()

    def _sync(self, touched: Iterable[str] = ()) -> set[str]:
        """Bring the index level with the engine, incrementally.

        Insert what appeared, drop what went away, re-read what the operation touched.
        Deliberately not ``rebuild()``: a full rebuild re-reads every object's bounds on
        every operation, which is correct and is exactly the cost ADR-011 exists to avoid.
        """
        live = set(self._engine.list_objects())
        for gone in self._known - live:
            self._index.remove(gone)
        for added in live - self._known:
            self._index.insert(added)
        for object_id in touched:
            if object_id in live:
                self._index.update(object_id)
        self._known = live
        return live

    def pairs_touching(
        self, touched: Sequence[str], margin: float
    ) -> tuple[tuple[str, str], ...]:
        """Every unordered pair of (a changed object, something near it), each reported once.

        ``margin`` expands the search: a pair whose boxes already overlap can be clipping,
        but a pair separated by a visible gap cannot be found without looking slightly wider
        than "touching". A gap detector that only sees overlapping boxes returns nothing,
        forever, and looks like a clean scene.
        """
        with self._guard:
            live = self._sync(touched)
            pairs: set[tuple[str, str]] = set()
            for object_id in touched:
                if object_id not in live:
                    continue
                for other in self._index.nearby(object_id, margin=margin):
                    pairs.add(
                        (object_id, other) if object_id < other else (other, object_id)
                    )
        return tuple(sorted(pairs))

    def all_pairs(self, margin: float) -> tuple[tuple[str, str], ...]:
        """Every overlapping pair in the whole scene.

        For the phase gate only. A promotion asks "is the *whole* scene ready", so scoping it
        to recent changes would let a defect introduced early survive every later check —
        and a promotion happens a handful of times per run, where a per-operation check
        happens thousands of times. Different question, different cost, different answer.
        """
        with self._guard:
            self._sync()
            return self._index.pairs_overlapping(margin=margin)
