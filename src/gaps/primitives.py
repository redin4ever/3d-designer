"""Thin wrappers over ``EngineProtocol`` repair primitives.

Each of these delegates entirely to an existing ``ModifierOps`` method — ``fill_holes``,
``merge_by_distance`` — rather than re-deriving mesh surgery gaps already has a primitive
for. See ``CLAUDE.md`` for why the other repairs in this package cannot do the same.
"""

from __future__ import annotations

from contracts import EPSILON, EngineProtocol, RepairOutcome

__all__ = ["fill_boundary_holes", "weld_duplicates", "merge_shells"]


def fill_boundary_holes(
    engine: EngineProtocol, object_id: str, *, max_sides: int = 0
) -> RepairOutcome:
    """Triangulate every boundary loop up to ``max_sides`` (0 = no limit).

    ``DefectClass.BOUNDARY_HOLE``. A loop wider than ``max_sides`` is reported in
    ``skipped``, never silently dropped from ``fixed`` — a bare 0 cannot tell "no holes"
    from "found a hole and declined it" (``contracts.RepairOutcome``).
    """
    return engine.fill_holes(object_id, max_sides=max_sides)


def weld_duplicates(
    engine: EngineProtocol, object_id: str, *, tolerance: float = EPSILON
) -> RepairOutcome:
    """Merge vertices within ``tolerance`` of each other.

    ``DefectClass.LOOSE_OR_DUPLICATE`` — the *duplicate* half only. A vertex referenced by
    no face is not near anything to merge with and survives this call untouched; that is
    :func:`gaps.remove_loose`'s job, not this one's (see ``CLAUDE.md``).
    """
    return engine.merge_by_distance(object_id, tolerance)


def merge_shells(
    engine: EngineProtocol, object_id: str, *, max_distance: float
) -> RepairOutcome:
    """Weld vertices across separate shells of one object within ``max_distance``.

    The same primitive as :func:`weld_duplicates`, at a caller-chosen distance meant to
    span a real gap between shells rather than float noise between coincident points —
    ``weld_duplicates`` defaults to ``EPSILON`` on purpose so it never bridges a gap that
    was never meant to close.
    """
    return engine.merge_by_distance(object_id, max_distance)
