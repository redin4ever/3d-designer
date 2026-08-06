"""Stub — ``suggest_seams``, the automatic hard-crease seam suggestion.

See ``src/uv/README.md`` for the full contract. UV is the highest-risk area in v1: seams and
stretching are where every existing AI-3D tool fails most visibly, and this function is the
default seam placement every unwrap uses unless the agent overrides it by name.

The model is ``src/detail/edges.py``'s dihedral-angle candidate search (same
``acos(dot(n1, n2))`` construction, same "only an edge with exactly two adjacent triangles is
a candidate" rule) — reimplemented locally rather than imported, because ``uv`` depends only
on ``contracts`` and ``measure`` (``.pipeline/modules.json``), not on ``detail``. Unlike
``detail.select_bevel_edges`` this applies no convexity or "hidden face" filter: every hard
crease is a legitimate seam candidate regardless of which way it folds, and a seam that
happens to face away from the camera is, if anything, the *best* place to hide a texture
discontinuity — the opposite of the bevel module's reasoning for excluding it.

Nothing here computes anything yet; the function raises until an implementer replaces the
body (Rule 4 — tests come first).
"""

from __future__ import annotations

import math

from contracts import MeshSnapshot, Vec3

__all__ = ["suggest_seams"]

#: The floor below which a triangle has no representable orientation at all.
#:
#: Deliberately the same **numerical** floor ``detail.edges.DEGENERATE_CROSS_LENGTH`` uses,
#: and deliberately not the same as the coarser *product* floor
#: ``align.position``/``constraints.anchors`` apply to the same formula — those two group
#: triangles into anchorable faces, this one reads a dihedral angle.
#: ``align/duplicated_geometry_test.py`` pins all four against each other.
#:
#: This was ``EPSILON`` (1e-4), inherited from ``Vec3.normalized()``, which raises below it.
#: That is 0.1 mm of *distance* being compared against a cross-product length — twice a
#: triangle's **area** — so it rejected small triangles rather than degenerate ones. Measured
#: on real Blender output: a default 4 mm bevel on a 0.28 x 1.0 x 0.18 m stair tread yields
#: 156 triangles of which 72 fall in [9.4e-6, 9.3e-5], all under ``EPSILON``, leaving 144 of
#: 234 candidate edges unreadable. For seams that means every crease around a bevelled corner
#: silently stops being a seam candidate — and UV seams are, per this module's README, the
#: single most visible failure mode in the product.
DEGENERATE_CROSS_LENGTH = 1e-15


def suggest_seams(snapshot: MeshSnapshot, *, min_dihedral_deg: float = 60.0) -> tuple[int, ...]:
    """Indices into ``snapshot.edges()`` where a seam plausibly belongs: hard creases.

    An edge is a *candidate* only if it has exactly two adjacent triangles — a boundary edge
    has no second face to measure a dihedral angle against and is never suggested. Among
    candidates, one qualifies iff its dihedral angle (the angle between the two adjacent
    triangles' face normals, ``acos(dot(n1, n2))`` in degrees, ``[0, 180]``) is at least
    ``min_dihedral_deg``.

    Every returned index is guaranteed to be inside ``range(len(snapshot.edges()))`` — an
    out-of-range index would silently seam whichever edge happens to sit at that position at
    the engine end instead, with no error at all (see ``MeshSnapshot.edges()``'s own
    docstring).
    """
    edges = snapshot.edges()
    verts = snapshot.world_vertices()
    adjacency = _build_adjacency(snapshot.triangles)
    normals = [_triangle_normal(verts, tri) for tri in snapshot.triangles]

    selected: list[int] = []
    for idx, (u, v) in enumerate(edges):
        occurrences = adjacency.get((u, v), ())
        if len(occurrences) != 2:
            # A boundary edge (one adjacent face) has no dihedral angle to measure and was
            # never a candidate.
            continue

        t1, t2 = occurrences
        n1, n2 = normals[t1], normals[t2]
        if n1 is None or n2 is None:
            # A literally zero-area adjacent triangle has no well-defined normal — treat the
            # edge as unmeasurable rather than crashing on it. This is now rare by
            # construction (see DEGENERATE_CROSS_LENGTH); it used to swallow 61% of a
            # bevelled mesh's candidate edges.
            continue

        cosine = max(-1.0, min(1.0, n1.dot(n2)))
        dihedral_deg = math.degrees(math.acos(cosine))
        if dihedral_deg >= min_dihedral_deg:
            selected.append(idx)

    return tuple(selected)


def _triangle_normal(verts: list[Vec3], tri: tuple[int, int, int]) -> Vec3 | None:
    """The triangle's unit normal, or ``None`` when it has no orientation at all.

    ``None`` on a degenerate triangle is the answer all four copies of this function give
    (``detail.edges``, ``align.position``, ``constraints.anchors``); the floor is the one
    thing they are allowed to differ on, and this copy uses the numerical one — see
    :data:`DEGENERATE_CROSS_LENGTH`. ``align/duplicated_geometry_test.py`` fails if either
    half of that arrangement drifts.

    Normalises by hand rather than through ``Vec3.normalized()``, which raises below
    ``EPSILON``: routing through it would silently re-impose a 1e-4 floor that has nothing
    to do with what this function is deciding.
    """
    a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
    cross = (b - a).cross(c - a)
    length = cross.length()
    if length <= DEGENERATE_CROSS_LENGTH:
        return None
    return Vec3(cross.x / length, cross.y / length, cross.z / length)


def _build_adjacency(triangles) -> dict[tuple[int, int], list[int]]:
    """Edge -> the triangle indices that touch it. Built once per call, not per edge."""
    adjacency: dict[tuple[int, int], list[int]] = {}
    for ti, tri in enumerate(triangles):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            adjacency.setdefault(key, []).append(ti)
    return adjacency
