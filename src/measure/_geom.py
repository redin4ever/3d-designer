"""Private pure-math helpers shared by ``metrics.py`` and ``intersections.py``.

Split out so the AABB gap/overlap arithmetic behind ``distance``, ``gap_width``,
``find_clipping`` and ``find_visual_gaps`` is computed in exactly one place — four
independently-hand-rolled versions of "the gap between two boxes" is how one of them
quietly drifts from the other three. Nothing here is public (see ``README.md``: only
``measure/__init__.py``'s ``__all__`` is public).
"""

from __future__ import annotations

from typing import Sequence

from contracts import AABB, Vec3

__all__ = [
    "axis_gap",
    "axis_overlap",
    "aabb_gap_vector",
    "aabb_axis_overlaps",
    "dominant_local_axis",
    "signed_tetra_volume",
]


def axis_gap(lo_a: float, hi_a: float, lo_b: float, hi_b: float) -> float:
    """Empty span between two 1-D intervals. 0 when they touch or overlap, never
    negative — the same non-negativity ``distance`` and ``gap_width`` both promise."""
    return max(0.0, lo_b - hi_a, lo_a - hi_b)


def axis_overlap(lo_a: float, hi_a: float, lo_b: float, hi_b: float) -> float:
    """Signed overlap between two 1-D intervals.

    Positive means genuine interpenetration on this axis; zero or negative means the
    intervals merely touch (0) or are separated (negative) — the sign is what lets a
    caller tell "touching" apart from "overlapping" without a second comparison.
    """
    return min(hi_a, hi_b) - max(lo_a, lo_b)


def aabb_gap_vector(a: AABB, b: AABB) -> Vec3:
    """Per-axis empty span between two world-space boxes.

    The zero vector iff the boxes touch or overlap on every axis. Its length is the
    number ``distance`` and ``gap_width`` both report — computed once here so neither
    can silently diverge from the other.
    """
    return Vec3(
        axis_gap(a.minimum.x, a.maximum.x, b.minimum.x, b.maximum.x),
        axis_gap(a.minimum.y, a.maximum.y, b.minimum.y, b.maximum.y),
        axis_gap(a.minimum.z, a.maximum.z, b.minimum.z, b.maximum.z),
    )


def aabb_axis_overlaps(a: AABB, b: AABB) -> tuple[float, float, float]:
    """Per-axis overlap between two world-space boxes.

    All three positive iff the boxes genuinely interpenetrate (a positive-volume
    overlap); the smallest of the three is the exact minimum-translation penetration
    depth for two axis-aligned boxes — the number ``find_clipping`` reports as
    ``magnitude``.
    """
    return (
        axis_overlap(a.minimum.x, a.maximum.x, b.minimum.x, b.maximum.x),
        axis_overlap(a.minimum.y, a.maximum.y, b.minimum.y, b.maximum.y),
        axis_overlap(a.minimum.z, a.maximum.z, b.minimum.z, b.maximum.z),
    )


def dominant_local_axis(vertices: Sequence[Vec3]) -> Vec3:
    """The unit local axis (X, Y or Z) spanning an object's largest local extent —
    its own "long" direction before any rotation is applied. ``angle_between`` rotates
    this by each object's transform and compares the results."""
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]
    zs = [v.z for v in vertices]
    extents = (
        (max(xs) - min(xs), Vec3(1.0, 0.0, 0.0)),
        (max(ys) - min(ys), Vec3(0.0, 1.0, 0.0)),
        (max(zs) - min(zs), Vec3(0.0, 0.0, 1.0)),
    )
    return max(extents, key=lambda pair: pair[0])[1]


def signed_tetra_volume(a: Vec3, b: Vec3, c: Vec3) -> float:
    """Signed volume of the tetrahedron formed by the world origin and triangle
    ``(a, b, c)``.

    Summed over every triangle of a closed, consistently-wound mesh this is the
    mesh's enclosed volume by the divergence theorem — exact for any watertight
    shape, convex or not, unlike multiplying the bounding box's extents (see
    ``metrics_test.py::test_volume_of_a_pyramid_is_not_its_bounding_box``).
    """
    return a.dot(b.cross(c)) / 6.0
