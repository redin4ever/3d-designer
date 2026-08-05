"""Private geometry helpers shared by the ``ops`` handlers.

Not part of the public surface — ``ops/__init__.py`` never re-exports anything from here.
Exists purely so the box/prism math used by ``add_wall``, ``add_staircase``,
``add_railing`` and ``add_opening`` is written once instead of four times, keeping each
responsibility file under the 300-line modularity cap.

Everything here operates on plain ``contracts`` value types only — no engine, no bpy.
"""

from __future__ import annotations

from contracts import Vec3

__all__ = [
    "box_mesh",
    "oriented_box_between",
    "path_arc_length",
    "vec_component",
    "vec_with_axes",
]


def box_mesh(mins: Vec3, maxs: Vec3) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """An axis-aligned, closed, outward-wound box spanning ``mins`` to ``maxs``.

    Same winding convention as ``testing.mesh_helpers.unit_cube`` (bottom, top, then the
    four sides), so a mesh built here is watertight for the same reason that one is.
    """
    x0, y0, z0 = mins.x, mins.y, mins.z
    x1, y1, z1 = maxs.x, maxs.y, maxs.z
    verts = [
        Vec3(x0, y0, z0), Vec3(x1, y0, z0), Vec3(x1, y1, z0), Vec3(x0, y1, z0),
        Vec3(x0, y0, z1), Vec3(x1, y0, z1), Vec3(x1, y1, z1), Vec3(x0, y1, z1),
    ]
    faces: list[tuple[int, ...]] = [
        (0, 3, 2, 1),  # bottom
        (4, 5, 6, 7),  # top
        (0, 1, 5, 4),  # -Y
        (1, 2, 6, 5),  # +X
        (2, 3, 7, 6),  # +Y
        (3, 0, 4, 7),  # -X
    ]
    return verts, faces


def _basis_for_direction(forward: Vec3) -> tuple[Vec3, Vec3]:
    """A stable (right, up) pair perpendicular to ``forward`` (already unit length)."""
    reference = Vec3(0.0, 0.0, 1.0)
    if abs(forward.dot(reference)) > 0.999:
        reference = Vec3(1.0, 0.0, 0.0)
    right = forward.cross(reference).normalized()
    up = right.cross(forward).normalized()
    return right, up


def oriented_box_between(
    a: Vec3, b: Vec3, width: float, depth: float
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """A closed prism running from ``a`` to ``b``, ``width`` x ``depth`` in cross-section.

    ``width`` is measured along the perpendicular closest to horizontal ("right");
    ``depth`` along the remaining perpendicular ("up"). This is what a wall and the
    railing's top rail are both built from — swept geometry between two world points with
    no quaternion-from-yaw-angle math needed at the call site.
    """
    delta = b - a
    length = delta.length()
    if length < 1e-9:
        raise ValueError("cannot build a prism between two coincident points")
    forward = delta.normalized()
    right, up = _basis_for_direction(forward)
    hw, hd = width / 2.0, depth / 2.0
    offsets = [(-hw, -hd), (hw, -hd), (hw, hd), (-hw, hd)]
    start_ring = [a + right * rx + up * ry for rx, ry in offsets]
    end_ring = [b + right * rx + up * ry for rx, ry in offsets]
    verts = start_ring + end_ring
    faces: list[tuple[int, ...]] = [
        (0, 1, 2, 3),  # start cap
        (7, 6, 5, 4),  # end cap
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return verts, faces


def path_arc_length(path) -> float:
    """The polyline's own true length — sum of 3D segment lengths, never a projection."""
    total = 0.0
    for a, b in zip(path, path[1:]):
        total += (b - a).length()
    return total


def vec_component(v: Vec3, axis: str) -> float:
    return getattr(v, axis)


def vec_with_axes(**components: float) -> Vec3:
    return Vec3(components.get("x", 0.0), components.get("y", 0.0), components.get("z", 0.0))
