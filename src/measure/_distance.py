"""True mesh-to-mesh distance.

``distance`` and ``gap_width`` were computed from world AABBs alone. For an axis-aligned
box that is exact; for anything rotated it is badly wrong, because the AABB of a 45°-yawed
4 m beam is far larger than the beam. Two such beams 1.4 m apart reported ``distance=0.0``
while ``find_clipping`` simultaneously reported a 0.1 m interpenetration between parts that
never touch. Every test used an unrotated cube, so nothing saw it.

ADR-005 gives measurement authority over the agent's own judgement, which makes a
confidently wrong number worse than no number: the agent moves correct geometry to fix a
defect that does not exist.

The maths here is standard: closest distance between two triangles is either a
vertex-to-face distance or an edge-to-edge distance, so both are checked.
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, MeshSnapshot, Vec3

__all__ = ["mesh_distance", "MAX_TRIANGLE_PAIRS"]

#: Beyond this many candidate triangle pairs the exact sweep is abandoned and the AABB
#: bound is returned instead, flagged by the caller. A wrong answer computed quickly is the
#: thing this module exists to stop; a slow one that never returns is no better.
MAX_TRIANGLE_PAIRS = 250_000


def _clamp(v: float, lo: float, hi: float) -> float:
    return lo if v < lo else hi if v > hi else v


def _point_segment_sq(p: Vec3, a: Vec3, b: Vec3) -> float:
    ab = b - a
    denom = ab.dot(ab)
    t = 0.0 if denom <= 0.0 else _clamp((p - a).dot(ab) / denom, 0.0, 1.0)
    d = p - (a + ab * t)
    return d.dot(d)


def _point_triangle_sq(p: Vec3, a: Vec3, b: Vec3, c: Vec3) -> float:
    """Squared distance from a point to a triangle, including its interior.

    Projects onto the triangle's plane and, if the projection falls outside, falls back to
    the nearest of the three edges — which is what makes this correct for the common case
    of a face pointing at another face.
    """
    ab, ac = b - a, c - a
    normal = ab.cross(ac)
    n2 = normal.dot(normal)
    if n2 > 1e-20:
        # Barycentric test against the plane projection.
        ap = p - a
        d = normal.dot(ap) / n2
        proj = p - normal * d
        v0, v1, v2 = ab, ac, proj - a
        d00, d01, d11 = v0.dot(v0), v0.dot(v1), v1.dot(v1)
        d20, d21 = v2.dot(v0), v2.dot(v1)
        denom = d00 * d11 - d01 * d01
        if abs(denom) > 1e-20:
            v = (d11 * d20 - d01 * d21) / denom
            w = (d00 * d21 - d01 * d20) / denom
            if v >= 0.0 and w >= 0.0 and v + w <= 1.0:
                gap = proj - p
                return gap.dot(gap)
    return min(
        _point_segment_sq(p, a, b),
        _point_segment_sq(p, b, c),
        _point_segment_sq(p, c, a),
    )


def _segment_segment_sq(p1: Vec3, q1: Vec3, p2: Vec3, q2: Vec3) -> float:
    """Squared distance between two segments — the case a vertex-to-face test misses.

    Two crossed beams can have every vertex far from the other's faces while their edges
    pass close together, so omitting this silently overestimates the gap.
    """
    d1, d2, r = q1 - p1, q2 - p2, p1 - p2
    a, e, f = d1.dot(d1), d2.dot(d2), d2.dot(r)
    if a <= 1e-20 and e <= 1e-20:
        return r.dot(r)
    if a <= 1e-20:
        s, t = 0.0, _clamp(f / e, 0.0, 1.0)
    else:
        c = d1.dot(r)
        if e <= 1e-20:
            t, s = 0.0, _clamp(-c / a, 0.0, 1.0)
        else:
            b = d1.dot(d2)
            denom = a * e - b * b
            s = _clamp((b * f - c * e) / denom, 0.0, 1.0) if denom > 1e-20 else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, _clamp(-c / a, 0.0, 1.0)
            elif t > 1.0:
                t, s = 1.0, _clamp((b - c) / a, 0.0, 1.0)
    diff = (p1 + d1 * s) - (p2 + d2 * t)
    return diff.dot(diff)


def _triangle_distance_sq(t1: tuple[Vec3, Vec3, Vec3], t2: tuple[Vec3, Vec3, Vec3]) -> float:
    best = min(_point_triangle_sq(p, *t2) for p in t1)
    best = min(best, min(_point_triangle_sq(p, *t1) for p in t2))
    edges1 = ((t1[0], t1[1]), (t1[1], t1[2]), (t1[2], t1[0]))
    edges2 = ((t2[0], t2[1]), (t2[1], t2[2]), (t2[2], t2[0]))
    for a1, b1 in edges1:
        for a2, b2 in edges2:
            best = min(best, _segment_segment_sq(a1, b1, a2, b2))
            if best <= 0.0:
                return 0.0
    return best


def _tri_bounds(tri: tuple[Vec3, Vec3, Vec3]) -> AABB:
    return AABB.from_points(tri)


def _aabb_gap(a: AABB, b: AABB) -> float:
    dx = max(0.0, max(a.minimum.x - b.maximum.x, b.minimum.x - a.maximum.x))
    dy = max(0.0, max(a.minimum.y - b.maximum.y, b.minimum.y - a.maximum.y))
    dz = max(0.0, max(a.minimum.z - b.maximum.z, b.minimum.z - a.maximum.z))
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def mesh_distance(a: MeshSnapshot, b: MeshSnapshot) -> tuple[float, bool]:
    """``(distance, exact)`` — the true closest surface-to-surface distance in metres.

    ``exact`` is ``False`` when the pair was too large to sweep and the returned value is
    the AABB lower bound instead. The caller must say so rather than presenting a bound as
    a measurement; a number the agent cannot distinguish from a real one is the failure this
    whole module exists to prevent.
    """
    tris_a = [tuple(a.transform.apply(a.vertices[i]) for i in t) for t in a.triangles]
    tris_b = [tuple(b.transform.apply(b.vertices[i]) for i in t) for t in b.triangles]
    if not tris_a or not tris_b:
        return (0.0, False)

    if len(tris_a) * len(tris_b) > MAX_TRIANGLE_PAIRS:
        return (_aabb_gap(a.world_bounds(), b.world_bounds()), False)

    bounds_b = [_tri_bounds(t) for t in tris_b]
    best_sq = float("inf")
    for t1 in tris_a:
        box1 = _tri_bounds(t1)
        for t2, box2 in zip(tris_b, bounds_b):
            # Cheap reject: no triangle pair can be closer than their boxes are.
            lower = _aabb_gap(box1, box2)
            if lower * lower >= best_sq:
                continue
            best_sq = min(best_sq, _triangle_distance_sq(t1, t2))
            if best_sq <= 0.0:
                return (0.0, True)
    return (best_sq ** 0.5, True)
