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

from contracts import EPSILON, MeshSnapshot, Vec3

__all__ = ["suggest_seams"]


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
            # A degenerate (zero-area) adjacent triangle has no well-defined normal — treat
            # the edge as unmeasurable rather than crashing on it.
            continue

        cosine = max(-1.0, min(1.0, n1.dot(n2)))
        dihedral_deg = math.degrees(math.acos(cosine))
        if dihedral_deg >= min_dihedral_deg:
            selected.append(idx)

    return tuple(selected)


def _triangle_normal(verts: list[Vec3], tri: tuple[int, int, int]) -> Vec3 | None:
    a, b, c = verts[tri[0]], verts[tri[1]], verts[tri[2]]
    cross = (b - a).cross(c - a)
    # EPSILON, not 1e-12: Vec3.normalized() raises below EPSILON, so a sliver whose
    # cross product falls between the two thresholds passes this guard and then trips
    # the very call it guards. detail/edges.py hit exactly this and was fixed; this
    # duplicated copy never received the fix.
    if cross.length() < EPSILON:
        return None
    return cross.normalized()


def _build_adjacency(triangles) -> dict[tuple[int, int], list[int]]:
    """Edge -> the triangle indices that touch it. Built once per call, not per edge."""
    adjacency: dict[tuple[int, int], list[int]] = {}
    for ti, tri in enumerate(triangles):
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            key = (a, b) if a < b else (b, a)
            adjacency.setdefault(key, []).append(ti)
    return adjacency
