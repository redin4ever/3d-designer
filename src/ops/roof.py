"""``add_gable_roof`` — a detailed roof assembly derived from architectural dimensions."""

from __future__ import annotations

import math

from contracts import EngineProtocol, Operation, OperationResult, Vec3

from ._geom import oriented_box_between
from .validation import validate_params

__all__ = ["add_gable_roof"]


def add_gable_roof(engine: EngineProtocol, op: Operation) -> OperationResult:
    """Build two exact-pitch slabs plus continuous ridge, rake and eave trim.

    ``origin`` is the centre of the building footprint at the wall-top bearing plane.
    ``width`` and ``depth`` are the wall footprint; overhang is added outside both. The
    pitch is measured from horizontal over half the *wall* span, so adding overhang lowers
    the outer eave without moving the ridge — the relationship a real roof keeps.
    """
    p = validate_params("add_gable_roof", op.params)
    prefix = p["object_id"]
    origin = p["origin"]
    axis = p["ridge_axis"]
    width, depth = p["width"], p["depth"]
    pitch_radians = math.radians(p["pitch_degrees"])
    pitch = math.tan(pitch_radians)
    thickness, overhang = p["thickness"], p["overhang"]
    trim_width, trim_depth = p["trim_width"], p["trim_depth"]

    # Width is always the gable span and depth is always the ridge length. Changing the
    # ridge axis rotates that architectural footprint; it does not silently swap the two
    # dimensions the caller supplied.
    span = width
    length = depth
    half_roof = span / 2.0 + overhang
    half_length = length / 2.0 + overhang
    ridge_z = origin.z + pitch * span / 2.0
    eave_z = origin.z - pitch * overhang

    neg_id = engine.create_mesh(
        f"{prefix}_slope_neg",
        *_panel_mesh(origin, axis, -half_roof, 0.0, half_length, ridge_z, pitch, thickness),
    )
    pos_id = engine.create_mesh(
        f"{prefix}_slope_pos",
        *_panel_mesh(origin, axis, 0.0, half_roof, half_length, ridge_z, pitch, thickness),
    )

    # Finish the ridge cap at the same visible height as the rake's vertical miter. The
    # previous cap merely touched the miter at its bottom corner and projected 183 mm
    # above it, which rendered as a square block perched on the white V. Lowering it by
    # the derived overlap makes the three boards read as one continuous trim system.
    rake_miter_depth = trim_depth / (2.0 * math.cos(pitch_radians))
    ridge_center_z = (
        ridge_z + thickness / 2.0 + rake_miter_depth - trim_depth / 2.0
    )
    ridge_a = _point(origin, axis, 0.0, -half_length, ridge_center_z)
    ridge_b = _point(origin, axis, 0.0, half_length, ridge_center_z)
    ridge_id = engine.create_mesh(
        f"{prefix}_ridge_cap", *oriented_box_between(ridge_a, ridge_b, trim_width, trim_depth)
    )

    gable_ids = []
    for along_sign, label in ((-1.0, "neg"), (1.0, "pos")):
        along = along_sign * (half_length + trim_width / 2.0)
        points = (
            _point(origin, axis, -half_roof, along, eave_z + thickness / 2.0),
            _point(origin, axis, 0.0, along, ridge_z + thickness / 2.0),
            _point(origin, axis, half_roof, along, eave_z + thickness / 2.0),
        )
        trim_id = engine.create_mesh(
            f"{prefix}_gable_{label}_trim",
            *_mitered_v_mesh(points, trim_width, trim_depth),
        )
        gable_ids.append(trim_id)

    eave_ids = []
    for cross_sign, label in ((-1.0, "neg"), (1.0, "pos")):
        cross = cross_sign * (half_roof + trim_width / 2.0)
        a = _point(origin, axis, cross, -half_length, eave_z + thickness / 2.0)
        b = _point(origin, axis, cross, half_length, eave_z + thickness / 2.0)
        eave_ids.append(
            engine.create_mesh(
                f"{prefix}_eave_{label}_fascia",
                *oriented_box_between(a, b, trim_width, trim_depth),
            )
        )

    # Rake and fascia profiles otherwise meet at only one mathematical point: their square
    # ends are perpendicular to different paths. A small chamfered cover overlaps both
    # profiles at each perimeter corner, turning that fragile point contact into a finished
    # continuous junction without changing the caller's architectural dimensions.
    corner_ids = []
    corner_radius = trim_width * 0.75
    corner_z = eave_z + thickness / 2.0
    for along_sign, gable_label in ((-1.0, "neg"), (1.0, "pos")):
        along = along_sign * (half_length + trim_width / 4.0)
        for cross_sign, eave_label in ((-1.0, "neg"), (1.0, "pos")):
            cross = cross_sign * (half_roof + trim_width / 4.0)
            corner_ids.append(
                engine.create_mesh(
                    f"{prefix}_gable_{gable_label}_eave_{eave_label}_cap",
                    *_chamfered_corner_mesh(
                        origin, axis, cross, along, corner_z, corner_radius, trim_depth
                    ),
                )
            )

    return OperationResult(
        op_id=op.op_id,
        ok=True,
        produced_objects=(neg_id, pos_id, ridge_id, *gable_ids, *eave_ids, *corner_ids),
    )


