"""Self-intersection, clipping and visual-gap detection.

``find_clipping`` is the heart of the product. No library can tell a post socketed 50mm
into a deck (correct) apart from two posts overlapping by 50mm (a bug) from geometry
alone — both are identical BVH overlaps of identical magnitude. The difference is
declared intent (:class:`contracts.JoineryIntent`), never inferred. See
``src/measure/README.md``.

Pure: read-only, via ``engine.snapshot`` and ``engine.world_bounds`` only.
"""

from __future__ import annotations

from typing import Sequence

from contracts import Defect, DefectClass, EngineProtocol, JoineryIntent

from ._geom import aabb_axis_overlaps, aabb_gap_vector
from ._triangle_intersect import triangles_intersect

__all__ = ["find_self_intersections", "find_clipping", "find_visual_gaps"]


def find_self_intersections(engine: EngineProtocol, object_id: str) -> tuple[Defect, ...]:
    """One :class:`Defect` per pair of non-adjacent triangles of the same mesh that share
    points in 3D.

    "Non-adjacent" means sharing no vertex index — two triangles that share a vertex
    (or a whole edge) are ordinary mesh connectivity, not a defect, even though they
    technically "share points". ``magnitude`` is left unmeasured (``None``): unlike
    :func:`find_clipping`'s AABB-based estimate, a crossing between two triangles has
    no natural single-number "depth", and ``None`` — never ``0.0`` — is how this
    module says "genuinely not measured" rather than "measured as zero" (see
    ``contracts.Defect.magnitude``). ``DefectClass.SELF_INTERSECTION``.
    """
    snap = engine.snapshot(object_id)
    verts = snap.world_vertices()
    triangles = snap.triangles

    defects = []
    for i in range(len(triangles)):
        for j in range(i + 1, len(triangles)):
            if set(triangles[i]) & set(triangles[j]):
                continue  # shared vertex: adjacent, not a defect
            tri_a = tuple(verts[v] for v in triangles[i])
            tri_b = tuple(verts[v] for v in triangles[j])
            if triangles_intersect(tri_a, tri_b):
                defects.append(
                    Defect.of(
                        DefectClass.SELF_INTERSECTION, object_id,
                        f"triangles {i} and {j} share points in 3D",
                    )
                )
    return tuple(defects)


def find_clipping(
    engine: EngineProtocol,
    pairs: Sequence[tuple[str, str]],
    joinery: Sequence[JoineryIntent] = (),
) -> tuple[Defect, ...]:
    """One :class:`Defect` per pair in ``pairs`` whose interpenetration is not covered by a
    matching :class:`JoineryIntent` in ``joinery`` (matched by ``{object_id, into_object_id}
    == {a, b}``, permitted when the measured overlap satisfies
    :meth:`JoineryIntent.permits`). A pair that only touches (zero overlap) never reports.

    ``magnitude`` is the smallest of the three per-axis AABB overlaps — exact for two
    axis-aligned boxes (which is what every test and every declared ``JoineryIntent``
    depth in this product describes: a post socketed N mm into a deck), and the same
    quantity :meth:`JoineryIntent.permits` compares its declared ``depth`` against.

    ``pairs`` is normally the output of ``spatial.pairs_overlapping(engine)``; this function
    takes the plain sequence of ids so it carries no dependency on the ``spatial`` module.

    ``DefectClass.PART_CLIPPING``.
    """
    defects = []
    for a, b in pairs:
        overlaps = aabb_axis_overlaps(engine.world_bounds(a), engine.world_bounds(b))
        magnitude = min(overlaps)
        if magnitude <= 0.0:
            continue  # separated, or merely touching — not a defect either way

        matching = [j for j in joinery if {j.object_id, j.into_object_id} == {a, b}]
        if any(intent.permits(magnitude) for intent in matching):
            continue

        defects.append(
            Defect.of(
                DefectClass.PART_CLIPPING, a,
                f"{a} interpenetrates {b} by {magnitude:.4g}m",
                magnitude=magnitude, other_object_id=b,
            )
        )
    return tuple(defects)


def find_visual_gaps(
    engine: EngineProtocol, pairs: Sequence[tuple[str, str]], max_gap: float
) -> tuple[Defect, ...]:
    """One :class:`Defect` per pair in ``pairs`` separated by an empty span greater than
    zero and less than or equal to ``max_gap`` — two parts that should meet and do not.

    Passes every manifold and watertight check, because each part is individually fine;
    that is the entire reason this check exists as its own thing. The gap must be
    *strictly* greater than zero: two parts that merely touch are not a visual gap, and
    reporting them as one would bury every genuine gap in noise from ordinary abutting
    joints. ``DefectClass.VISUAL_GAP``.
    """
    defects = []
    for a, b in pairs:
        gap = aabb_gap_vector(engine.world_bounds(a), engine.world_bounds(b)).length()
        if 0.0 < gap <= max_gap:
            defects.append(
                Defect.of(
                    DefectClass.VISUAL_GAP, a,
                    f"{a} and {b} are separated by {gap:.4g}m",
                    magnitude=gap, other_object_id=b,
                )
            )
    return tuple(defects)
