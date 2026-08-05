"""Stub — self-intersection, clipping and visual-gap detection.

``find_clipping`` is the heart of the product. No library can tell a post socketed 50mm
into a deck (correct) apart from two posts overlapping by 50mm (a bug) from geometry
alone — both are identical BVH overlaps of identical magnitude. The difference is declared
intent (:class:`contracts.JoineryIntent`), never inferred. See ``src/measure/README.md``.

Nothing below is implemented yet — every function raises. Pure: read-only.
"""

from __future__ import annotations

from typing import Sequence

from contracts import Defect, EngineProtocol, JoineryIntent

__all__ = ["find_self_intersections", "find_clipping", "find_visual_gaps"]


def find_self_intersections(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per pair of non-adjacent triangles of the same mesh that share
    points in 3D.

    ``DefectClass.SELF_INTERSECTION``.
    """
    raise NotImplementedError("measure.find_self_intersections: not implemented")


def find_clipping(
    engine: EngineProtocol,
    pairs: Sequence[tuple[str, str]],
    joinery: Sequence[JoineryIntent] = (),
) -> tuple[Defect, ...]:
    """One :class:`Defect` per pair in ``pairs`` whose interpenetration is not covered by a
    matching :class:`JoineryIntent` in ``joinery`` (matched by ``{object_id, into_object_id}
    == {a, b}``, permitted when the measured overlap satisfies
    :meth:`JoineryIntent.permits`). A pair that only touches (zero overlap) never reports.

    ``pairs`` is normally the output of ``spatial.pairs_overlapping(engine)``; this function
    takes the plain sequence of ids so it carries no dependency on the ``spatial`` module.

    ``DefectClass.PART_CLIPPING``.
    """
    raise NotImplementedError("measure.find_clipping: not implemented")


def find_visual_gaps(
    engine: EngineProtocol, pairs: Sequence[tuple[str, str]], max_gap: float
) -> tuple[Defect, ...]:
    """One :class:`Defect` per pair in ``pairs`` separated by an empty span greater than
    zero and less than or equal to ``max_gap`` — two parts that should meet and do not.

    Passes every manifold and watertight check, because each part is individually fine;
    that is the entire reason this check exists as its own thing. ``DefectClass.VISUAL_GAP``.
    """
    raise NotImplementedError("measure.find_visual_gaps: not implemented")