def _point(origin: Vec3, axis: str, cross: float, along: float, z: float) -> Vec3:
    if axis == "y":
        return Vec3(origin.x + cross, origin.y + along, z)
    return Vec3(origin.x + along, origin.y + cross, z)


def _mitered_v_mesh(
    points: tuple[Vec3, Vec3, Vec3], width: float, depth: float
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """One closed rake-trim mesh with a shared, vertical miter at the ridge.

    Two separately swept boxes leave disconnected shells and need their square end caps
    shortened, which produced the visible 86 mm break below the ridge cap. This sweep has
    one apex ring. Its vertical offset is enlarged by ``1 / cos(pitch)`` so each leg keeps
    the requested perpendicular depth after the miter.
    """
    p0, apex, p2 = points
    forward_a = (apex - p0).normalized()
    forward_b = (p2 - apex).normalized()
    world_up = Vec3(0.0, 0.0, 1.0)

    side_a = forward_a.cross(world_up).normalized()
    side_b = forward_b.cross(world_up).normalized()
    up_a = side_a.cross(forward_a).normalized()
    up_b = side_b.cross(forward_b).normalized()

    # Keep profile ordering consistent when a future roof orientation reverses the
    # cross-product basis. A flipped ring would twist the four connecting side faces.
    if side_a.dot(side_b) < 0.0:
        side_b = side_b * -1.0
        up_b = up_b * -1.0

    miter_side = (side_a + side_b).normalized()
    miter_up = (up_a + up_b).normalized()
    half_width = width / 2.0
    half_depth = depth / 2.0
    miter_width = half_width / max(abs(miter_side.dot(side_a)), 1e-9)
    miter_depth = half_depth / max(abs(miter_up.dot(up_a)), 1e-9)

    def ring(point: Vec3, side: Vec3, up: Vec3, hw: float, hd: float) -> list[Vec3]:
        return [
            point - side * hw - up * hd,
            point + side * hw - up * hd,
            point + side * hw + up * hd,
            point - side * hw + up * hd,
        ]

    verts = [
        *ring(p0, side_a, up_a, half_width, half_depth),
        *ring(apex, miter_side, miter_up, miter_width, miter_depth),
        *ring(p2, side_b, up_b, half_width, half_depth),
    ]
    faces: list[tuple[int, ...]] = [(0, 1, 2, 3), (11, 10, 9, 8)]
    for start, end in ((0, 4), (4, 8)):
        faces.extend(
            (
                (start, end, end + 1, start + 1),
                (start + 1, end + 1, end + 2, start + 2),
                (start + 2, end + 2, end + 3, start + 3),
                (start + 3, end + 3, end, start),
            )
        )
    return verts, faces


def _chamfered_corner_mesh(
    origin: Vec3,
    axis: str,
    cross: float,
    along: float,
    center_z: float,
    radius: float,
    depth: float,
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """Closed octagonal cover joining one rake end to one fascia end."""
    sides = 8
    rings: list[Vec3] = []
    for z in (center_z - depth / 2.0, center_z + depth / 2.0):
        for index in range(sides):
            angle = 2.0 * math.pi * index / sides
            dx = radius * math.cos(angle)
            dy = radius * math.sin(angle)
            if axis == "y":
                rings.append(_point(origin, axis, cross + dx, along + dy, z))
            else:
                rings.append(_point(origin, axis, cross + dy, along + dx, z))
    faces: list[tuple[int, ...]] = [
        tuple(reversed(range(sides))),
        tuple(range(sides, sides * 2)),
    ]
    faces.extend(
        (index, (index + 1) % sides, sides + (index + 1) % sides, sides + index)
        for index in range(sides)
    )
    return rings, faces


def _panel_mesh(
    origin: Vec3,
    axis: str,
    cross_min: float,
    cross_max: float,
    half_length: float,
    ridge_z: float,
    pitch: float,
    thickness: float,
) -> tuple[list[Vec3], list[tuple[int, ...]]]:
    """One closed sloped slab, vertically thickened so the two ridge faces coincide."""
    if axis == "y":
        projected = (
            (cross_min, -half_length),
            (cross_max, -half_length),
            (cross_max, half_length),
            (cross_min, half_length),
        )
    else:
        projected = (
            (cross_min, -half_length),
            (cross_min, half_length),
            (cross_max, half_length),
            (cross_max, -half_length),
        )
    bottom = [
        _point(origin, axis, cross, along, ridge_z - abs(cross) * pitch)
        for cross, along in projected
    ]
    verts = bottom + [p + Vec3(0.0, 0.0, thickness) for p in bottom]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    return verts, faces
