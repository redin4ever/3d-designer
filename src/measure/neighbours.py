"""Neighbour-scoped pairwise checks — the two defect classes a single object id cannot see.

:func:`measure.inspect` runs every *single-object* check and says so. The two checks a
person actually notices in a build — parts driven into each other, and joints that should
meet and do not — need a second object, so the automatic post-operation loop, which knows
only what an operation just touched, could never run them. A railing driven through a tread
was reported by nobody until somebody asked by hand.

This is the missing half: *given these object ids and the engine, what is wrong between
them and the things they are near*. It is where :class:`spatial.SpatialIndex` genuinely
belongs — object-level, engine-backed, and already the structure ADR-011 built for scoping
checks at thousands of objects. Callers that keep an index alive across operations should
pass it; building one per call re-reads every object's bounds and defeats the point.
"""

from __future__ import annotations

from typing import Sequence

from contracts import Defect, EngineProtocol, JoineryIntent
from spatial import SpatialIndex

from ._errors import require_objects
from .intersections import find_clipping, find_visual_gaps

__all__ = ["neighbour_pairs", "neighbour_defects", "DEFAULT_MAX_GAP"]

#: The gap width below which two parts that should meet read as a defect rather than as a
#: deliberate reveal. 5 mm is the figure ADR-005's own worked example uses ("close every gap
#: under 5mm"); a caller with a tighter or looser standard passes its own.
DEFAULT_MAX_GAP = 0.005


def _index_for(
    engine: EngineProtocol, object_ids: Sequence[str], index: SpatialIndex | None
) -> SpatialIndex:
    """The caller's maintained index, or a fresh one.

    A supplied index may not know an id yet — an object created by the operation that
    triggered this check is the normal case — so each subject is inserted if missing.
    Inserting is not the same as invalidating: it never re-reads bounds the index already
    holds, so a maintained index keeps its laziness.
    """
    if index is None:
        fresh = SpatialIndex(engine)
        fresh.rebuild()
        return fresh
    for object_id in object_ids:
        try:
            index.bounds_of(object_id)
        except ValueError:
            index.insert(object_id)
    return index


def neighbour_pairs(
    engine: EngineProtocol,
    object_ids: Sequence[str],
    *,
    margin: float = 0.0,
    index: SpatialIndex | None = None,
) -> tuple[tuple[str, str], ...]:
    """Every unordered pair ``(a, b)`` where ``a`` or ``b`` is one of ``object_ids`` and
    the two are within ``margin`` metres of each other by bounding box.

    Each pair appears once, alphabetically ordered inside the pair and between them. Both
    matter: the objects of a clipping pair are usually touched by the same operation, so an
    unordered set that kept ``(a, b)`` and ``(b, a)`` would double every defect in the
    problem list, and an unstable order would make two identical checks produce two
    different reports.
    """
    ids = require_objects(engine, object_ids)
    resolved = _index_for(engine, ids, index)

    pairs: set[tuple[str, str]] = set()
    for object_id in ids:
        for other in resolved.nearby(object_id, margin=margin):
            pairs.add((object_id, other) if object_id < other else (other, object_id))
    return tuple(sorted(pairs))


def neighbour_defects(
    engine: EngineProtocol,
    object_ids: Sequence[str],
    *,
    joinery: Sequence[JoineryIntent] = (),
    max_gap: float = DEFAULT_MAX_GAP,
    margin: float = 0.0,
    index: SpatialIndex | None = None,
) -> tuple[Defect, ...]:
    """Clipping and visual-gap defects between ``object_ids`` and their spatial neighbours.

    The one call the automatic post-operation check needs. ``joinery`` is what keeps it
    usable: without a way to declare that a post is *meant* to be 500 mm into a deck, a
    staircase plus its railing reports dozens of clipping defects that are all correct
    joinery, and an agent that sees a problem list it must ignore learns to ignore the
    problem list.

    ``max_gap`` of ``0`` skips the visual-gap sweep entirely, which is the cheaper of the
    two by a wide margin only when it is not run — it measures real triangles, not boxes.

    The neighbour search widens to ``max(margin, max_gap)`` so a pair separated by a gap
    small enough to *be* the defect is still found; a pure overlap test would only ever
    return pairs that are already touching, and no visual gap could be reported at all.
    """
    pairs = neighbour_pairs(
        engine, object_ids, margin=max(margin, max_gap), index=index
    )
    if not pairs:
        return ()
    defects = find_clipping(engine, pairs, joinery)
    if max_gap > 0.0:
        defects += find_visual_gaps(engine, pairs, max_gap)
    return defects
