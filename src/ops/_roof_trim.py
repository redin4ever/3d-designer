"""Shared compound-miter geometry for the rake and fascia roof perimeter."""

from __future__ import annotations

from contracts import Vec3

__all__ = ["perimeter_trim_meshes"]

Mesh = tuple[list[Vec3], list[tuple[int, ...]]]
Ring = tuple[Vec3, Vec3, Vec3, Vec3]


def perimeter_trim_meshes(
    origin: Vec3,
    axis: str,
    half_roof: float,
    half_length: float,
    eave_z: float,
    ridge_z: float,
    width: float,
    depth: float,
) -> dict[str, Mesh]:
    """Four closed boards cut from one six-corner miter-ring layout.

    Adjacent boards receive the exact same four corner vertices. Their end faces therefore
    meet across a full compound-miter plane instead of touching at one point or needing a
    visible cover block.
    """
    points = (
        _point(origin, axis, -half_roof, -half_length, eave_z),
        _point(origin, axis, 0.0, -half_length, ridge_z),
        _point(origin, axis, half_roof, -half_length, eave_z),
        _point(origin, axis, half_roof, half_length, eave_z),
        _point(origin, axis, 0.0, half_length, ridge_z),
        _point(origin, axis, -half_roof, half_length, eave_z),
    )
    expected_outward = (
        _direction(axis, 0.0, -1.0),
        _direction(axis, 0.0, -1.0),
        _direction(axis, 1.0, 0.0),
        _direction(axis, 0.0, 1.0),
        _direction(axis, 0.0, 1.0),
        _direction(axis, -1.0, 0.0),
    )
    world_up = Vec3(0.0, 0.0, 1.0)
    tangents: list[Vec3] = []
    sides: list[Vec3] = []
    profile_ups: list[Vec3] = []
    for index, point in enumerate(points):
        tangent = (points[(index + 1) % len(points)] - point).normalized()
        side = tangent.cross(world_up).normalized()
        if side.dot(expected_outward[index]) < 0.0:
            side = side * -1.0
        tangents.append(tangent)
        sides.append(side)
        profile_ups.append(side.cross(tangent).normalized())

    rings = tuple(
        _miter_ring(
            point,
            sides[index - 1],
            sides[index],
            profile_ups[index - 1],
            profile_ups[index],
            width,
            depth,
        )
        for index, point in enumerate(points)
    )
    return {
        "gable_neg": _swept_mesh((rings[0], rings[1], rings[2])),
        "gable_pos": _swept_mesh((rings[3], rings[4], rings[5])),
        "eave_neg": _swept_mesh((rings[5], rings[0])),
        "eave_pos": _swept_mesh((rings[2], rings[3])),
    }


def _miter_ring(
    point: Vec3,
    side_a: Vec3,
    side_b: Vec3,
    up_a: Vec3,
    up_b: Vec3,
    width: float,
    depth: float,
) -> Ring:
    side = (side_a + side_b).normalized()
    up = (up_a + up_b).normalized()
    side_projection = min(abs(side.dot(side_a)), abs(side.dot(side_b)))
    up_projection = min(abs(up.dot(up_a)), abs(up.dot(up_b)))
    outward = width / max(side_projection, 1e-9)
    half_depth = depth / (2.0 * max(up_projection, 1e-9))
    return (
        point - up * half_depth,
        point + side * outward - up * half_depth,
        point + side * outward + up * half_depth,
        point + up * half_depth,
    )


def _swept_mesh(rings: tuple[Ring, ...]) -> Mesh:
    verts = [vertex for ring in rings for vertex in ring]
    last = len(verts) - 4
    faces: list[tuple[int, ...]] = [(0, 1, 2, 3), (last + 3, last + 2, last + 1, last)]
    for start in range(0, last, 4):
        end = start + 4
        faces.extend(
            (
                (start, end, end + 1, start + 1),
                (start + 1, end + 1, end + 2, start + 2),
                (start + 2, end + 2, end + 3, start + 3),
                (start + 3, end + 3, end, start),
            )
        )
    return verts, faces


def _point(origin: Vec3, axis: str, cross: float, along: float, z: float) -> Vec3:
    if axis == "y":
        return Vec3(origin.x + cross, origin.y + along, z)
    return Vec3(origin.x + along, origin.y + cross, z)


def _direction(axis: str, cross: float, along: float) -> Vec3:
    if axis == "y":
        return Vec3(cross, along, 0.0)
    return Vec3(along, cross, 0.0)
