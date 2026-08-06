"""Pure geometry helpers used by the test engine.

Separated from ``fake_engine`` because these are stateless functions over plain data with
no engine concept in them at all — a distinct actor, and the part most worth testing
directly. Nothing here imports bpy.
"""

from __future__ import annotations

import math
from typing import Sequence

from contracts import Quat, Vec3, WORLD_UP

__all__ = [
    "unit_cube",
    "sample_polyline",
    "arc_length_to",
    "tangent_at",
    "rotation_from_up_to",
    "boundary_loops",
    "connected_components",
]


def unit_cube(size: Vec3 | None = None) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """A closed, manifold, outward-wound box centred on the origin."""
    s = size or Vec3(1.0, 1.0, 1.0)
    hx, hy, hz = s.x / 2, s.y / 2, s.z / 2
    verts = [
        Vec3(-hx, -hy, -hz), Vec3(hx, -hy, -hz), Vec3(hx, hy, -hz), Vec3(-hx, hy, -hz),
        Vec3(-hx, -hy, hz), Vec3(hx, -hy, hz), Vec3(hx, hy, hz), Vec3(-hx, hy, hz),
    ]
    faces: list[tuple[int, ...]] = [
        (0, 3, 2, 1),  # bottom — wound so the normal points -Z
        (4, 5, 6, 7),  # top
        (0, 1, 5, 4),  # -Y
        (1, 2, 6, 5),  # +X
        (2, 3, 7, 6),  # +Y
        (3, 0, 4, 7),  # -X
    ]
    return verts, faces


def sample_polyline(points: Sequence[Vec3], spacing: float) -> list[Vec3]:
    """Positions at a regular arc-length interval along a polyline.

    Spacing is measured along the path, not along a straight line between endpoints —
    the difference is what stops instances bunching up around a bend.
    """
    if spacing <= 0:
        raise ValueError("spacing must be positive")
    out = [points[0]]
    carry = 0.0
    for a, b in zip(points, points[1:]):
        seg = b - a
        length = seg.length()
        if length < 1e-9:
            continue
        direction = seg * (1.0 / length)
        t = spacing - carry
        while t <= length + 1e-9:
            out.append(a + direction * t)
            t += spacing
        carry = (carry + length) % spacing
    if (out[-1] - points[-1]).length() > 1e-6:
        out.append(points[-1])
    return out


def arc_length_to(points: Sequence[Vec3], target: Vec3) -> float:
    """Distance along the polyline to the point nearest ``target``.

    Used to order instances along a path when forced positions (corners) are mixed in
    with regularly-spaced ones.
    """
    total = 0.0
    best = math.inf
    best_len = 0.0
    for a, b in zip(points, points[1:]):
        seg = b - a
        length = seg.length()
        if length > 1e-9:
            t = max(0.0, min(1.0, (target - a).dot(seg) / (length * length)))
            d = (target - (a + seg * t)).length()
            if d < best:
                best, best_len = d, total + t * length
        total += length
    return best_len


def tangent_at(points: Sequence[Vec3], position: Vec3) -> Vec3:
    """Unit direction of the polyline segment nearest ``position``."""
    best, best_dist = points[1] - points[0], math.inf
    for a, b in zip(points, points[1:]):
        seg = b - a
        length = seg.length()
        if length < 1e-9:
            continue
        t = max(0.0, min(1.0, (position - a).dot(seg) / (length * length)))
        d = (position - (a + seg * t)).length()
        if d < best_dist:
            best, best_dist = seg, d
    return best.normalized()


def rotation_from_up_to(direction: Vec3) -> Quat:
    """The rotation taking world up onto ``direction``.

    This is what *not* to apply to a fence post. Aligning an instance's own up-axis to the
    path tangent is the classic naive-generator error: on a stair rake it produces posts
    leaning at the stair angle instead of standing plumb.
    """
    d = direction.normalized()
    axis = WORLD_UP.cross(d)
    if axis.length() < 1e-9:
        return Quat.identity() if d.z > 0 else Quat.from_axis_angle(Vec3(1, 0, 0), math.pi)
    return Quat.from_axis_angle(axis, math.acos(max(-1.0, min(1.0, WORLD_UP.dot(d)))))


def boundary_loops(edges: Sequence[tuple[int, int]]) -> list[list[int]]:
    """Group boundary edges into closed loops.

    A boundary edge is one bounding exactly one face. Each loop it forms is one hole.
    """
    adjacency: dict[int, list[int]] = {}
    for a, b in edges:
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    unvisited = set(edges)
    loops: list[list[int]] = []
    while unvisited:
        a, b = next(iter(unvisited))
        unvisited.discard((a, b))
        loop = [a, b]
        while True:
            nxt = None
            for cand in adjacency.get(loop[-1], []):
                e = (min(loop[-1], cand), max(loop[-1], cand))
                if e in unvisited:
                    nxt = cand
                    unvisited.discard(e)
                    break
            if nxt is None or nxt == loop[0]:
                break
            loop.append(nxt)
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def connected_components(
    vertex_count: int, faces: Sequence[Sequence[int]]
) -> list[set[int]]:
    """Vertex groups connected through shared faces — i.e. the mesh's separate shells."""
    adjacency: dict[int, set[int]] = {i: set() for i in range(vertex_count)}
    for f in faces:
        for a in f:
            adjacency[a].update(f)
    seen: set[int] = set()
    components: list[set[int]] = []
    for start in adjacency:
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            n = stack.pop()
            if n in comp:
                continue
            comp.add(n)
            stack.extend(adjacency[n] - comp)
        seen |= comp
        components.append(comp)
    return components
