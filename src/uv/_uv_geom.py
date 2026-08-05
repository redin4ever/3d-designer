"""Pure 2D UV-space geometry: triangle area and triangle-triangle overlap.

Split from ``quality.py`` the same way ``measure/_geom.py`` splits pure geometry primitives
from the metric functions that call them (see ``src/measure/_geom.py``) — neither function
here has any concept of an engine, a snapshot, or a ``Measurement``.

Nothing here computes anything yet; every function raises until an implementer replaces the
body (Rule 4 — tests come first).
"""

from __future__ import annotations

import math

__all__ = ["uv_triangle_area", "triangles_overlap"]

Point = tuple[float, float]
Triangle = tuple[Point, Point, Point]


def uv_triangle_area(a: Point, b: Point, c: Point) -> float:
    """Unsigned area of a triangle in 2D UV space (shoelace formula)."""
    return abs((b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])) / 2.0


def triangles_overlap(tri_a: Triangle, tri_b: Triangle, eps: float = 1e-9) -> bool:
    """True iff the two triangles' interiors overlap with positive area.

    Separating Axis Theorem over the six candidate axes (each triangle's three edge
    normals) — exact for convex polygons, which a triangle always is. Two triangles that
    only *touch* — sharing an edge or a vertex, with no interior in common — must not count
    as overlapping (a well-formed unwrap tiles adjacent triangles edge-to-edge; that contact
    is not the defect this function exists to catch), so a zero-width gap between two
    triangles' projections counts as separation via ``eps`` rather than requiring a strictly
    positive one.
    """
    for tri in (tri_a, tri_b):
        for i in range(3):
            p0, p1 = tri[i], tri[(i + 1) % 3]
            axis = (-(p1[1] - p0[1]), p1[0] - p0[0])
            if math.hypot(axis[0], axis[1]) < eps:
                continue  # a degenerate edge carries no separating information
            lo_a, hi_a = _project(tri_a, axis)
            lo_b, hi_b = _project(tri_b, axis)
            if hi_a <= lo_b + eps or hi_b <= lo_a + eps:
                return False
    return True


def _project(tri: Triangle, axis: Point) -> tuple[float, float]:
    values = [p[0] * axis[0] + p[1] * axis[1] for p in tri]
    return min(values), max(values)
