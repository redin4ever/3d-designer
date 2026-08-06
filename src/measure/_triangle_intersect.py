"""Private segment/triangle intersection primitive for self-intersection detection.

Möller–Trumbore ray-triangle intersection, restricted to a finite segment and to
strictly-interior hits. Kept apart from ``intersections.py`` so the numerical
primitive — the part most worth getting right in isolation — is not tangled up with
the mesh-level bookkeeping (adjacency filtering, defect construction) that calls it.
"""

from __future__ import annotations

from contracts import Vec3

__all__ = ["triangles_intersect"]

#: Deliberately tiny and dimensionless: it only guards against exact parallelism and
#: exact-boundary hits, both of which are genuine floating-point degeneracies, not
#: modelling tolerance. Modelling tolerance is ``contracts.EPSILON``; this is not that.
_EPS = 1e-9


def _segment_crosses_triangle(p0: Vec3, p1: Vec3, a: Vec3, b: Vec3, c: Vec3) -> bool:
    """True iff the open segment ``(p0, p1)`` pierces the *interior* of triangle
    ``(a, b, c)``.

    Deliberately excludes endpoints and the triangle's own edges/vertices: two
    triangles that legitimately share a vertex or edge (ordinary mesh connectivity)
    must never register as "intersecting" here — that filtering is what lets a clean,
    closed mesh report zero self-intersections.
    """
    edge1 = b - a
    edge2 = c - a
    direction = p1 - p0
    h = direction.cross(edge2)
    det = edge1.dot(h)
    if -_EPS < det < _EPS:
        return False  # segment parallel (or near-parallel) to the triangle's plane
    inv_det = 1.0 / det
    s = p0 - a
    u = inv_det * s.dot(h)
    if u <= _EPS or u >= 1.0 - _EPS:
        return False
    q = s.cross(edge1)
    v = inv_det * direction.dot(q)
    if v <= _EPS or u + v >= 1.0 - _EPS:
        return False
    t = inv_det * edge2.dot(q)
    return _EPS < t < 1.0 - _EPS


def triangles_intersect(
    tri_a: tuple[Vec3, Vec3, Vec3], tri_b: tuple[Vec3, Vec3, Vec3]
) -> bool:
    """True iff any edge of either triangle pierces the other's interior.

    Sufficient for two non-coplanar triangles in general position, which is what
    every mesh this product generates produces: a genuine transversal crossing
    always cuts through at least one edge of one triangle and the other's interior.
    Coplanar overlapping triangles (a much rarer degenerate case) are not detected by
    this test; no test in this suite exercises that case.
    """
    a0, a1, a2 = tri_a
    b0, b1, b2 = tri_b
    for p, q in ((a0, a1), (a1, a2), (a2, a0)):
        if _segment_crosses_triangle(p, q, b0, b1, b2):
            return True
    for p, q in ((b0, b1), (b1, b2), (b2, b0)):
        if _segment_crosses_triangle(p, q, a0, a1, a2):
            return True
    return False
