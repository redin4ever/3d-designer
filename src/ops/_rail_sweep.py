"""Continuous rectangular sweeps for handrails with true shared miter rings."""

from __future__ import annotations

from contracts import Vec3

__all__ = ["mitered_rectangular_sweep"]


def _frame(tangent: Vec3) -> tuple[Vec3, Vec3]:
    reference = Vec3(0.0, 0.0, 1.0)
    if abs(tangent.dot(reference)) > 0.999:
        reference = Vec3(1.0, 0.0, 0.0)
    right = tangent.cross(reference).normalized()
    return right, right.cross(tangent).normalized()


def _endpoint_ring(
    centre: Vec3, tangent: Vec3, width: float, depth: float
) -> list[Vec3]:
    right, up = _frame(tangent)
    hw, hd = width / 2.0, depth / 2.0
    return [
        centre + right * sx * hw + up * sy * hd
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    ]


def _miter_ring(
    centre: Vec3, incoming: Vec3, outgoing: Vec3, width: float, depth: float
) -> list[Vec3]:
    """Intersect the incoming rail's four longitudinal edges with the bend bisector.

    Each result is used by both adjacent segments. There are therefore no internal end
    caps, duplicate vertices, overlapping shells, or numerical crack at the bend.
    """
    normal_sum = incoming + outgoing
    if normal_sum.length() < 1e-8:
        raise ValueError("a handrail path cannot reverse direction at one vertex")
    miter_normal = normal_sum.normalized()
    denominator = incoming.dot(miter_normal)
    if abs(denominator) < 1e-8:
        raise ValueError("handrail bend is too sharp for a finite miter")

    right, up = _frame(incoming)
    hw, hd = width / 2.0, depth / 2.0
    ring = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        offset = right * sx * hw + up * sy * hd
        distance = -offset.dot(miter_normal) / denominator
        ring.append(centre + offset + incoming * distance)
    return ring


def mitered_rectangular_sweep(
    path: list[Vec3], width: float, depth: float
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """A closed, single-shell rectangular rail following an open polyline."""
    tangents = [(b - a).normalized() for a, b in zip(path, path[1:])]
    rings = [_endpoint_ring(path[0], tangents[0], width, depth)]
    rings.extend(
        _miter_ring(point, incoming, outgoing, width, depth)
        for point, incoming, outgoing in zip(path[1:-1], tangents, tangents[1:])
    )
    rings.append(_endpoint_ring(path[-1], tangents[-1], width, depth))

    vertices = [vertex for ring in rings for vertex in ring]
    faces: list[tuple[int, ...]] = [(0, 1, 2, 3)]
    for ring_index in range(len(rings) - 1):
        start = ring_index * 4
        end = start + 4
        faces.extend(
            (
                (start, end, end + 1, start + 1),
                (start + 1, end + 1, end + 2, start + 2),
                (start + 2, end + 2, end + 3, start + 3),
                (start + 3, end + 3, end, start),
            )
        )
    last = (len(rings) - 1) * 4
    faces.append((last + 3, last + 2, last + 1, last))
    return vertices, faces
